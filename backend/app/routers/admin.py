import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ArtisanProfile, Role, User
from app.schemas import (
    DisputeResolutionIn, JobOut, RevokeVouchIn, RoleChangeIn, TradeGroupAdminOut, TradeGroupIn, UserOut,
)
from app.routers.jobs import to_out as job_to_out
from app.security.permissions import require_roles
from app.config import get_settings
from app.models import TradeGroup
from app.routers.trade_groups import vouch_out
from app.services import email_service, job_service, payment_providers
from app.services import trade_group_service

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUser = Depends(require_roles(Role.ADMIN))


@router.post("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: uuid.UUID, payload: RoleChangeIn, admin: User = AdminUser, db: Session = Depends(get_db)) -> User:
    """The ONLY way to create verifiers/admins (registration cannot self-assign them)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.user_id == admin.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Administrators cannot change their own role")
    user.role = payload.role
    db.commit()
    return user


def _set_suspended(db: Session, artisan_id: uuid.UUID, value: bool) -> dict:
    artisan = db.get(ArtisanProfile, artisan_id)
    if artisan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artisan not found")
    artisan.is_suspended = value
    db.commit()
    return {"artisan_id": artisan_id, "is_suspended": value}


@router.post("/artisans/{artisan_id}/suspend")
def suspend(artisan_id: uuid.UUID, _: User = AdminUser, db: Session = Depends(get_db)) -> dict:
    return _set_suspended(db, artisan_id, True)


@router.post("/artisans/{artisan_id}/unsuspend")
def unsuspend(artisan_id: uuid.UUID, _: User = AdminUser, db: Session = Depends(get_db)) -> dict:
    return _set_suspended(db, artisan_id, False)


@router.post("/jobs/{job_id}/skip-probation", response_model=JobOut)
def skip_probation(job_id: uuid.UUID, admin: User = AdminUser, db: Session = Depends(get_db)) -> JobOut:
    """DEMO ONLY: ends the cooling-off period immediately. Exists only while the payment provider is simulated."""
    if not payment_providers.is_simulated():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return job_to_out(job_service.skip_probation_simulated(db, admin, job_id), admin)


@router.post("/jobs/{job_id}/resolve-dispute", response_model=JobOut)
def resolve_dispute(job_id: uuid.UUID, payload: DisputeResolutionIn, admin: User = AdminUser,
                    db: Session = Depends(get_db)) -> JobOut:
    return job_to_out(job_service.resolve_dispute(db, admin, job_id, payload.outcome, payload.notes), admin)


# ----------------------------------------------------------------------------- trade groups
def _group_out(db: Session, group: TradeGroup, email_sent: bool | None = None) -> TradeGroupAdminOut:
    counts = trade_group_service.group_vouch_counts(db).get(group.group_id, {})
    return TradeGroupAdminOut(
        group_id=group.group_id, name=group.name, email=group.email, description=group.description,
        status=group.status, email_verified=group.email_verified_at is not None, created_at=group.created_at,
        confirmed_vouches=counts.get("CONFIRMED", 0), pending_vouches=counts.get("PENDING_CONFIRMATION", 0),
        email_status=None if email_sent is None else ("SENT" if email_sent else "FAILED"),
    )


@router.post("/trade-groups", response_model=TradeGroupAdminOut, status_code=status.HTTP_201_CREATED)
def register_trade_group(payload: TradeGroupIn, admin: User = AdminUser, db: Session = Depends(get_db)):
    """Register a trade group you have contacted. It e-mails the group a link; the group is usable only after
    someone at that address confirms it."""
    group, sent = trade_group_service.create_group(db, admin, payload.name, payload.email, payload.description)
    return _group_out(db, group, sent)


@router.get("/trade-groups", response_model=list[TradeGroupAdminOut])
def list_trade_groups(_: User = AdminUser, db: Session = Depends(get_db)):
    from sqlalchemy import select
    return [_group_out(db, g) for g in db.scalars(select(TradeGroup).order_by(TradeGroup.name))]


@router.post("/trade-groups/{group_id}/resend-verification", response_model=TradeGroupAdminOut)
def resend_group_verification(group_id: uuid.UUID, admin: User = AdminUser, db: Session = Depends(get_db)):
    sent = trade_group_service.resend_group_verification(db, admin, group_id)
    return _group_out(db, db.get(TradeGroup, group_id), sent)


@router.post("/trade-groups/{group_id}/suspend", response_model=TradeGroupAdminOut)
def suspend_group(group_id: uuid.UUID, admin: User = AdminUser, db: Session = Depends(get_db)):
    return _group_out(db, trade_group_service.set_group_suspended(db, admin, group_id, True))


@router.post("/trade-groups/{group_id}/activate", response_model=TradeGroupAdminOut)
def activate_group(group_id: uuid.UUID, admin: User = AdminUser, db: Session = Depends(get_db)):
    return _group_out(db, trade_group_service.set_group_suspended(db, admin, group_id, False))


@router.post("/trade-group-vouches/{vouch_id}/revoke")
def revoke_vouch(vouch_id: uuid.UUID, payload: RevokeVouchIn, admin: User = AdminUser, db: Session = Depends(get_db)):
    """Withdraw a confirmed vouch (e.g. the group vouched fraudulently). The skill is unverified again unless
    another approved verification still backs it."""
    return vouch_out(trade_group_service.revoke(db, admin, vouch_id, payload.notes))


@router.get("/dev/outbox")
def dev_outbox(_: User = AdminUser) -> list[dict]:
    """DEMO ONLY: read the simulated e-mails (console mode). Disabled whenever real e-mail is configured."""
    if get_settings().email_mode != "console":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return [{"to": m.to, "subject": m.subject, "body": m.body} for m in email_service.OUTBOX]
