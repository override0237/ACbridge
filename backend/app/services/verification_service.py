"""Endorsements and the verification workflow.

Workflow (state machine):
    PENDING --> UNDER_REVIEW --> APPROVED | REJECTED | NEEDS_MORE_EVIDENCE
    NEEDS_MORE_EVIDENCE --(artisan uploads new evidence)--> PENDING

Three independent dimensions are never merged:
  * identity verification  -> an approved IDENTITY check
  * skill verification     -> artisan_skills.verification_status (one per skill!)
  * work reputation        -> reputation_service

HONESTY: verification in this MVP is SIMULATED. A verifier clicking "approve" here is a stand-in for
a real-world assessment (ID inspection, practical test). The API labels every verification so.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError
from app.models import (
    ArtisanProfile, ArtisanSkill, CheckStatus, CheckType, Endorsement, Role, SkillVerificationStatus, User,
    VerificationCheck,
)

SIMULATION_NOTICE = (
    "SIMULATED verification: no real-world identity or skill assessment has been performed. "
    "This record only demonstrates the workflow."
)

# Allowed transitions of a verification check.
CHECK_TRANSITIONS: dict[str, frozenset[str]] = {
    CheckStatus.PENDING.value: frozenset({CheckStatus.UNDER_REVIEW.value}),
    CheckStatus.UNDER_REVIEW.value: frozenset({
        CheckStatus.APPROVED.value, CheckStatus.REJECTED.value, CheckStatus.NEEDS_MORE_EVIDENCE.value,
    }),
    CheckStatus.NEEDS_MORE_EVIDENCE.value: frozenset({CheckStatus.PENDING.value}),
    CheckStatus.APPROVED.value: frozenset(),
    CheckStatus.REJECTED.value: frozenset(),
}
ACTIVE_STATUSES = (CheckStatus.PENDING.value, CheckStatus.UNDER_REVIEW.value)


def get_artisan_or_404(db: Session, artisan_id: uuid.UUID) -> ArtisanProfile:
    artisan = db.get(ArtisanProfile, artisan_id)
    if artisan is None:
        raise NotFoundError("Artisan not found")
    return artisan


def count_endorsements(db: Session, artisan_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Endorsement).where(Endorsement.artisan_id == artisan_id)) or 0


def is_identity_verified(db: Session, artisan_id: uuid.UUID) -> bool:
    return db.scalar(
        select(func.count()).select_from(VerificationCheck).where(
            VerificationCheck.artisan_id == artisan_id,
            VerificationCheck.check_type == CheckType.IDENTITY.value,
            VerificationCheck.status == CheckStatus.APPROVED.value,
        )
    ) > 0


# ----------------------------------------------------------------------------- endorsements
def add_endorsement(db: Session, endorser: User, artisan_id: uuid.UUID, evidence: str) -> Endorsement:
    artisan = get_artisan_or_404(db, artisan_id)
    if artisan.user_id == endorser.user_id:
        raise PermissionDeniedError("You cannot endorse yourself")
    if endorser.role == Role.ADMIN.value:
        raise PermissionDeniedError("Platform administrators cannot endorse artisans")
    endorsement = Endorsement(artisan_id=artisan_id, endorser_id=endorser.user_id, evidence_description=evidence)
    db.add(endorsement)
    try:
        db.commit()  # UNIQUE(artisan_id, endorser_id) is the real duplicate guard (race-safe)
    except IntegrityError:
        db.rollback()
        raise ConflictError("You have already endorsed this artisan")
    return endorsement


# ----------------------------------------------------------------------------- submitting a check
def submit_check(
    db: Session, user: User, check_type: str, skill_id: uuid.UUID | None, evidence: str
) -> VerificationCheck:
    artisan = user.artisan_profile
    if artisan is None:
        raise BadRequestError("Create an artisan profile before requesting verification")

    artisan_skill = None
    if check_type == CheckType.SKILL.value:
        if skill_id is None:
            raise BadRequestError("skill_id is required for SKILL verification")
        artisan_skill = db.get(ArtisanSkill, (artisan.artisan_id, skill_id))
        if artisan_skill is None:
            raise BadRequestError("Add this skill to your profile before requesting its verification")
        if artisan_skill.verification_status == SkillVerificationStatus.VERIFIED.value:
            raise ConflictError("This skill is already verified")
    else:
        skill_id = None
        if is_identity_verified(db, artisan.artisan_id):
            raise ConflictError("Your identity is already verified")

    duplicate = db.scalar(
        select(VerificationCheck.check_id).where(
            VerificationCheck.artisan_id == artisan.artisan_id,
            VerificationCheck.check_type == check_type,
            VerificationCheck.skill_id.is_(skill_id) if skill_id is None else VerificationCheck.skill_id == skill_id,
            VerificationCheck.status.in_(ACTIVE_STATUSES + (CheckStatus.NEEDS_MORE_EVIDENCE.value,)),
        )
    )
    if duplicate is not None:
        raise ConflictError("A verification request for this item is already open")

    check = VerificationCheck(
        artisan_id=artisan.artisan_id, skill_id=skill_id, check_type=check_type, evidence_description=evidence
    )
    db.add(check)
    if artisan_skill is not None:
        artisan_skill.verification_status = SkillVerificationStatus.PENDING.value
    db.commit()
    return check


# ----------------------------------------------------------------------------- verifier decision
def decide(
    db: Session, verifier: User, check_id: uuid.UUID, decision: str, notes: str | None
) -> VerificationCheck:
    # Row lock: two verifiers cannot decide the same check at the same moment.
    check = db.scalar(
        select(VerificationCheck).where(VerificationCheck.check_id == check_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if check is None:
        raise NotFoundError("Verification request not found")
    artisan = check.artisan

    # --- separation of duties (the anti-fraud heart of this module) ---
    if verifier.role != Role.VERIFIER.value:
        raise PermissionDeniedError("Only authorised verifiers can decide verification requests")
    if artisan.user_id == verifier.user_id:
        raise PermissionDeniedError("You cannot verify your own profile")
    endorsed_by_verifier = db.scalar(
        select(func.count()).select_from(Endorsement).where(
            Endorsement.artisan_id == artisan.artisan_id, Endorsement.endorser_id == verifier.user_id
        )
    )
    if endorsed_by_verifier:
        raise PermissionDeniedError("Conflict of interest: you endorsed this artisan, so you cannot verify them")

    if decision not in CHECK_TRANSITIONS[check.status]:
        raise ConflictError(f"Cannot move a verification from {check.status} to {decision}")
    if check.status == CheckStatus.UNDER_REVIEW.value and check.verifier_id != verifier.user_id:
        raise PermissionDeniedError("This request is being reviewed by another verifier")

    if decision == CheckStatus.APPROVED.value and check.check_type == CheckType.SKILL.value:
        needed = get_settings().min_endorsements_for_skill_verification
        have = count_endorsements(db, artisan.artisan_id)
        if have < needed:
            raise ConflictError(
                f"Cannot approve: {have} community endorsement(s) on record, {needed} required"
            )

    check.status = decision
    if decision == CheckStatus.UNDER_REVIEW.value:
        check.verifier_id = verifier.user_id  # the verifier "claims" the check
    else:
        check.decision_notes = notes
        check.reviewed_at = datetime.now(timezone.utc)

    _sync_skill_status(db, check)
    db.commit()
    return check


def _sync_skill_status(db: Session, check: VerificationCheck) -> None:
    """Mirror the check outcome onto the specific skill (identity checks never touch skills)."""
    if check.check_type != CheckType.SKILL.value:
        return
    artisan_skill = db.get(ArtisanSkill, (check.artisan_id, check.skill_id))
    if artisan_skill is None:
        return
    mapping = {
        CheckStatus.APPROVED.value: SkillVerificationStatus.VERIFIED.value,
        CheckStatus.REJECTED.value: SkillVerificationStatus.REJECTED.value,
    }
    artisan_skill.verification_status = mapping.get(check.status, SkillVerificationStatus.PENDING.value)


# ----------------------------------------------------------------------------- evidence upload
_ALLOWED_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",), ".pdf": (b"%PDF-",),
}


def save_evidence_file(db: Session, user: User, check_id: uuid.UUID, filename: str, data: bytes) -> VerificationCheck:
    settings = get_settings()
    check = db.get(VerificationCheck, check_id)
    if check is None or check.artisan.user_id != user.user_id:
        raise NotFoundError("Verification request not found")  # don't reveal other people's records
    if check.status not in (CheckStatus.PENDING.value, CheckStatus.NEEDS_MORE_EVIDENCE.value):
        raise ConflictError("Evidence can only be added while the request is PENDING or NEEDS_MORE_EVIDENCE")
    if len(data) == 0 or len(data) > settings.max_evidence_bytes:
        raise BadRequestError(f"File must be between 1 byte and {settings.max_evidence_bytes} bytes")

    extension = Path(filename or "").suffix.lower()
    signatures = _ALLOWED_SIGNATURES.get(extension)
    # Check the extension AND the real file header: a renamed .exe is rejected.
    if signatures is None or not data.startswith(signatures):
        raise BadRequestError("Only genuine JPG, PNG or PDF files are accepted")

    # Server-generated name: the client-supplied filename is never used on disk (blocks path traversal).
    folder = Path(settings.evidence_upload_dir) / str(check.check_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}{extension}"
    stored.write_bytes(data)
    check.evidence_file_path = str(stored)
    if check.status == CheckStatus.NEEDS_MORE_EVIDENCE.value:
        check.status = CheckStatus.PENDING.value
        check.verifier_id = None
    db.commit()
    return check


# ----------------------------------------------------------------------------- hints for human verifiers
def review_signals(db: Session, artisan: ArtisanProfile) -> list[str]:
    """Patterns worth a HUMAN look. They are hints, not proof, and never block or accuse anyone."""
    signals: list[str] = []
    endorsers = db.execute(
        select(User.created_at).join(Endorsement, Endorsement.endorser_id == User.user_id)
        .where(Endorsement.artisan_id == artisan.artisan_id)
    ).scalars().all()
    if not endorsers:
        signals.append("No community endorsements yet")
    owner_created = artisan.user.created_at
    fresh = 0
    for created in endorsers:
        a, b = _aware(created), _aware(owner_created)
        if abs((a - b).total_seconds()) < 24 * 3600:
            fresh += 1
    if fresh:
        signals.append(
            f"{fresh} endorser account(s) created within 24h of the artisan account - "
            "worth confirming they are independent (this is common for genuine neighbours too)"
        )
    return signals


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
