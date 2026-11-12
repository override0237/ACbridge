"""Job lifecycle as an explicit STATE MACHINE.

    REQUESTED --accept--> ACCEPTED --start--> IN_PROGRESS --first confirmation--> PENDING_CONFIRMATION
        |                    |                    |                                      |
        +--cancel--> CANCELLED <--cancel----------+                         second confirmation
                                                  |                                      v
                                                  +--dispute--> DISPUTED <--dispute-- COMPLETED
    DISPUTED --admin resolves--> CANCELLED | IN_PROGRESS            (COMPLETED and CANCELLED are final)

Cooling-off ("probation"): when the price is agreed (fixed price: the artisan agrees; inspection job: the
customer approves the quote) a PROBATION_HOURS window (default 24h) starts. During it either party may withdraw
for free, the artisan cannot pay the commission and the customer cannot pay into escrow. Afterwards the artisan
confirms (commission) and the customer pays: those payments are the final commitment. Once committed, a job can
no longer be cancelled normally; refunds happen only through a proven hardship claim (hardship_service).

Money gates (see payment_service):
  * REQUESTED -> ACCEPTED happens only when the artisan has agreed to the terms AND paid the platform fee
    (commission on a fixed price, or the flat assignment fee for jobs needing inspection).
  * Inspection jobs: after assignment the artisan quotes, the customer approves the quote.
  * ACCEPTED -> IN_PROGRESS requires an agreed price AND the customer's payment held in escrow.
  * COMPLETED releases the escrow to the artisan; CANCELLED refunds it.

Rules enforced here (never by the client):
  * Only transitions listed in ALLOWED_TRANSITIONS are possible.
  * Only the two parties to the job can act on it (admins only resolve disputes).
  * COMPLETED requires BOTH confirmations - also guaranteed by a database CHECK constraint.
  * Each transition runs in one transaction, holding a row lock (SELECT ... FOR UPDATE on PostgreSQL),
    so simultaneous or repeated requests cannot produce an inconsistent job.
  * Every transition writes an append-only job_events row.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError
from app.models import (
    AvailabilityStatus, Job, JobEvent, JobStatus, PaymentStatus, PaymentType, PricingMode, RequestStatus, Role,
    ServiceRequest, User,
)
from app.services import payment_service
from app.services.contact_service import artisan_to_customer_message, whatsapp_link
from app.services.matching_service import is_eligible_for_request

S = JobStatus
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    S.REQUESTED.value: frozenset({S.ACCEPTED.value, S.CANCELLED.value}),
    S.ACCEPTED.value: frozenset({S.IN_PROGRESS.value, S.CANCELLED.value}),
    # CANCELLED from IN_PROGRESS / PENDING_CONFIRMATION is reachable ONLY through a proven hardship claim.
    S.IN_PROGRESS.value: frozenset({S.PENDING_CONFIRMATION.value, S.DISPUTED.value, S.CANCELLED.value}),
    S.PENDING_CONFIRMATION.value: frozenset({S.COMPLETED.value, S.DISPUTED.value, S.CANCELLED.value}),
    S.DISPUTED.value: frozenset({S.IN_PROGRESS.value, S.CANCELLED.value}),
    S.COMPLETED.value: frozenset(),
    S.CANCELLED.value: frozenset(),
}
# Keeps service_requests.status in step with its job.
_REQUEST_STATUS_FOR_JOB = {
    S.REQUESTED.value: RequestStatus.MATCHED, S.ACCEPTED.value: RequestStatus.MATCHED,
    S.IN_PROGRESS.value: RequestStatus.IN_PROGRESS, S.PENDING_CONFIRMATION.value: RequestStatus.IN_PROGRESS,
    S.DISPUTED.value: RequestStatus.IN_PROGRESS, S.COMPLETED.value: RequestStatus.COMPLETED,
    S.CANCELLED.value: RequestStatus.CANCELLED,
}


# ----------------------------------------------------------------------------- helpers
def party_of(job: Job, user: User) -> str | None:
    if job.request.customer_id == user.user_id:
        return "CUSTOMER"
    if job.artisan.user_id == user.user_id:
        return "ARTISAN"
    return None


def get_job_for_party(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    if user.role != Role.ADMIN.value and party_of(job, user) is None:
        raise PermissionDeniedError("You are not a party to this job")
    return job


def _lock_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.scalar(
        select(Job).where(Job.job_id == job_id).with_for_update().execution_options(populate_existing=True)
    )
    if job is None:
        raise NotFoundError("Job not found")
    return job


def _record(db: Session, job: Job, actor: User, event_type: str, metadata: dict | None = None) -> None:
    db.add(JobEvent(job_id=job.job_id, actor_id=actor.user_id, event_type=event_type, event_metadata=metadata))


def _transition(db: Session, job: Job, new_status: str, actor: User, event_type: str, metadata: dict | None = None) -> None:
    if new_status not in ALLOWED_TRANSITIONS[job.status]:
        raise ConflictError(f"Invalid transition: a {job.status} job cannot become {new_status}")
    previous = job.status
    job.status = new_status
    job.request.status = _REQUEST_STATUS_FOR_JOB[new_status].value
    _record(db, job, actor, event_type, {**(metadata or {}), "from": previous, "to": new_status})


def _require_party(job: Job, user: User, expected: str) -> None:
    party = party_of(job, user)
    if party is None:
        raise PermissionDeniedError("You are not a party to this job")
    if party != expected:
        raise PermissionDeniedError(f"Only the {expected.lower()} can do this")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes


def probation_active(job: Job) -> bool:
    return job.probation_ends_at is not None and _now() < _aware(job.probation_ends_at)


def can_cancel_freely(job: Job) -> bool:
    """Normal cancellation is only possible before commitment: before the artisan's fee is paid (REQUESTED),
    or on an accepted job while no price is agreed yet / the cooling-off period is still running."""
    if job.status == S.REQUESTED.value:
        return True
    return job.status == S.ACCEPTED.value and (job.agreed_price is None or probation_active(job))


def _start_probation(job: Job) -> datetime:
    job.terms_agreed_at = _now()
    job.probation_ends_at = job.terms_agreed_at + timedelta(hours=get_settings().probation_hours)
    return job.probation_ends_at


def split_model() -> bool:
    """True when the customer pays the commission as part of the price (see config.commission_model)."""
    return get_settings().commission_model == "customer_split"


def _require_quote_not_expired(job: Job) -> None:
    """A proposed price is only valid for quote_ttl_hours. Once the artisan has agreed, the price is frozen."""
    ttl = get_settings().quote_ttl_hours
    if ttl > 0 and not job.artisan_agreed and _now() > _aware(job.created_at) + timedelta(hours=ttl):
        raise ConflictError(f"This price proposal expired after {ttl} hours: ask for a new one")


def _require_probation_over(job: Job) -> None:
    if probation_active(job):
        raise ConflictError(
            f"Cooling-off period: both sides can still withdraw until {_aware(job.probation_ends_at).isoformat()}. "
            "Payments open when it ends."
        )


# ----------------------------------------------------------------------------- actions
def create_job(db: Session, customer: User, request_id: uuid.UUID, artisan_id: uuid.UUID,
               proposed_price: int | None) -> Job:
    """Customer picks an artisan for their request. Eligibility is re-checked on the server."""
    service_request = db.scalar(
        select(ServiceRequest).where(ServiceRequest.request_id == request_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if service_request is None or service_request.customer_id != customer.user_id:
        raise NotFoundError("Service request not found")
    if service_request.status != RequestStatus.OPEN.value:
        raise ConflictError("This request already has an artisan assigned or is closed")

    # The kind of job follows the REQUEST: problems that need inspection have no price yet.
    if service_request.needs_inspection:
        if proposed_price is not None:
            raise BadRequestError("This request needs inspection first: do not propose a price yet")
        mode = PricingMode.INSPECTION_REQUIRED.value
    else:
        if proposed_price is None:
            raise BadRequestError("proposed_price is required for a fixed-price job")
        mode = PricingMode.FIXED_PRICE.value

    reason = is_eligible_for_request(db, service_request, artisan_id)
    if reason is not None:
        raise BadRequestError(f"This artisan cannot take this request ({reason})")

    job = Job(request_id=request_id, artisan_id=artisan_id, pricing_mode=mode, status=S.REQUESTED.value,
              proposed_price=proposed_price, proposed_by="CUSTOMER" if proposed_price is not None else None)
    db.add(job)
    service_request.status = RequestStatus.MATCHED.value
    try:
        db.flush()
    except IntegrityError:  # UNIQUE(request_id): another request won the race
        db.rollback()
        raise ConflictError("This request already has a job")
    _record(db, job, customer, "JOB_REQUESTED", {"pricing_mode": mode, "proposed_price": proposed_price})
    db.commit()
    return job


def accept_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    """The artisan agrees to the terms.

    Fixed price : the price becomes agreed and the cooling-off period starts. NO money moves yet; after the
                  period the artisan calls confirm-terms, which creates the commission payment.
    Inspection  : the flat assignment fee is due immediately (the price comes later, from the quote).
    Repeating the call never restarts probation or double-charges.
    """
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    if job.status != S.REQUESTED.value:
        raise ConflictError(f"A {job.status} job cannot be accepted")
    _require_artisan_in_good_standing(job)
    _require_quote_not_expired(job)

    if job.pricing_mode == PricingMode.FIXED_PRICE.value:
        if not job.artisan_agreed:
            job.artisan_agreed = True
            job.agreed_price = job.proposed_price          # the artisan confirmed they are OK with the amount
            ends = _start_probation(job)
            _record(db, job, user, "TERMS_AGREED_BY_ARTISAN",
                    {"agreed_price": job.agreed_price, "probation_ends_at": ends.isoformat(),
                     "commission_if_confirmed": payment_service.compute_commission(job.agreed_price)})
    else:
        fee = get_settings().inspection_assignment_fee
        if not job.artisan_agreed:
            job.artisan_agreed = True
            _record(db, job, user, "TERMS_AGREED_BY_ARTISAN",
                    {"pricing_mode": job.pricing_mode, "fee": fee, "fee_type": PaymentType.ASSIGNMENT_FEE.value})
        payment_service.initiate(db, job, user, PaymentType.ASSIGNMENT_FEE.value, fee,
                                 "Flat assignment fee for a job that needs inspection before pricing")
    db.commit()
    return job


def confirm_terms(db: Session, user: User, job_id: uuid.UUID) -> Job:
    """Fixed-price jobs: after the cooling-off period the artisan makes the FINAL confirmation, which creates
    the commission payment. Paying it assigns the artisan (job ACCEPTED)."""
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    if job.pricing_mode != PricingMode.FIXED_PRICE.value:
        raise ConflictError("Only fixed-price jobs have a separate confirmation step")
    if job.status != S.REQUESTED.value or not job.artisan_agreed:
        raise ConflictError("Agree to the customer's price first (accept the job)")
    _require_probation_over(job)
    _require_artisan_in_good_standing(job)
    if split_model():
        # Customer-split model: the artisan pays nothing up front; the commission is cut from the customer's payment.
        _record(db, job, user, "TERMS_CONFIRMED_BY_ARTISAN", {"fee": 0, "commission_model": "customer_split"})
        _transition(db, job, S.ACCEPTED.value, user, "JOB_ACCEPTED", {"commission_model": "customer_split"})
        db.commit()
        return job
    first_time = payment_service.active_payment(job, PaymentType.COMMISSION.value) is None
    fee = payment_service.compute_commission(job.agreed_price)
    payment_service.initiate(db, job, user, PaymentType.COMMISSION.value, fee,
                             f"Platform commission on an agreed price of {job.agreed_price} FCFA")
    if first_time:
        _record(db, job, user, "TERMS_CONFIRMED_BY_ARTISAN", {"fee": fee})
    db.commit()
    return job


def _require_artisan_in_good_standing(job: Job) -> None:
    artisan = job.artisan
    if artisan.is_suspended or artisan.availability_status == AvailabilityStatus.UNAVAILABLE.value:
        raise ConflictError("You must be available and in good standing to take jobs")


def skip_probation_simulated(db: Session, admin: User, job_id: uuid.UUID) -> Job:
    """DEMO ONLY (simulated mode): end the cooling-off period now so a demo need not wait 24 hours."""
    if admin.role != Role.ADMIN.value:
        raise PermissionDeniedError("Only administrators can do this")
    job = _lock_job(db, job_id)
    if job.probation_ends_at is None:
        raise ConflictError("This job has no probation period")
    job.probation_ends_at = _now()
    _record(db, job, admin, "PROBATION_SKIPPED", {"simulated": True})
    db.commit()
    return job


def settle_payment(db: Session, payment_id: uuid.UUID, succeeded: bool, actor: User) -> Job:
    """Apply a provider result and unlock whatever the payment pays for. One transaction.

    A real provider would call this from a signed webhook; the simulated provider calls it from the
    simulate-approval/failure endpoints. Settling twice is harmless (idempotent).
    """
    payment = payment_service.get_payment(db, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found")
    job = _lock_job(db, payment.job_id)                       # lock order: job first, then payment
    payment = payment_service.lock_payment(db, payment_id)
    if not payment_service.mark_settled(db, payment, succeeded, actor):
        return job  # already settled: nothing more to do

    if succeeded and payment.payment_type in payment_service.FEE_TYPES and job.status == S.REQUESTED.value:
        _transition(db, job, S.ACCEPTED.value, actor, "JOB_ACCEPTED",
                    {"fee_type": payment.payment_type, "fee": payment.amount})
    db.commit()
    return job


def pay_job(db: Session, user: User, job_id: uuid.UUID, idempotency_key: str | None = None):
    """Customer pays the agreed price into escrow. The amount always comes from the job in the database, never the request.
    The same Idempotency-Key from the same customer returns the original payment instead of creating another."""
    job = _lock_job(db, job_id)
    _require_party(job, user, "CUSTOMER")
    if idempotency_key:
        from app.models import Payment
        previous = db.scalar(select(Payment).where(Payment.payer_id == user.user_id,
                                                   Payment.idempotency_key == idempotency_key))
        if previous is not None:
            if previous.job_id != job.job_id:
                raise ConflictError("This Idempotency-Key was already used for a different job")
            return previous
    if job.status != S.ACCEPTED.value:
        raise ConflictError("You can pay once the artisan has accepted the job (and before work starts)")
    if job.agreed_price is None:
        raise ConflictError("No price has been agreed yet: approve the artisan's quote first")
    _require_probation_over(job)
    payment = payment_service.initiate(
        db, job, user, PaymentType.JOB_PAYMENT.value, job.agreed_price, "Customer payment held in escrow"
    )
    if idempotency_key and payment.idempotency_key is None:
        payment.idempotency_key = idempotency_key
    db.commit()
    return payment


def propose_quote(db: Session, user: User, job_id: uuid.UUID, amount: int) -> Job:
    """Inspection jobs: after inspecting, the assigned artisan proposes a price."""
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    if job.pricing_mode != PricingMode.INSPECTION_REQUIRED.value:
        raise ConflictError("Only jobs that need inspection use quotes")
    if job.status != S.ACCEPTED.value or job.agreed_price is not None:
        raise ConflictError("A quote can only be given on an accepted job that has no agreed price yet")
    job.proposed_price, job.proposed_by = amount, "ARTISAN"
    _record(db, job, user, "QUOTE_PROPOSED", {"amount": amount})
    db.commit()
    return job


def respond_to_quote(db: Session, user: User, job_id: uuid.UUID, approve: bool) -> Job:
    job = _lock_job(db, job_id)
    _require_party(job, user, "CUSTOMER")
    if job.status != S.ACCEPTED.value or job.proposed_by != "ARTISAN" or job.agreed_price is not None:
        raise ConflictError("There is no open quote to answer")
    if approve:
        job.agreed_price = job.proposed_price
        ends = _start_probation(job)
        _record(db, job, user, "QUOTE_APPROVED", {"amount": job.agreed_price, "probation_ends_at": ends.isoformat()})
    else:
        _record(db, job, user, "QUOTE_REJECTED", {"amount": job.proposed_price})
        job.proposed_price, job.proposed_by = None, None
    db.commit()
    return job


def start_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    if job.status != S.ACCEPTED.value:
        raise ConflictError(f"A {job.status} job cannot be started")
    if job.agreed_price is None:
        raise ConflictError("Agree a price first (the customer must approve your quote)")
    escrow = payment_service.active_payment(job, PaymentType.JOB_PAYMENT.value)
    if escrow is None or escrow.status != PaymentStatus.SUCCEEDED.value:
        raise ConflictError("The customer must pay into escrow before work can start")
    _transition(db, job, S.IN_PROGRESS.value, user, "JOB_STARTED")
    db.commit()
    return job


def cancel_job(db: Session, user: User, job_id: uuid.UUID, reason: str | None) -> Job:
    job = _lock_job(db, job_id)
    party = party_of(job, user)
    if party is None:
        raise PermissionDeniedError("You are not a party to this job")
    if not can_cancel_freely(job):
        raise ConflictError(
            "This job is confirmed and can no longer be cancelled. If one of you has died, or had a serious accident "
            "or illness, file a hardship claim with proof; for any other problem, open a dispute."
        )
    _transition(db, job, S.CANCELLED.value, user, "JOB_CANCELLED",
                {"by": party, "reason": reason, "during_probation": probation_active(job)})
    payment_service.close_open_payments(db, job, user, reason or "job cancelled")
    db.commit()
    return job


def confirm_completion(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = _lock_job(db, job_id)  # serialises concurrent confirmations of the same job
    party = party_of(job, user)
    if party is None:
        raise PermissionDeniedError("You are not a party to this job")

    flag = "customer_confirmed" if party == "CUSTOMER" else "artisan_confirmed"
    if getattr(job, flag) and job.status in (S.PENDING_CONFIRMATION.value, S.COMPLETED.value):
        return job  # idempotent: a retried request (flaky mobile network) changes nothing
    if job.status not in (S.IN_PROGRESS.value, S.PENDING_CONFIRMATION.value):
        raise ConflictError(f"A {job.status} job cannot be confirmed as completed")

    setattr(job, flag, True)
    _record(db, job, user, "COMPLETION_CONFIRMED", {"party": party})
    if job.status == S.IN_PROGRESS.value:
        _transition(db, job, S.PENDING_CONFIRMATION.value, user, "JOB_PENDING_CONFIRMATION")
    if job.customer_confirmed and job.artisan_confirmed:
        job.completed_at = datetime.now(timezone.utc)
        _transition(db, job, S.COMPLETED.value, user, "JOB_COMPLETED")
        payment_service.release_escrow(db, job, user)       # artisan is paid only when both sides confirmed
    db.commit()
    return job


def open_dispute(db: Session, user: User, job_id: uuid.UUID, reason: str) -> Job:
    job = _lock_job(db, job_id)
    party = party_of(job, user)
    if party is None:
        raise PermissionDeniedError("You are not a party to this job")
    _transition(db, job, S.DISPUTED.value, user, "JOB_DISPUTED", {"by": party, "reason": reason})
    from app.services import payout_service
    payout_service.hold_for_dispute(db, job, user, reason)   # money never moves while a dispute is open
    db.commit()
    return job


def resolve_dispute(db: Session, admin: User, job_id: uuid.UUID, outcome: str, notes: str) -> Job:
    if admin.role != Role.ADMIN.value:
        raise PermissionDeniedError("Only administrators can resolve disputes")
    job = _lock_job(db, job_id)
    if job.status != S.DISPUTED.value:
        raise ConflictError("Only disputed jobs can be resolved")
    if outcome == S.IN_PROGRESS.value:
        # Work resumes; earlier confirmations are discarded so completion must be re-confirmed by both.
        job.customer_confirmed = False
        job.artisan_confirmed = False
        from app.services import payout_service
        payout_service.resume_after_dispute(db, job, admin)
    _transition(db, job, outcome, admin, "DISPUTE_RESOLVED", {"notes": notes})
    if outcome == S.CANCELLED.value:
        payment_service.close_open_payments(db, job, admin, notes)
    db.commit()
    return job


def cancel_for_hardship(db: Session, admin: User, job_id: uuid.UUID, claim_id: uuid.UUID, notes: str) -> Job:
    """Admin approved a proven hardship claim: cancel the job and refund fees + escrow in one transaction."""
    if admin.role != Role.ADMIN.value:
        raise PermissionDeniedError("Only administrators can approve hardship claims")
    job = _lock_job(db, job_id)
    _transition(db, job, S.CANCELLED.value, admin, "JOB_CANCELLED_HARDSHIP",
                {"claim_id": str(claim_id), "notes": notes})
    payment_service.refund_all(db, job, admin, f"hardship claim {claim_id}")
    return job


def job_is_paid(job: Job) -> bool:
    payment = payment_service.active_payment(job, PaymentType.JOB_PAYMENT.value)
    return payment is not None and payment.status in (PaymentStatus.SUCCEEDED.value, PaymentStatus.RELEASED.value)


def counterpart_phone(job: Job, user: User) -> str | None:
    """Phone numbers are shared only between the two parties, and only once the job is accepted."""
    if job.status in (S.REQUESTED.value, S.CANCELLED.value):
        return None
    if split_model() and not job_is_paid(job):
        return None   # contact details stay hidden until the customer's payment has succeeded
    party = party_of(job, user)
    if party == "CUSTOMER":
        return job.artisan.user.phone
    if party == "ARTISAN":
        return job.request.customer.phone
    return None


def counterpart_whatsapp_link(job: Job, user: User) -> str | None:
    """WhatsApp chat link to the other party (same visibility rule as the phone number)."""
    party = party_of(job, user)
    phone = counterpart_phone(job, user)
    if phone is None:
        return None
    if party == "CUSTOMER":
        # Respect the artisan's chosen WhatsApp number if they set one.
        number = job.artisan.whatsapp_number or phone
        return whatsapp_link(number, f"Hello {job.artisan.full_name.split()[0]}, about our ACbridge job (ref {str(job.job_id)[:8]}).")
    return whatsapp_link(phone, artisan_to_customer_message(job.artisan.full_name, str(job.job_id)))


def payments_visible_to(job: Job, user: User) -> list:
    """Customers see their own payment; artisans see their own fee and the escrow state; admins see all."""
    if user.role == Role.ADMIN.value:
        return list(job.payments)
    return [p for p in job.payments
            if p.payer_id == user.user_id or p.payment_type == PaymentType.JOB_PAYMENT.value]
