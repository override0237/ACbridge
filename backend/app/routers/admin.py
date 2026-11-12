import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ArtisanProfile, Role, User
from app.schemas import DisputeResolutionIn, JobOut, RoleChangeIn, UserOut
from app.routers.jobs import to_out as job_to_out
from app.security.permissions import require_roles
from app.services import job_service

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


@router.post("/jobs/{job_id}/resolve-dispute", response_model=JobOut)
def resolve_dispute(job_id: uuid.UUID, payload: DisputeResolutionIn, admin: User = AdminUser,
                    db: Session = Depends(get_db)) -> JobOut:
    return job_to_out(job_service.resolve_dispute(db, admin, job_id, payload.outcome, payload.notes), admin)
