"""Platform payments: artisan commission / assignment fee, and customer escrow.

Money flow (all through the platform):
  1. Fixed-price job : customer proposes an amount -> artisan agrees -> artisan pays COMMISSION
                       (% of the price, with a minimum) -> job is ACCEPTED.
  2. Inspection job  : no price yet -> artisan pays a flat ASSIGNMENT_FEE -> job is ACCEPTED, the artisan
                       inspects and quotes, the customer approves the quote.
  3. Customer pays the agreed price into escrow (JOB_PAYMENT). Work cannot start until it is funded.
  4. Both sides confirm completion -> escrow is RELEASED to the artisan (full amount: the artisan's
     commission was already paid in step 1/2). Cancelled before completion -> escrow is REFUNDED.

Integers only (FCFA has no minor unit), so there is no floating-point money error.
This module records payments and writes audit events; job_service decides what a payment unlocks.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ConflictError
from app.models import Job, JobEvent, Payment, PaymentStatus, PaymentType, User
from app.services.payment_providers import get_provider

FEE_TYPES = (PaymentType.COMMISSION.value, PaymentType.ASSIGNMENT_FEE.value)


def compute_commission(agreed_price: int) -> int:
    settings = get_settings()
    return max(settings.commission_min, agreed_price * settings.commission_rate_bps // 10_000)


def pricing_policy() -> dict:
    settings = get_settings()
    return {
        "currency": "XAF",
        "fixed_price_commission_percent": settings.commission_rate_bps / 100,
        "fixed_price_commission_minimum": settings.commission_min,
        "inspection_assignment_fee": settings.inspection_assignment_fee,
        "fees_paid_by": "ARTISAN",
        "customer_pays": "the agreed price, held in escrow until the job is confirmed complete",
        "probation_hours": settings.probation_hours,
        "probation_rule": "After the price is agreed both sides have a cooling-off period: either may withdraw "
                          "for free and no fee or escrow can be paid until it ends.",
        "refund_policy": "Fees and escrow are refunded only after a confirmed job is cancelled because of the "
                         "death, or a serious accident/illness, of a party - proven by a death certificate or "
                         "medical records and approved by an administrator.",
        "provider": get_provider().name,
    }


def _event(db: Session, job_id: uuid.UUID, actor_id: uuid.UUID, event_type: str, metadata: dict) -> None:
    db.add(JobEvent(job_id=job_id, actor_id=actor_id, event_type=event_type, event_metadata=metadata))


def active_payment(job: Job, payment_type: str) -> Payment | None:
    """The single non-failed payment of this type, if any (the DB guarantees there is at most one)."""
    for payment in job.payments:
        if payment.payment_type == payment_type and payment.status != PaymentStatus.FAILED.value:
            return payment
    return None


def initiate(db: Session, job: Job, payer: User, payment_type: str, amount: int, description: str) -> Payment:
    existing = active_payment(job, payment_type)
    if existing is not None:
        return existing  # idempotent: a retried request never creates a second charge
    provider = get_provider()
    payment = Payment(
        job_id=job.job_id, payer_id=payer.user_id, payment_type=payment_type, amount=amount,
        status=PaymentStatus.PENDING.value, provider=provider.name, description=description,
    )
    payment.payment_id = uuid.uuid4()
    payment.provider_reference = provider.initiate_charge(payment.payment_id, payer.phone, amount)
    db.add(payment)
    try:
        db.flush()
    except IntegrityError:  # partial unique index: a concurrent request created it first
        db.rollback()
        raise ConflictError("A payment of this type already exists for this job")
    job.payments.append(payment)
    _event(db, job.job_id, payer.user_id, "PAYMENT_INITIATED",
           {"payment_id": str(payment.payment_id), "type": payment_type, "amount": amount})
    return payment


def mark_settled(db: Session, payment: Payment, succeeded: bool, actor: User) -> bool:
    """Apply a provider result. Returns False (and changes nothing) if it was already settled."""
    if payment.status != PaymentStatus.PENDING.value:
        return False
    payment.status = PaymentStatus.SUCCEEDED.value if succeeded else PaymentStatus.FAILED.value
    payment.settled_at = datetime.now(timezone.utc)
    _event(db, payment.job_id, actor.user_id, "PAYMENT_SUCCEEDED" if succeeded else "PAYMENT_FAILED",
           {"payment_id": str(payment.payment_id), "type": payment.payment_type, "amount": payment.amount})
    from app.services import audit_service, ledger_service   # imported here: they import this module too
    audit_service.record(db, "PROVIDER", None, "PAYMENT_SUCCEEDED" if succeeded else "PAYMENT_FAILED",
                         f"payment:{payment.payment_id}", {"type": payment.payment_type, "amount": payment.amount})
    if succeeded:
        ledger_service.on_payment_succeeded(db, payment)   # books the money; a customer payment also creates the payout
    return True


def release_escrow(db: Session, job: Job, actor: User) -> None:
    """Job completed: the artisan's payout is released and paid (unless it is held), see payout_service."""
    payment = active_payment(job, PaymentType.JOB_PAYMENT.value)
    if payment is None or payment.status != PaymentStatus.SUCCEEDED.value:
        return
    from app.services import payout_service
    payout_service.release_for_completed_job(db, job, actor)


