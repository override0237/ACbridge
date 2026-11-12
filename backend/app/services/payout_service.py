"""Artisan payouts:  PENDING -> RELEASED -> PAID, or HELD by a dispute / an operator, or FAILED when the escrow is refunded.

  * Created PENDING when the customer's payment succeeds (see ledger_service.on_payment_succeeded).
  * Released only when the job is COMPLETED (both sides confirmed) AND the job is not disputed. In the app this is the
    moment the correct job code is entered; the backend's own proof is the double confirmation.
  * PAID when the provider confirms the disbursement; the ledger moves the amount from artisan_pending to artisan_paid.
  * An operator can HOLD a payout (reason required) and later RELEASE it (reason required). Both write to the audit log.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.config import get_settings
from app.models import Job, JobEvent, JobStatus, Payout, PayoutStatus, PaymentStatus, PaymentType, User
from app.services import audit_service, ledger_service
from app.services.payment_providers import get_provider

P = PayoutStatus


def get_for_job(db: Session, job_id: uuid.UUID) -> Payout | None:
    return db.scalar(select(Payout).where(Payout.job_id == job_id))


def _lock(db: Session, payout_id: uuid.UUID) -> Payout:
    payout = db.scalar(select(Payout).where(Payout.payout_id == payout_id)
                       .with_for_update().execution_options(populate_existing=True))
    if payout is None:
        raise NotFoundError("Payout not found")
    return payout


def _audit(db: Session, actor_type: str, actor_id, action: str, payout: Payout, extra: dict | None = None) -> None:
    audit_service.record(db, actor_type, actor_id, action, f"payout:{payout.payout_id}",
                         {"status": payout.status, "amount": payout.amount, "job_id": str(payout.job_id), **(extra or {})})


def pay_out(db: Session, payout: Payout, actor_type: str, actor_id) -> None:
    """RELEASED -> PAID: ask the provider to disburse, then book it. Sandbox disbursements confirm immediately."""
    payout.status = P.RELEASED.value
    _audit(db, actor_type, actor_id, "PAYOUT_RELEASED", payout)
    payout.provider_reference = get_provider().payout(payout.payout_id, payout.amount)
    payout.status = P.PAID.value
    ledger_service.on_payout_paid(db, payout)
    payment = payout.payment
    if payment.payment_type == PaymentType.JOB_PAYMENT.value and payment.status == PaymentStatus.SUCCEEDED.value:
        payment.status = PaymentStatus.RELEASED.value   # the escrow has been paid out
    db.add(JobEvent(job_id=payout.job_id, actor_id=actor_id, event_type="PAYOUT_RELEASED", event_metadata={
        "payment_id": str(payment.payment_id), "amount": payout.amount, "commission": payout.commission,
        "reference": payout.provider_reference, "simulated": get_settings().payment_provider == "simulated"}))
    _audit(db, "PROVIDER", None, "PAYOUT_PAID", payout, {"provider_reference": payout.provider_reference})


def release_for_completed_job(db: Session, job: Job, actor: User) -> bool:
    """Called when the job becomes COMPLETED. Returns True if the artisan was paid."""
    payout = get_for_job(db, job.job_id)
    if payout is None or payout.status != P.PENDING.value:
        return False   # nothing to pay, already paid, or held (an operator must release a held payout)
    if job.status != JobStatus.COMPLETED.value:
        return False
    pay_out(db, payout, "USER", actor.user_id)
    return True


def hold_for_dispute(db: Session, job: Job, actor: User, reason: str) -> None:
    payout = get_for_job(db, job.job_id)
    if payout is not None and payout.status in (P.PENDING.value, P.RELEASED.value):
        payout.status, payout.note = P.HELD.value, f"dispute: {reason}"[:300]
        _audit(db, "USER", actor.user_id, "PAYOUT_HELD", payout, {"reason": "dispute opened"})


def resume_after_dispute(db: Session, job: Job, actor: User) -> None:
    """Dispute resolved in favour of continuing the work: a dispute hold goes back to PENDING."""
    payout = get_for_job(db, job.job_id)
    if payout is not None and payout.status == P.HELD.value and (payout.note or "").startswith("dispute"):
        payout.status, payout.note = P.PENDING.value, None
        _audit(db, "OPERATOR", actor.user_id, "PAYOUT_RESUMED", payout)


def void_after_refund(db: Session, job: Job, actor: User, reason: str) -> None:
    payout = get_for_job(db, job.job_id)
    if payout is not None and payout.status in (P.PENDING.value, P.RELEASED.value, P.HELD.value):
        payout.status, payout.note = P.FAILED.value, f"voided: {reason}"[:300]
        _audit(db, "SYSTEM", None, "PAYOUT_VOIDED", payout, {"reason": reason})


# ------------------------------------------------------------------------------- operator actions
def operator_hold(db: Session, operator: User, payout_id: uuid.UUID, reason: str) -> Payout:
    payout = _lock(db, payout_id)
    if payout.status not in (P.PENDING.value, P.RELEASED.value):
        raise ConflictError(f"A {payout.status} payout cannot be held")
    payout.status, payout.note = P.HELD.value, f"operator: {reason}"[:300]
    _audit(db, "OPERATOR", operator.user_id, "PAYOUT_HELD", payout, {"reason": reason})
    db.commit()
    return payout


def operator_release(db: Session, operator: User, payout_id: uuid.UUID, reason: str) -> Payout:
    payout = _lock(db, payout_id)
    if payout.status not in (P.PENDING.value, P.HELD.value):
        raise ConflictError(f"A {payout.status} payout cannot be released")
    job = db.get(Job, payout.job_id)
    if job.status == JobStatus.DISPUTED.value:
        raise ConflictError("This job has an open dispute: resolve the dispute before releasing the payout")
    if job.status != JobStatus.COMPLETED.value:
        raise ConflictError("The payout can only be released after the job is confirmed complete")
    payout.note = f"operator release: {reason}"[:300]
    _audit(db, "OPERATOR", operator.user_id, "PAYOUT_RELEASE_REQUESTED", payout, {"reason": reason})
    pay_out(db, payout, "OPERATOR", operator.user_id)
    db.commit()
    return payout
