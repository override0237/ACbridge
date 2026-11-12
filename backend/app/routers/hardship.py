"""Hardship claims: proven death / serious accident or illness -> job cancelled, fees and escrow refunded."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import HardshipClaim, Role, User
from app.schemas import HardshipClaimIn, HardshipClaimOut, HardshipDecisionIn
from app.security.authentication import get_current_user
from app.security.permissions import require_roles
from app.security.rate_limit import rate_limit
from app.services import hardship_service as svc

router = APIRouter(tags=["hardship claims"])

REQUIRED_PROOF = {
    "DEATH": "A death certificate",
    "ACCIDENT_OR_SERIOUS_ILLNESS": "Medical records or a doctor's certificate",
}


def to_out(claim: HardshipClaim) -> HardshipClaimOut:
    return HardshipClaimOut(
        claim_id=claim.claim_id, job_id=claim.job_id, kind=claim.kind, affected_party=claim.affected_party,
        description=claim.description, status=claim.status, has_document=bool(claim.document_path),
        decision_notes=claim.decision_notes, created_at=claim.created_at, decided_at=claim.decided_at,
        required_proof=REQUIRED_PROOF[claim.kind],
    )


@router.post("/jobs/{job_id}/hardship-claims", response_model=HardshipClaimOut, status_code=status.HTTP_201_CREATED)
def file_claim(job_id: uuid.UUID, payload: HardshipClaimIn,
               user: User = Depends(require_roles(Role.CUSTOMER, Role.ARTISAN)), db: Session = Depends(get_db)):
    """A party to the job reports a death or serious accident/illness. Then upload the proof document."""
    return to_out(svc.file_claim(db, user, job_id, payload.kind, payload.affected_party, payload.description))


@router.post("/hardship-claims/{claim_id}/document", response_model=HardshipClaimOut,
             dependencies=[Depends(rate_limit("upload", 20, 3600))])
async def upload_document(claim_id: uuid.UUID, file: UploadFile = File(...), user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    data = await file.read(get_settings().max_evidence_bytes + 1)
    return to_out(svc.attach_document(db, user, claim_id, file.filename or "", data))


@router.get("/hardship-claims/{claim_id}", response_model=HardshipClaimOut)
def get_claim(claim_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_out(svc.get_claim_for(db, user, claim_id))


@router.get("/hardship-claims/{claim_id}/document")
def download_document(claim_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claim = svc.get_claim_for(db, user, claim_id)
    if not claim.document_path or not Path(claim.document_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document uploaded")
    return FileResponse(claim.document_path, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/admin/hardship-claims", response_model=list[HardshipClaimOut])
def pending_claims(_: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [to_out(c) for c in svc.list_pending(db)]


@router.post("/admin/hardship-claims/{claim_id}/decision", response_model=HardshipClaimOut)
def decide_claim(claim_id: uuid.UUID, payload: HardshipDecisionIn, admin: User = Depends(require_roles(Role.ADMIN)),
                 db: Session = Depends(get_db)):
    return to_out(svc.decide(db, admin, claim_id, payload.approve, payload.notes))