def _book_refund(db: Session, job: Job, payment: Payment, actor: User, reason: str) -> None:
    """Ledger + payout + audit for a refund REQUEST (the sandbox provider call has already been simulated)."""
    from app.services import audit_service, ledger_service, payout_service
    ledger_service.on_refund(db, payment)
    if payment.payment_type == PaymentType.JOB_PAYMENT.value:
        payout_service.void_after_refund(db, job, actor, reason)
    audit_service.record(db, "USER", actor.user_id, "REFUND_RECORDED", f"payment:{payment.payment_id}",
                         {"type": payment.payment_type, "amount": payment.amount, "reason": reason})


def close_open_payments(db: Session, job: Job, actor: User, reason: str) -> None:
    """Dispute resolved as cancelled: refund escrow already paid, and void any charge still waiting for approval.
    Platform fees are NEVER returned here: only a proven hardship claim refunds them (see refund_all)."""
    for payment in job.payments:
        if payment.payment_type == PaymentType.JOB_PAYMENT.value and payment.status == PaymentStatus.SUCCEEDED.value:
            reference = get_provider().refund(payment.payment_id, payment.amount)
            payment.status = PaymentStatus.REFUNDED.value
            _event(db, job.job_id, actor.user_id, "ESCROW_REFUNDED",
                   {"payment_id": str(payment.payment_id), "amount": payment.amount, "reference": reference,
                    "reason": reason})
            _book_refund(db, job, payment, actor, reason)
        elif payment.status == PaymentStatus.PENDING.value:
            payment.status = PaymentStatus.FAILED.value
            payment.settled_at = datetime.now(timezone.utc)
            _event(db, job.job_id, actor.user_id, "PAYMENT_VOIDED",
                   {"payment_id": str(payment.payment_id), "reason": reason})


def refund_all(db: Session, job: Job, actor: User, reason: str) -> None:
    """Proven-hardship cancellation: refund EVERYTHING paid for this job (platform fees and escrow)
    and void anything still pending. This is the only path that returns platform fees."""
    provider = get_provider()
    for payment in job.payments:
        if payment.status == PaymentStatus.SUCCEEDED.value:
            reference = provider.refund(payment.payment_id, payment.amount)
            payment.status = PaymentStatus.REFUNDED.value
            kind = "FEE_REFUNDED" if payment.payment_type in FEE_TYPES else "ESCROW_REFUNDED"
            _event(db, job.job_id, actor.user_id, kind,
                   {"payment_id": str(payment.payment_id), "amount": payment.amount, "reference": reference,
                    "reason": reason})
            _book_refund(db, job, payment, actor, reason)
        elif payment.status == PaymentStatus.PENDING.value:
            payment.status = PaymentStatus.FAILED.value
            payment.settled_at = datetime.now(timezone.utc)
            _event(db, job.job_id, actor.user_id, "PAYMENT_VOIDED",
                   {"payment_id": str(payment.payment_id), "reason": reason})


def get_payment(db: Session, payment_id: uuid.UUID) -> Payment | None:
    return db.get(Payment, payment_id)


def lock_payment(db: Session, payment_id: uuid.UUID) -> Payment | None:
    return db.scalar(
        select(Payment).where(Payment.payment_id == payment_id)
        .with_for_update().execution_options(populate_existing=True)
    )
