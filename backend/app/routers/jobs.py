import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, Role, User
from app.models import PaymentStatus, PaymentType
from app.schemas import (
    CancelIn, DisputeIn, JobCreateIn, JobEventOut, JobOut, PaymentOut, QuoteIn, QuoteResponseIn, ReviewIn, ReviewOut,
)
from app.services import payment_providers
from app.config import get_settings
from app.security import rate_limit as limiter
from app.security.authentication import get_current_user
from app.security.permissions import require_roles
from app.services import job_service as svc
from app.services import reputation_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def payment_out(payment) -> PaymentOut:
    return PaymentOut(
        payment_id=payment.payment_id, job_id=payment.job_id, payment_type=payment.payment_type,
        amount=payment.amount, currency=payment.currency, status=payment.status, provider=payment.provider,
        description=payment.description, created_at=payment.created_at, settled_at=payment.settled_at,
        simulated=payment_providers.is_simulated(), notice=payment_providers.SIMULATION_NOTICE,
    )


def _escrow_status(job: Job) -> str:
    escrow = next((p for p in job.payments if p.payment_type == PaymentType.JOB_PAYMENT.value
                   and p.status != PaymentStatus.FAILED.value), None)
    if escrow is None:
        return "NOT_PAID"
    return {"PENDING": "AWAITING_PAYMENT", "SUCCEEDED": "HELD"}.get(escrow.status, escrow.status)


def to_out(job: Job, user: User) -> JobOut:
    visible = svc.payments_visible_to(job, user)
    due = next((p for p in visible if p.status == PaymentStatus.PENDING.value and p.payer_id == user.user_id), None)
    return JobOut(
        pricing_mode=job.pricing_mode, proposed_price=job.proposed_price, proposed_by=job.proposed_by,
        artisan_agreed=job.artisan_agreed, terms_agreed_at=job.terms_agreed_at,
        probation_ends_at=job.probation_ends_at, probation_active=svc.probation_active(job),
        can_cancel_freely=svc.can_cancel_freely(job), escrow_status=_escrow_status(job),
        payment_due=payment_out(due) if due else None, payments=[payment_out(p) for p in visible],
        counterpart_whatsapp_link=svc.counterpart_whatsapp_link(job, user),
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
    return to_out(svc.create_job(db, user, payload.request_id, payload.artisan_id, payload.proposed_price), user)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.get_job_for_party(db, user, job_id), user)


# NOTE: there is deliberately NO "set status" endpoint. Each action below is one controlled transition.
@router.post("/{job_id}/accept", response_model=JobOut)
def accept(job_id: uuid.UUID, user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.accept_job(db, user, job_id), user)


@router.post("/{job_id}/confirm-terms", response_model=JobOut)
def confirm_terms(job_id: uuid.UUID, user: User = Depends(require_roles(Role.ARTISAN)),
                  db: Session = Depends(get_db)) -> JobOut:
    """Fixed-price jobs: final confirmation after the cooling-off period. Creates the commission payment."""
    return to_out(svc.confirm_terms(db, user, job_id), user)


@router.post("/{job_id}/pay", response_model=PaymentOut, status_code=status.HTTP_201_CREATED, tags=["payments"])
def pay(job_id: uuid.UUID, user: User = Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=80)) -> PaymentOut:
    """Customer starts the payment of the agreed price (the amount comes from the server, never the request).
    Send an `Idempotency-Key` header: repeating it returns the same payment. Limited per phone number."""
    settings = get_settings()
    limiter.check(f"pay:{user.phone}", settings.pay_rate_limit_calls, settings.pay_rate_limit_window_seconds)
    return payment_out(svc.pay_job(db, user, job_id, idempotency_key))


@router.get("/{job_id}/payments", response_model=list[PaymentOut], tags=["payments"])
def list_payments(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = svc.get_job_for_party(db, user, job_id)
    return [payment_out(p) for p in svc.payments_visible_to(job, user)]


@router.post("/{job_id}/quote", response_model=JobOut)
def quote(job_id: uuid.UUID, payload: QuoteIn, user: User = Depends(require_roles(Role.ARTISAN)),
          db: Session = Depends(get_db)) -> JobOut:
    """Inspection jobs: the assigned artisan proposes a price after examining the problem."""
    return to_out(svc.propose_quote(db, user, job_id, payload.amount), user)


@router.post("/{job_id}/quote/respond", response_model=JobOut)
def respond_quote(job_id: uuid.UUID, payload: QuoteResponseIn, user: User = Depends(require_roles(Role.CUSTOMER)),
                  db: Session = Depends(get_db)) -> JobOut:
    return to_out(svc.respond_to_quote(db, user, job_id, payload.approve), user)


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
