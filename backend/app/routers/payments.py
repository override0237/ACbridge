"""Payment endpoints.

In SIMULATED mode the payer "approves the mobile-money prompt" with simulate-approval. A real provider
would instead call job_service.settle_payment from a signed webhook (and these two routes would be disabled).
"""
import hmac
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.models import Payment, User, WebhookEvent
from app.routers.jobs import payment_out
from app.schemas import PaymentOut, PricingPolicyOut
from app.security.authentication import get_current_user
from app.services import audit_service, job_service, payment_providers, payment_service

router = APIRouter(tags=["payments"])


@router.get("/pricing", response_model=PricingPolicyOut)
def pricing() -> PricingPolicyOut:
    """Public fee policy, so artisans know the cost before they accept anything."""
    return PricingPolicyOut(**payment_service.pricing_policy(), notice=payment_providers.SIMULATION_NOTICE)


def _own_pending_payment(db: Session, user: User, payment_id: uuid.UUID):
    if not payment_providers.is_simulated():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    payment = payment_service.get_payment(db, payment_id)
    if payment is None or payment.payer_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")  # others' payments stay invisible
    return payment


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = payment_service.get_payment(db, payment_id)
    if payment is None or payment.payer_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment_out(payment)


@router.post("/payments/{payment_id}/simulate-approval", response_model=PaymentOut)
def simulate_approval(payment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = _own_pending_payment(db, user, payment_id)
    job_service.settle_payment(db, payment.payment_id, True, user)
    db.refresh(payment)
    return payment_out(payment)


@router.post("/payments/{payment_id}/simulate-failure", response_model=PaymentOut)
def simulate_failure(payment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = _own_pending_payment(db, user, payment_id)
    job_service.settle_payment(db, payment.payment_id, False, user)
    db.refresh(payment)
    return payment_out(payment)


@router.post("/webhooks/payments/{provider}")
async def payment_webhook(provider: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Provider callback. The HMAC-SHA256 signature of the RAW body (header X-Signature) is checked BEFORE the body is
    read; a missing or wrong signature returns 401 and changes nothing. Events are idempotent by event_id, and the
    payment status and ledger are written in one transaction.

    Body: {"event_id": "...", "provider_reference": "...", "status": "SUCCEEDED" | "FAILED"}
    """
    raw = await request.body()
    signature = request.headers.get("X-Signature", "")
    if not signature or not hmac.compare_digest(signature, payment_providers.sign_webhook(raw)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    if provider.lower() != get_settings().payment_provider.lower():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown provider")
    try:
        data = json.loads(raw)
        event_id, reference, outcome = str(data["event_id"])[:80], str(data["provider_reference"]), data["status"]
        if outcome not in ("SUCCEEDED", "FAILED"):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Body must contain event_id, provider_reference and status")

    already = db.scalar(select(WebhookEvent).where(WebhookEvent.provider == provider.lower(),
                                                   WebhookEvent.event_id == event_id))
    if already is not None:
        return {"status": "duplicate"}          # a replay: acknowledged, nothing is processed twice
    payment = db.scalar(select(Payment).where(Payment.provider_reference == reference))
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown payment reference")
    db.add(WebhookEvent(provider=provider.lower(), event_id=event_id,
                        payload_hash=audit_service.payload_hash({"event_id": event_id, "status": outcome})))
    audit_service.record(db, "PROVIDER", None, "WEBHOOK_RECEIVED", f"payment:{payment.payment_id}",
                         {"event_id": event_id, "status": outcome})
    try:
        job_service.settle_payment(db, payment.payment_id, outcome == "SUCCEEDED", payment.payer)  # commits everything
    except IntegrityError:
        db.rollback()                            # two identical callbacks raced: the other one won
        return {"status": "duplicate"}
    return {"status": "processed"}
