"""Operator payments panel API (administrators only): payments, ledger, payouts with hold/release, reconciliation."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AuditLog, LedgerEntry, Payment, Payout, Role, User
from app.schemas import (
    AuditLogOut, LedgerEntryOut, LedgerOut, OperatorPaymentOut, PayoutOut, ReasonIn, ReconciliationOut,
)
from app.security.permissions import require_roles
from app.services import ledger_service, payout_service, reconciliation_service
from app.services.privacy import mask_phone

router = APIRouter(prefix="/operator", tags=["operator payments"])
Operator = Depends(require_roles(Role.ADMIN))


def _payout_out(p: Payout) -> PayoutOut:
    return PayoutOut(payout_id=p.payout_id, job_id=p.job_id, artisan_id=p.artisan_id, artisan_name=p.artisan.full_name,
                     payment_id=p.payment_id, amount=p.amount, commission=p.commission, status=p.status,
                     provider_reference=p.provider_reference, note=p.note, created_at=p.created_at, updated_at=p.updated_at)


@router.get("/payments", response_model=list[OperatorPaymentOut])
def payments(limit: int = Query(100, ge=1, le=500), _: User = Operator, db: Session = Depends(get_db)):
    rows = db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(limit))
    return [OperatorPaymentOut(
        payment_id=p.payment_id, job_id=p.job_id, payment_type=p.payment_type, amount=p.amount, currency=p.currency,
        status=p.status, provider=p.provider, provider_reference=p.provider_reference, created_at=p.created_at,
        settled_at=p.settled_at, payer_phone_masked=mask_phone(p.payer.phone)) for p in rows]


@router.get("/ledger", response_model=LedgerOut)
def ledger(limit: int = Query(100, ge=1, le=500), _: User = Operator, db: Session = Depends(get_db)) -> LedgerOut:
    entries = db.scalars(select(LedgerEntry).order_by(LedgerEntry.created_at.desc(), LedgerEntry.tx_key).limit(limit))
    unbalanced = ledger_service.unbalanced_transactions(db)
    return LedgerOut(balances=ledger_service.balances(db), balanced=not unbalanced, unbalanced_transactions=unbalanced,
                     entries=[LedgerEntryOut.model_validate(e) for e in entries])


@router.get("/payouts", response_model=list[PayoutOut])
def payouts(_: User = Operator, db: Session = Depends(get_db)) -> list[PayoutOut]:
    return [_payout_out(p) for p in db.scalars(select(Payout).order_by(Payout.created_at.desc()))]


@router.post("/payouts/{payout_id}/hold", response_model=PayoutOut)
def hold(payout_id: uuid.UUID, payload: ReasonIn, operator: User = Operator, db: Session = Depends(get_db)) -> PayoutOut:
    """Stop a payout. A reason is required and the action is written to the audit log."""
    return _payout_out(payout_service.operator_hold(db, operator, payout_id, payload.reason))


@router.post("/payouts/{payout_id}/release", response_model=PayoutOut)
def release(payout_id: uuid.UUID, payload: ReasonIn, operator: User = Operator,
            db: Session = Depends(get_db)) -> PayoutOut:
    """Release a held payout after the job is complete and not disputed. A reason is required and audited."""
    return _payout_out(payout_service.operator_release(db, operator, payout_id, payload.reason))


@router.get("/reconciliation", response_model=ReconciliationOut)
def reconciliation(
    provider_collected_override: int | None = Query(None, ge=0, description="SANDBOX ONLY: pretend the provider reports this total"),
    _: User = Operator, db: Session = Depends(get_db),
) -> ReconciliationOut:
    if provider_collected_override is not None and get_settings().payment_provider != "simulated":
        provider_collected_override = None
    return ReconciliationOut(**reconciliation_service.reconcile(db, provider_collected_override))


@router.get("/audit", response_model=list[AuditLogOut])
def audit(limit: int = Query(100, ge=1, le=500), _: User = Operator, db: Session = Depends(get_db)):
    return list(db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)))
