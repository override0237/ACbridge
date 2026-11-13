"""Trade-group vouching.

Why it is trustworthy
  * A trade group exists only after an ADMIN registered it AND someone with access to the group's e-mail
    address clicked a one-time link (so we really "got in contact" with the group).
  * Every vouch needs its OWN e-mail confirmation: the platform e-mails the group a single-use link naming the
    artisan and skill. Vouching for a second artisan means a second e-mail and a second confirmation.
  * Links carry a 256-bit random token; only its SHA-256 is stored; the token is cleared once used and expires
    after VOUCH_TOKEN_TTL_HOURS. Opening the link (GET) changes nothing: only an explicit POST decides, so mail
    scanners that pre-fetch links cannot confirm by accident.
  * One CONFIRMED vouch from a vetted group automatically verifies that skill (TRADE_GROUP_VOUCH_AUTO_VERIFIES).
  * Individuals may vouch for ONE artisan only (database constraint on endorsements); groups for many.
  * An admin can revoke a confirmed vouch; the skill drops back to UNVERIFIED unless another approved
    verification still backs it.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import BadRequestError, ConflictError, GoneError, NotFoundError, PermissionDeniedError
from app.models import (
    ArtisanProfile, ArtisanSkill, CheckStatus, CheckType, Role, SkillVerificationStatus, TradeGroup,
    TradeGroupStatus, TradeGroupVouch, User, VerificationCheck, VouchStatus,
)
from app.services import email_service

OPEN_CHECK_STATUSES = (CheckStatus.PENDING.value, CheckStatus.UNDER_REVIEW.value, CheckStatus.NEEDS_MORE_EVIDENCE.value)


# ----------------------------------------------------------------------------- tokens
def _new_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _expiry() -> datetime:
    return _now() + timedelta(hours=get_settings().vouch_token_ttl_hours)


def _confirm_url(path: str, raw_token: str) -> str:
    return f"{get_settings().public_api_url.rstrip('/')}{path}?token={raw_token}"


# ----------------------------------------------------------------------------- trade group onboarding
def create_group(db: Session, admin: User, name: str, email: str, description: str | None) -> tuple[TradeGroup, bool]:
    if admin.role != Role.ADMIN.value:
        raise PermissionDeniedError("Only administrators can register trade groups")
    raw, hashed = _new_token()
    group = TradeGroup(name=name.strip(), email=email.strip().lower(), description=description, created_by=admin.user_id,
                       verification_token_hash=hashed, verification_expires_at=_expiry())
    db.add(group)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("A trade group with this name or e-mail address already exists")
    return group, _send_group_verification(group, raw)


def _send_group_verification(group: TradeGroup, raw_token: str) -> bool:
    link = _confirm_url("/trade-groups/verify-page", raw_token)
    return email_service.send_email(
        group.email, "Confirm your trade group on ACbridge",
        f"Hello,\n\n{group.name} has been registered on ACbridge, a platform that helps customers find trusted "
        "artisans. Once confirmed, artisans can ask your group to vouch for their skills. You will be e-mailed "
        "each time, and nothing is confirmed without your approval.\n\n"
        f"To confirm that this address belongs to {group.name}, open this link:\n{link}\n\n"
        "If you did not expect this message, ignore it.\n",
    )


def resend_group_verification(db: Session, admin: User, group_id: uuid.UUID) -> bool:
    group = _get_group(db, group_id)
    if group.status != TradeGroupStatus.PENDING_EMAIL_VERIFICATION.value:
        raise ConflictError("This trade group's e-mail is already verified")
    raw, hashed = _new_token()
    group.verification_token_hash, group.verification_expires_at = hashed, _expiry()
    db.commit()
    return _send_group_verification(group, raw)


def verify_group_email(db: Session, raw_token: str) -> TradeGroup:
    group = db.scalar(select(TradeGroup).where(TradeGroup.verification_token_hash == _hash(raw_token)).with_for_update())
    if group is None:
        raise NotFoundError("This link is invalid or has already been used")
    if _aware(group.verification_expires_at) < _now():
        raise GoneError("This link has expired. Ask the ACbridge administrator to send a new one")
    group.status = TradeGroupStatus.ACTIVE.value
    group.email_verified_at = _now()
    group.verification_token_hash = None   # single use
    db.commit()
    return group


def group_for_verification_token(db: Session, raw_token: str) -> TradeGroup | None:
    """Read-only lookup for the verification page (changes nothing)."""
    return db.scalar(select(TradeGroup).where(TradeGroup.verification_token_hash == _hash(raw_token)))


def set_group_suspended(db: Session, admin: User, group_id: uuid.UUID, suspended: bool) -> TradeGroup:
    group = _get_group(db, group_id)
    if suspended:
        group.status = TradeGroupStatus.SUSPENDED.value
    else:
        if group.email_verified_at is None:
            raise ConflictError("Verify the group's e-mail before activating it")
        group.status = TradeGroupStatus.ACTIVE.value
    db.commit()
    return group


def _get_group(db: Session, group_id: uuid.UUID) -> TradeGroup:
    group = db.get(TradeGroup, group_id)
    if group is None:
        raise NotFoundError("Trade group not found")
    return group


def list_active_groups(db: Session) -> list[TradeGroup]:
    return list(db.scalars(select(TradeGroup).where(TradeGroup.status == TradeGroupStatus.ACTIVE.value)
                           .order_by(TradeGroup.name)))


def group_vouch_counts(db: Session) -> dict[uuid.UUID, dict[str, int]]:
    rows = db.execute(select(TradeGroupVouch.group_id, TradeGroupVouch.status, func.count())
                      .group_by(TradeGroupVouch.group_id, TradeGroupVouch.status))
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for group_id, status, count in rows:
        counts.setdefault(group_id, {})[status] = count
    return counts


# ----------------------------------------------------------------------------- requesting a vouch
def request_vouch(db: Session, user: User, artisan_id: uuid.UUID, group_id: uuid.UUID, skill_id: uuid.UUID,
                  note: str | None) -> tuple[TradeGroupVouch, bool]:
    artisan = db.get(ArtisanProfile, artisan_id)
    if artisan is None or artisan.user_id != user.user_id:
        raise PermissionDeniedError("You can only request vouches for your own profile")
    group = db.get(TradeGroup, group_id)
    if group is None or group.status != TradeGroupStatus.ACTIVE.value:
        raise NotFoundError("Trade group not found or not active")
    artisan_skill = db.get(ArtisanSkill, (artisan_id, skill_id))
    if artisan_skill is None:
        raise BadRequestError("Add this skill to your profile before asking for a vouch")
    if artisan_skill.verification_status == SkillVerificationStatus.VERIFIED.value:
        raise ConflictError("This skill is already verified")

    cooldown = _now() - timedelta(days=get_settings().vouch_reject_cooldown_days)
    recently_rejected = db.scalar(
        select(func.count()).select_from(TradeGroupVouch).where(
            TradeGroupVouch.group_id == group_id, TradeGroupVouch.artisan_id == artisan_id,
            TradeGroupVouch.skill_id == skill_id, TradeGroupVouch.status == VouchStatus.REJECTED.value,
            TradeGroupVouch.decided_at > cooldown))
    if recently_rejected:
        raise ConflictError("This trade group recently declined your request. Please wait before asking again")

    raw, hashed = _new_token()
    vouch = TradeGroupVouch(group_id=group_id, artisan_id=artisan_id, skill_id=skill_id, requested_by=user.user_id,
                            artisan_note=note, token_hash=hashed, token_expires_at=_expiry())
    db.add(vouch)
    try:
        db.commit()   # partial unique index: no duplicate open/confirmed vouch
    except IntegrityError:
        db.rollback()
        raise ConflictError("A vouch from this trade group for this skill is already pending or confirmed")
    return vouch, _send_vouch_email(db, vouch, raw)


def _send_vouch_email(db: Session, vouch: TradeGroupVouch, raw_token: str) -> bool:
    group, artisan, skill = vouch.group, vouch.artisan, vouch.skill
    note = f"\nMessage from the artisan:\n  {vouch.artisan_note}\n" if vouch.artisan_note else ""
    link = _confirm_url("/trade-group-vouches/confirm-page", raw_token)
    return email_service.send_email(
        group.email, f"{artisan.full_name} asks {group.name} to vouch for their {skill.skill_name} skills",
        f"Hello {group.name},\n\n"
        f"{artisan.full_name} ({artisan.location}) says they are a member of, or known to, your trade group and "
        f"asks you to vouch for their skill: {skill.skill_name}.\n{note}\n"
        "Please vouch ONLY if you personally know their work. A vouch from your group lets them be listed as "
        "verified for this skill, and customers will rely on it.\n\n"
        f"Review and decide here (you can confirm or decline):\n{link}\n\n"
        f"This link works once and expires in {get_settings().vouch_token_ttl_hours // 24} days. If you do not "
        "know this person, decline or ignore this message.\n",
    )


def resend_vouch(db: Session, user: User, artisan_id: uuid.UUID, vouch_id: uuid.UUID) -> tuple[TradeGroupVouch, bool]:
    vouch = db.get(TradeGroupVouch, vouch_id)
    if vouch is None or vouch.artisan_id != artisan_id or vouch.artisan.user_id != user.user_id:
        raise NotFoundError("Vouch request not found")
    if vouch.status != VouchStatus.PENDING_CONFIRMATION.value and not (
        vouch.status == VouchStatus.EXPIRED.value
    ):
        raise ConflictError("Only a pending or expired request can be re-sent")
    if vouch.group.status != TradeGroupStatus.ACTIVE.value:
        raise ConflictError("This trade group is not active")
    raw, hashed = _new_token()
    vouch.token_hash, vouch.token_expires_at = hashed, _expiry()   # the old link stops working
    vouch.status = VouchStatus.PENDING_CONFIRMATION.value
    db.commit()
    return vouch, _send_vouch_email(db, vouch, raw)


def list_for_artisan(db: Session, artisan_id: uuid.UUID, confirmed_only: bool = False) -> list[TradeGroupVouch]:
    query = select(TradeGroupVouch).where(TradeGroupVouch.artisan_id == artisan_id)
    if confirmed_only:
        query = query.where(TradeGroupVouch.status == VouchStatus.CONFIRMED.value)
    return list(db.scalars(query.order_by(TradeGroupVouch.created_at)))


def has_confirmed_vouch(db: Session, artisan_id: uuid.UUID, skill_id: uuid.UUID) -> bool:
    return bool(db.scalar(
        select(func.count()).select_from(TradeGroupVouch).where(
            TradeGroupVouch.artisan_id == artisan_id, TradeGroupVouch.skill_id == skill_id,
            TradeGroupVouch.status == VouchStatus.CONFIRMED.value)))


# ----------------------------------------------------------------------------- the trade group answers
def get_by_token(db: Session, raw_token: str) -> TradeGroupVouch:
    """Read-only lookup for the confirmation page. Changes nothing (safe against link pre-fetching)."""
    vouch = db.scalar(select(TradeGroupVouch).where(TradeGroupVouch.token_hash == _hash(raw_token)))
    if vouch is None:
        raise NotFoundError("This link is invalid or has already been used")
    if _aware(vouch.token_expires_at) < _now():
        raise GoneError("This link has expired. The artisan can send a new request")
    return vouch


def respond(db: Session, raw_token: str, confirm: bool) -> TradeGroupVouch:
    vouch = db.scalar(select(TradeGroupVouch).where(TradeGroupVouch.token_hash == _hash(raw_token))
                      .with_for_update().execution_options(populate_existing=True))
    if vouch is None or vouch.status != VouchStatus.PENDING_CONFIRMATION.value:
        raise NotFoundError("This link is invalid or has already been used")
    if _aware(vouch.token_expires_at) < _now():
        vouch.status, vouch.token_hash = VouchStatus.EXPIRED.value, None
        db.commit()
        raise GoneError("This link has expired. The artisan can send a new request")
    if vouch.group.status != TradeGroupStatus.ACTIVE.value:
        raise ConflictError("This trade group is not active")

    vouch.token_hash = None   # single use, whatever the answer
    vouch.decided_at = _now()
    if confirm:
        vouch.status = VouchStatus.CONFIRMED.value
        _qualify(db, vouch)
    else:
        vouch.status = VouchStatus.REJECTED.value
    db.commit()
    return vouch


def _qualify(db: Session, vouch: TradeGroupVouch) -> None:
    """A confirmed vouch automatically qualifies the artisan for this skill."""
    if not get_settings().trade_group_vouch_auto_verifies:
        return   # it then only satisfies the community-proof requirement for a verifier (verification_service)
    note = f"Vouched for by trade group '{vouch.group.name}' (e-mail confirmed). Automatic qualification."
    check = db.scalar(select(VerificationCheck).where(
        VerificationCheck.artisan_id == vouch.artisan_id, VerificationCheck.skill_id == vouch.skill_id,
        VerificationCheck.check_type == CheckType.SKILL.value, VerificationCheck.status.in_(OPEN_CHECK_STATUSES)))
    if check is None:
        check = VerificationCheck(artisan_id=vouch.artisan_id, skill_id=vouch.skill_id,
                                  check_type=CheckType.SKILL.value, evidence_description=note)
        db.add(check)
    check.status = CheckStatus.APPROVED.value
    check.decision_notes = note
    check.reviewed_at = _now()
    db.flush()
    vouch.verification_check_id = check.check_id
    artisan_skill = db.get(ArtisanSkill, (vouch.artisan_id, vouch.skill_id))
    if artisan_skill is not None:
        artisan_skill.verification_status = SkillVerificationStatus.VERIFIED.value


# ----------------------------------------------------------------------------- revocation
def revoke(db: Session, admin: User, vouch_id: uuid.UUID, notes: str) -> TradeGroupVouch:
    if admin.role != Role.ADMIN.value:
        raise PermissionDeniedError("Only administrators can revoke vouches")
    vouch = db.scalar(select(TradeGroupVouch).where(TradeGroupVouch.vouch_id == vouch_id)
                      .with_for_update().execution_options(populate_existing=True))
    if vouch is None:
        raise NotFoundError("Vouch not found")
    if vouch.status != VouchStatus.CONFIRMED.value:
        raise ConflictError("Only a confirmed vouch can be revoked")
    vouch.status = VouchStatus.REVOKED.value
    vouch.decision_notes = notes
    if vouch.verification_check_id is not None:
        check = db.get(VerificationCheck, vouch.verification_check_id)
        check.status = CheckStatus.REJECTED.value
        check.decision_notes = f"Trade-group vouch revoked: {notes}"
        other_basis = db.scalar(select(func.count()).select_from(VerificationCheck).where(
            VerificationCheck.artisan_id == vouch.artisan_id, VerificationCheck.skill_id == vouch.skill_id,
            VerificationCheck.check_type == CheckType.SKILL.value,
            VerificationCheck.status == CheckStatus.APPROVED.value,
            VerificationCheck.check_id != check.check_id))   # the revoked check itself never counts
        artisan_skill = db.get(ArtisanSkill, (vouch.artisan_id, vouch.skill_id))
        if not other_basis and artisan_skill is not None:
            artisan_skill.verification_status = SkillVerificationStatus.UNVERIFIED.value
    db.commit()
    return vouch
