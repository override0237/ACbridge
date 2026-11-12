import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ArtisanProfile, ArtisanSkill, Role, Skill, User
from app.schemas import (
    ArtisanOut, ArtisanProfileIn, ArtisanProfileUpdate, ArtisanSkillIn, ArtisanSkillOut, EndorsementIn,
    EndorsementOut, ReputationOut,
)
from app.security.permissions import require_roles
from app.services import reputation_service, verification_service

router = APIRouter(prefix="/artisans", tags=["artisans"])


def reputation_out(rep: reputation_service.Reputation) -> ReputationOut:
    settings = get_settings()
    return ReputationOut(
        artisan_id=rep.artisan_id, reputation_score=rep.reputation_score, verified_reviews=rep.verified_reviews,
        average_rating=rep.average_rating, completed_jobs=rep.completed_jobs,
        platform_average_prior=settings.reputation_platform_average,
        min_evidence_threshold=settings.reputation_min_evidence,
        note="Based only on reviews from jobs both parties confirmed as completed. "
             "Scores stay near the platform average until enough reviews exist.",
    )


def build_artisan_out(db: Session, artisan: ArtisanProfile) -> ArtisanOut:
    skills = [
        ArtisanSkillOut(
            skill_id=s.skill_id, skill_name=s.skill.skill_name, proficiency_level=s.proficiency_level,
            verification_status=s.verification_status, typical_price=s.typical_price,
        ) for s in artisan.skills
    ]
    return ArtisanOut(
        artisan_id=artisan.artisan_id, full_name=artisan.full_name, location=artisan.location,
        description=artisan.description, availability_status=artisan.availability_status,
        is_suspended=artisan.is_suspended,
        identity_verified=verification_service.is_identity_verified(db, artisan.artisan_id),
        skills=skills, endorsement_count=verification_service.count_endorsements(db, artisan.artisan_id),
        reputation=reputation_out(reputation_service.get_reputation(db, artisan.artisan_id)),
        verification_mode=get_settings().verification_mode,
        verification_notice=verification_service.SIMULATION_NOTICE,
    )


@router.post("", response_model=ArtisanOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ArtisanProfileIn, user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db)
) -> ArtisanOut:
    # user_id comes from the verified token, never from the request body.
    artisan = ArtisanProfile(user_id=user.user_id, **payload.model_dump())
    db.add(artisan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an artisan profile")
    return build_artisan_out(db, artisan)


@router.get("/{artisan_id}", response_model=ArtisanOut)
def get_artisan(artisan_id: uuid.UUID, db: Session = Depends(get_db)) -> ArtisanOut:
    """Public: customers can look at a profile before booking. Contains no phone number or evidence."""
    return build_artisan_out(db, verification_service.get_artisan_or_404(db, artisan_id))


def _own_profile(db: Session, user: User, artisan_id: uuid.UUID) -> ArtisanProfile:
    artisan = verification_service.get_artisan_or_404(db, artisan_id)
    if artisan.user_id != user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only manage your own profile")
    return artisan


@router.patch("/{artisan_id}", response_model=ArtisanOut)
def update_profile(
    artisan_id: uuid.UUID, payload: ArtisanProfileUpdate,
    user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db),
) -> ArtisanOut:
    artisan = _own_profile(db, user, artisan_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(artisan, field, value)
    db.commit()
    return build_artisan_out(db, artisan)


@router.post("/{artisan_id}/skills", response_model=ArtisanSkillOut, status_code=status.HTTP_201_CREATED)
def add_skill(
    artisan_id: uuid.UUID, payload: ArtisanSkillIn,
    user: User = Depends(require_roles(Role.ARTISAN)), db: Session = Depends(get_db),
) -> ArtisanSkillOut:
    artisan = _own_profile(db, user, artisan_id)
    skill = db.get(Skill, payload.skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    # verification_status is NEVER taken from the client: every new skill starts UNVERIFIED.
    link = ArtisanSkill(
        artisan_id=artisan.artisan_id, skill_id=skill.skill_id,
        proficiency_level=payload.proficiency_level, typical_price=payload.typical_price,
    )
    db.add(link)
    try:
        db.commit()  # composite PK (artisan_id, skill_id) blocks duplicates
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have this skill on your profile")
    return ArtisanSkillOut(
        skill_id=skill.skill_id, skill_name=skill.skill_name, proficiency_level=link.proficiency_level,
        verification_status=link.verification_status, typical_price=link.typical_price,
    )


@router.post("/{artisan_id}/endorsements", response_model=EndorsementOut, status_code=status.HTTP_201_CREATED)
def endorse(
    artisan_id: uuid.UUID, payload: EndorsementIn,
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ARTISAN, Role.VERIFIER)),
    db: Session = Depends(get_db),
):
    return verification_service.add_endorsement(db, user, artisan_id, payload.evidence_description)


@router.get("/{artisan_id}/reputation", response_model=ReputationOut, tags=["reviews"])
def get_reputation(artisan_id: uuid.UUID, db: Session = Depends(get_db)) -> ReputationOut:
    verification_service.get_artisan_or_404(db, artisan_id)
    return reputation_out(reputation_service.get_reputation(db, artisan_id))
