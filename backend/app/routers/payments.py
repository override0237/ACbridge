"""Payment endpoints.

In SIMULATED mode the payer "approves the mobile-money prompt" with simulate-approval. A real provider
would instead call job_service.settle_payment from a signed webhook (and these two routes would be disabled).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.jobs import payment_out
from app.schemas import PaymentOut, PricingPolicyOut
from app.security.authentication import get_current_user
from app.services import job_service, payment_providers, payment_service

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
