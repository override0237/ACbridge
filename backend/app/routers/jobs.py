import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, Role, User
from app.schemas import CancelIn, DisputeIn, JobCreateIn, JobEventOut, JobOut, ReviewIn, ReviewOut
from app.security.authentication import get_current_user
from app.security.permissions import require_roles
from app.services import job_service as svc
from app.services import reputation_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def to_out(job: Job, user: User) -> JobOut:
    return JobOut(
        job_id=job.job_id, request_id=job.request_id, artisan_id=job.artisan_id,
        customer_id=job.request.customer_id, agreed_price=job.agreed_price, status=job.status,
        customer_confirmed=job.customer_confirmed, artisan_confirmed=job.artisan_confirmed,
        created_at=job.created_at, completed_at=job.completed_at,
        counterpart_phone=svc.counterpart_phone(job, user),
        events=[JobEventOut.model_validate(e) for e in job.events],
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreateIn, user: User = Depends(require_roles(Role.CUSTOMER)),
               db: Session = Depends(get_db)) -> JobOut:
    """Customer chooses one artisan from the matches; creates the job in REQUESTED state."""
    return to_out(svc.create_job(db, user, payload.request_id, payload.artisan_id, payload.agreed_price), user)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.get_job_for_party(db, user, job_id), user)


# NOTE: there is deliberately NO "set status" endpoint. Each action below is one controlled transition.
@router.post("/{job_id}/accept", response_model=JobOut)
def accept(job_id: uuid.UUID, user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.accept_job(db, user, job_id), user)


@router.post("/{job_id}/start", response_model=JobOut)
def start(job_id: uuid.UUID, user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.start_job(db, user, job_id), user)


@router.post("/{job_id}/confirm-completion", response_model=JobOut)
def confirm_completion(
    job_id: uuid.UUID, user: User = Depends(require_roles(Role.CUSTOMER, Role.ARTISAN)), db: Session = Depends(get_db)
) -> JobOut:
    return to_out(svc.confirm_completion(db, user, job_id), user)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: uuid.UUID, payload: CancelIn, user: User = Depends(require_roles(Role.CUSTOMER, Role.ARTISAN)),
           db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.cancel_job(db, user, job_id, payload.reason), user)


@router.post("/{job_id}/dispute", response_model=JobOut)
def dispute(job_id: uuid.UUID, payload: DisputeIn, user: User = Depends(require_roles(Role.CUSTOMER, Role.ARTISAN)),
            db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.open_dispute(db, user, job_id, payload.reason), user)


@router.post("/{job_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED, tags=["reviews"])
def review(job_id: uuid.UUID, payload: ReviewIn, user: User = Depends(require_roles(Role.CUSTOMER)),
           db: Session = Depends(get_db)):
    return reputation_service.create_review(db, user, job_id, payload.rating, payload.comment)
