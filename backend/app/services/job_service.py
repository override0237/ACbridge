"""Job lifecycle as an explicit STATE MACHINE.

    REQUESTED --accept--> ACCEPTED --start--> IN_PROGRESS --first confirmation--> PENDING_CONFIRMATION
        |                    |                    |                                      |
        +--cancel--> CANCELLED <--cancel----------+                         second confirmation
                                                  |                                      v
                                                  +--dispute--> DISPUTED <--dispute-- COMPLETED
    DISPUTED --admin resolves--> CANCELLED | IN_PROGRESS            (COMPLETED and CANCELLED are final)

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

from app.errors import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError
from app.models import (
    ArtisanProfile, AvailabilityStatus, Job, JobEvent, JobStatus, RequestStatus, Role, ServiceRequest, User,
)
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
def create_job(db: Session, customer: User, request_id: uuid.UUID, artisan_id: uuid.UUID, agreed_price: int) -> Job:
    """Customer picks an artisan for their request. Eligibility is re-checked on the server."""
    service_request = db.scalar(
        select(ServiceRequest).where(ServiceRequest.request_id == request_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if service_request is None or service_request.customer_id != customer.user_id:
        raise NotFoundError("Service request not found")
    if service_request.status != RequestStatus.OPEN.value:
        raise ConflictError("This request already has an artisan assigned or is closed")
    reason = is_eligible_for_request(db, service_request, artisan_id)
    if reason is not None:
        raise BadRequestError(f"This artisan cannot take this request ({reason})")

    job = Job(request_id=request_id, artisan_id=artisan_id, agreed_price=agreed_price, status=S.REQUESTED.value)
    db.add(job)
    service_request.status = RequestStatus.MATCHED.value
    try:
        db.flush()
    except IntegrityError:  # UNIQUE(request_id): another request won the race
        db.rollback()
        raise ConflictError("This request already has a job")
    _record(db, job, customer, "JOB_REQUESTED", {"agreed_price": agreed_price})
    db.commit()
    return job


def accept_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    artisan = job.artisan
    if artisan.is_suspended or artisan.availability_status == AvailabilityStatus.UNAVAILABLE.value:
        raise ConflictError("You must be available and in good standing to accept jobs")
    _transition(db, job, S.ACCEPTED.value, user, "JOB_ACCEPTED")
    db.commit()
    return job


def start_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = _lock_job(db, job_id)
    _require_party(job, user, "ARTISAN")
    _transition(db, job, S.IN_PROGRESS.value, user, "JOB_STARTED")
    db.commit()
    return job


def cancel_job(db: Session, user: User, job_id: uuid.UUID, reason: str | None) -> Job:
    job = _lock_job(db, job_id)
    party = party_of(job, user)
    if party is None:
        raise PermissionDeniedError("You are not a party to this job")
    _transition(db, job, S.CANCELLED.value, user, "JOB_CANCELLED", {"by": party, "reason": reason})
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
