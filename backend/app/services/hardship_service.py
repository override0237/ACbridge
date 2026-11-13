"""Hardship claims: the only way platform fees and escrow are refunded after a job is confirmed.

Eligible: the DEATH, or a serious ACCIDENT / ILLNESS, of the customer or the artisan.
Proof is mandatory: a death certificate or medical records (JPG/PNG/PDF) uploaded by the claimant and
checked by an administrator, who approves or rejects. Approval cancels the job and refunds fees + escrow.
Documents are private (claimant and admins only). Nothing is refunded automatically.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError
from app.models import ClaimStatus, HardshipClaim, Job, JobEvent, JobStatus, Role, User
from app.services import file_storage, job_service

FINAL_STATES = (JobStatus.COMPLETED.value, JobStatus.CANCELLED.value)


def _event(db: Session, job_id: uuid.UUID, actor_id: uuid.UUID, event_type: str, metadata: dict) -> None:
    db.add(JobEvent(job_id=job_id, actor_id=actor_id, event_type=event_type, event_metadata=metadata))


def file_claim(db: Session, user: User, job_id: uuid.UUID, kind: str, affected_party: str, description: str) -> HardshipClaim:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    if job_service.party_of(job, user) is None:       # admins cannot file; only the two parties
        raise PermissionDeniedError("You are not a party to this job")
    if job.status in FINAL_STATES:
        raise ConflictError("This job is already finished")
    claim = HardshipClaim(job_id=job_id, claimant_id=user.user_id, kind=kind, affected_party=affected_party,
                          description=description)
    db.add(claim)
    try:
        db.flush()   # partial unique index: one open claim per job
    except IntegrityError:
        db.rollback()
        raise ConflictError("A hardship claim for this job is already being reviewed")
    _event(db, job_id, user.user_id, "HARDSHIP_CLAIM_FILED",
           {"claim_id": str(claim.claim_id), "kind": kind, "affected_party": affected_party})
    db.commit()
    return claim


def get_claim_for(db: Session, user: User, claim_id: uuid.UUID) -> HardshipClaim:
    claim = db.get(HardshipClaim, claim_id)
    if claim is None or (claim.claimant_id != user.user_id and user.role != Role.ADMIN.value):
        raise NotFoundError("Hardship claim not found")   # other people's claims stay invisible
    return claim


def attach_document(db: Session, user: User, claim_id: uuid.UUID, filename: str, data: bytes) -> HardshipClaim:
    claim = db.get(HardshipClaim, claim_id)
    if claim is None or claim.claimant_id != user.user_id:
        raise NotFoundError("Hardship claim not found")
    if claim.status != ClaimStatus.PENDING.value:
        raise ConflictError("This claim has already been decided")
    claim.document_path = file_storage.store_private_file("hardship", claim.claim_id, filename, data)
    db.commit()
    return claim


def decide(db: Session, admin: User, claim_id: uuid.UUID, approve: bool, notes: str) -> HardshipClaim:
    if admin.role != Role.ADMIN.value:
        raise PermissionDeniedError("Only administrators can decide hardship claims")
    claim = db.scalar(
        select(HardshipClaim).where(HardshipClaim.claim_id == claim_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if claim is None:
        raise NotFoundError("Hardship claim not found")
    if claim.status != ClaimStatus.PENDING.value:
        raise ConflictError("This claim has already been decided")
    if approve:
        if not claim.document_path:
            raise BadRequestError("A supporting document (death certificate or medical records) is required to approve")
        job_service.cancel_for_hardship(db, admin, claim.job_id, claim.claim_id, notes)
    claim.status = ClaimStatus.APPROVED.value if approve else ClaimStatus.REJECTED.value
    claim.decided_by = admin.user_id
    claim.decision_notes = notes
    claim.decided_at = datetime.now(timezone.utc)
    _event(db, claim.job_id, admin.user_id, "HARDSHIP_CLAIM_APPROVED" if approve else "HARDSHIP_CLAIM_REJECTED",
           {"claim_id": str(claim.claim_id)})
    db.commit()
    return claim


def list_pending(db: Session, limit: int = 50) -> list[HardshipClaim]:
    return list(db.scalars(
        select(HardshipClaim).where(HardshipClaim.status == ClaimStatus.PENDING.value)
        .order_by(HardshipClaim.created_at).limit(limit)
    ))
