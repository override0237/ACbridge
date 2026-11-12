"""Job lifecycle as an explicit STATE MACHINE.

    REQUESTED --accept--> ACCEPTED --start--> IN_PROGRESS --first confirmation--> PENDING_CONFIRMATION
        |                    |                    |                                      |
        +--cancel--> CANCELLED <--cancel----------+                         second confirmation
                                                  |                                      v
                                                  +--dispute--> DISPUTED <--dispute-- COMPLETED
    DISPUTED --admin resolves--> CANCELLED | IN_PROGRESS            (COMPLETED and CANCELLED are final)

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
from datetime import datetime, timezone

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
    S.IN_PROGRESS.value: frozenset({S.PENDING_CONFIRMATION.value, S.DISPUTED.value}),
    S.PENDING_CONFIRMATION.value: frozenset({S.COMPLETED.value, S.DISPUTED.value}),
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
    """The artisan agrees to the terms. The job only becomes ACCEPTED once the platform fee is paid.

    Fixed price  -> fee = commission on the proposed amount.
    Inspection   -> fee = flat assignment fee (the price is quoted later).
    Calling this again (e.g. after a failed payment) re-uses or recreates the pending fee: it is idempotent.
    """
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    if job.status != S.REQUESTED.value:
        raise ConflictError(f"A {job.status} job cannot be accepted")
    artisan = job.artisan
    if artisan.is_suspended or artisan.availability_status == AvailabilityStatus.UNAVAILABLE.value:
        raise ConflictError("You must be available and in good standing to accept jobs")

    if job.pricing_mode == PricingMode.FIXED_PRICE.value:
        payment_type = PaymentType.COMMISSION.value
        fee = payment_service.compute_commission(job.proposed_price)
        description = f"Platform commission on an agreed price of {job.proposed_price} FCFA"
        job.agreed_price = job.proposed_price          # the artisan confirmed they are OK with the amount
    else:
        payment_type = PaymentType.ASSIGNMENT_FEE.value
        fee = get_settings().inspection_assignment_fee
        description = "Flat assignment fee for a job that needs inspection before pricing"

    if not job.artisan_agreed:
        job.artisan_agreed = True
        _record(db, job, user, "TERMS_AGREED_BY_ARTISAN",
                {"pricing_mode": job.pricing_mode, "agreed_price": job.agreed_price, "fee": fee, "fee_type": payment_type})
    payment_service.initiate(db, job, user, payment_type, fee, description)
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


def pay_job(db: Session, user: User, job_id: uuid.UUID):
    """Customer pays the agreed price into escrow."""
    job = _lock_job(db, job_id)
    _require_party(job, user, "CUSTOMER")
    if job.status != S.ACCEPTED.value:
        raise ConflictError("You can pay once the artisan has accepted the job (and before work starts)")
    if job.agreed_price is None:
        raise ConflictError("No price has been agreed yet: approve the artisan's quote first")
    payment = payment_service.initiate(
        db, job, user, PaymentType.JOB_PAYMENT.value, job.agreed_price, "Customer payment held in escrow"
    )
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
        _record(db, job, user, "QUOTE_APPROVED", {"amount": job.agreed_price})
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
    _transition(db, job, S.CANCELLED.value, user, "JOB_CANCELLED", {"by": party, "reason": reason})
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
    _transition(db, job, outcome, admin, "DISPUTE_RESOLVED", {"notes": notes})
    if outcome == S.CANCELLED.value:
        payment_service.close_open_payments(db, job, admin, notes)
    db.commit()
    return job


def counterpart_phone(job: Job, user: User) -> str | None:
    """Phone numbers are shared only between the two parties, and only once the job is accepted."""
    if job.status in (S.REQUESTED.value, S.CANCELLED.value):
        return None
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
