import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import CheckStatus, Role, User, VerificationCheck
from app.schemas import VerificationDecisionIn, VerificationIn, VerificationOut
from app.security.permissions import require_roles
from app.security.rate_limit import rate_limit
from app.security.authentication import get_current_user
from app.services import verification_service as svc

router = APIRouter(prefix="/verifications", tags=["verification"])


def to_out(db: Session, check: VerificationCheck) -> VerificationOut:
    return VerificationOut(
        check_id=check.check_id, artisan_id=check.artisan_id, skill_id=check.skill_id,
        verifier_id=check.verifier_id, check_type=check.check_type, status=check.status,
        evidence_description=check.evidence_description, has_evidence_file=bool(check.evidence_file_path),
        decision_notes=check.decision_notes, created_at=check.created_at, reviewed_at=check.reviewed_at,
        endorsement_count=svc.count_endorsements(db, check.artisan_id),
        review_signals=svc.review_signals(db, check.artisan),
        simulated=get_settings().verification_mode.upper() == "SIMULATED", notice=svc.SIMULATION_NOTICE,
    )


def _visible_check(db: Session, user: User, check_id: uuid.UUID) -> VerificationCheck:
    """Evidence is private: only the owning artisan, verifiers and admins may see a check."""
    check = db.get(VerificationCheck, check_id)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification request not found")
    is_owner = check.artisan.user_id == user.user_id
    if not is_owner and user.role not in (Role.VERIFIER.value, Role.ADMIN.value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification request not found")
    return check


@router.post("", response_model=VerificationOut, status_code=status.HTTP_201_CREATED)
def submit(payload: VerificationIn, user: User = Depends(require_roles(Role.ARTISAN)),
           db: Session = Depends(get_db)) -> VerificationOut:
    check = svc.submit_check(db, user, payload.check_type, payload.skill_id, payload.evidence_description)
    return to_out(db, check)


@router.get("", response_model=list[VerificationOut])
def review_queue(
    status_filter: CheckStatus = CheckStatus.PENDING, limit: int = 50,
    _: User = Depends(require_roles(Role.VERIFIER, Role.ADMIN)), db: Session = Depends(get_db),
) -> list[VerificationOut]:
    """Verifier work queue (oldest first)."""
    checks = db.scalars(
        select(VerificationCheck).where(VerificationCheck.status == status_filter.value)
        .order_by(VerificationCheck.created_at).limit(min(max(limit, 1), 100))
    )
    return [to_out(db, c) for c in checks]


@router.get("/{verification_id}", response_model=VerificationOut)
def get_verification(verification_id: uuid.UUID, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> VerificationOut:
    return to_out(db, _visible_check(db, user, verification_id))


@router.post("/{verification_id}/decision", response_model=VerificationOut)
def decision(verification_id: uuid.UUID, payload: VerificationDecisionIn,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VerificationOut:
    # Role/ownership/conflict-of-interest rules live in the service so they are unit-testable.
    check = svc.decide(db, user, verification_id, payload.decision, payload.decision_notes)
    return to_out(db, check)


@router.post("/{verification_id}/evidence", response_model=VerificationOut,
             dependencies=[Depends(rate_limit("upload", 20, 3600))])
async def upload_evidence(
    verification_id: uuid.UUID, file: UploadFile = File(...),
    user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db),
) -> VerificationOut:
    max_bytes = get_settings().max_evidence_bytes
    data = await file.read(max_bytes + 1)  # never buffer more than the limit
    check = svc.save_evidence_file(db, user, verification_id, file.filename or "", data)
    return to_out(db, check)


@router.get("/{verification_id}/evidence")
def download_evidence(verification_id: uuid.UUID, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> FileResponse:
    check = _visible_check(db, user, verification_id)
    if not check.evidence_file_path or not Path(check.evidence_file_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evidence file uploaded")
    return FileResponse(check.evidence_file_path, headers={"X-Content-Type-Options": "nosniff"})
