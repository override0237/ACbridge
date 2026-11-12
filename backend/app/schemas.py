"""Pydantic models: validate everything coming IN and shape everything going OUT.

Output schemas deliberately omit password hashes, evidence file paths and other private data.
"""
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import (
    AvailabilityStatus, CheckStatus, CheckType, ProficiencyLevel,
)

AvailabilityLiteral = Literal["AVAILABLE", "BUSY", "UNAVAILABLE"]
ProficiencyLiteral = Literal["BEGINNER", "INTERMEDIATE", "EXPERT"]
_ = (AvailabilityStatus, ProficiencyLevel, CheckType, CheckStatus)  # enums documented in models.py


def normalize_phone(raw: str) -> str:
    """Accept local Cameroon mobiles (6XXXXXXXX) or international +E.164; store one canonical form."""
    cleaned = re.sub(r"[\s\-().]", "", raw)
    if re.fullmatch(r"6\d{8}", cleaned):
        cleaned = "+237" + cleaned
    elif re.fullmatch(r"237\d{9}", cleaned):
        cleaned = "+" + cleaned
    if not re.fullmatch(r"\+[1-9]\d{7,14}", cleaned):
        raise ValueError("Enter a valid phone number, e.g. 670123456 or +237670123456")
    return cleaned


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    phone: str
    password: str = Field(min_length=8, max_length=128)
    # Only these two roles can be self-selected. VERIFIER/ADMIN are granted by an admin, never by the client.
    role: Literal["CUSTOMER", "ARTISAN"]

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, value: str) -> str:
        return normalize_phone(value)


class LoginIn(BaseModel):
    phone: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, value: str) -> str:
        return normalize_phone(value)


class UserOut(ORM):
    user_id: uuid.UUID
    phone: str
    role: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    role: str


class RoleChangeIn(BaseModel):
    role: Literal["CUSTOMER", "ARTISAN", "VERIFIER", "ADMIN"]


# ------------------------------------------------------------------ skills
class SkillIn(BaseModel):
    skill_name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    safety_critical: bool = False


class SkillOut(ORM):
    skill_id: uuid.UUID
    skill_name: str
    description: str | None
    safety_critical: bool


# ------------------------------------------------------------------ artisans
class ReputationOut(BaseModel):
    artisan_id: uuid.UUID
    reputation_score: float = Field(description="Bayesian-smoothed rating (1-5)")
    verified_reviews: int
    average_rating: float | None
    completed_jobs: int
    platform_average_prior: float
    min_evidence_threshold: int
    note: str


class ArtisanProfileIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=160, description="'Neighbourhood, Town' e.g. 'Small Soppo, Buea'")
    description: str | None = Field(default=None, max_length=1000)
    availability_status: AvailabilityLiteral = "AVAILABLE"


class ArtisanProfileUpdate(BaseModel):
    location: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    availability_status: AvailabilityLiteral | None = None


class ArtisanSkillIn(BaseModel):
    skill_id: uuid.UUID
    proficiency_level: ProficiencyLiteral
    typical_price: int | None = Field(default=None, ge=0, le=100_000_000, description="Typical price in FCFA")


class ArtisanSkillOut(BaseModel):
    skill_id: uuid.UUID
    skill_name: str
    proficiency_level: str
    verification_status: str
    typical_price: int | None


class ArtisanOut(BaseModel):
    """Public view of an artisan. Three SEPARATE dimensions: identity, skill verification, work reputation."""

    artisan_id: uuid.UUID
    full_name: str
    location: str
    description: str | None
    availability_status: str
    is_suspended: bool
    identity_verified: bool
    skills: list[ArtisanSkillOut]
    endorsement_count: int
    reputation: ReputationOut
    verification_mode: str
    verification_notice: str


class EndorsementIn(BaseModel):
    evidence_description: str = Field(
        min_length=10, max_length=1000, description="How do you know this artisan's work?"
    )


class EndorsementOut(ORM):
    endorsement_id: uuid.UUID
    artisan_id: uuid.UUID
    created_at: datetime


# ------------------------------------------------------------------ verification
class VerificationIn(BaseModel):
    check_type: Literal["IDENTITY", "SKILL"]
    skill_id: uuid.UUID | None = Field(default=None, description="Required when check_type is SKILL")
    evidence_description: str = Field(min_length=10, max_length=2000)


class VerificationDecisionIn(BaseModel):
    decision: Literal["UNDER_REVIEW", "APPROVED", "REJECTED", "NEEDS_MORE_EVIDENCE"]
    decision_notes: str | None = Field(default=None, max_length=2000)


class VerificationOut(BaseModel):
    check_id: uuid.UUID
    artisan_id: uuid.UUID
    skill_id: uuid.UUID | None
    verifier_id: uuid.UUID | None
    check_type: str
    status: str
    evidence_description: str
    has_evidence_file: bool
    decision_notes: str | None
    created_at: datetime
    reviewed_at: datetime | None
    endorsement_count: int
    review_signals: list[str] = Field(description="Hints for the HUMAN verifier. Not accusations of fraud.")
    simulated: bool
    notice: str


# ------------------------------------------------------------------ service requests
class ServiceRequestIn(BaseModel):
    skill_id: uuid.UUID
    description: str = Field(min_length=5, max_length=2000)
    location: str = Field(min_length=2, max_length=160, description="'Neighbourhood, Town'")
    budget: int | None = Field(default=None, ge=0, le=100_000_000, description="Budget in FCFA")


class ServiceRequestOut(ORM):
    request_id: uuid.UUID
    customer_id: uuid.UUID
    skill_id: uuid.UUID
    description: str
    location: str
    budget: int | None
    status: str
    created_at: datetime


# ------------------------------------------------------------------ matching
class ScoreBreakdown(BaseModel):
    skill: float
    location: float
    availability: float
    work_history: float
    price: float


class MatchOut(BaseModel):
    artisan_id: uuid.UUID
    full_name: str
    location: str
    availability_status: str
    skill_verification_status: str
    typical_price: int | None
    verified_reviews: int
    reputation_score: float
    match_score: float
    breakdown: ScoreBreakdown


class MatchesOut(BaseModel):
    request_id: uuid.UUID
    weights: dict[str, float]
    service_area_supported: bool
    matches: list[MatchOut]
    excluded_summary: dict[str, int] = Field(description="How many candidates were filtered out, and why")
    disclaimer: str


# ------------------------------------------------------------------ jobs
class JobCreateIn(BaseModel):
    request_id: uuid.UUID
    artisan_id: uuid.UUID
    agreed_price: int = Field(ge=0, le=100_000_000)


class DisputeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class DisputeResolutionIn(BaseModel):
    outcome: Literal["CANCELLED", "IN_PROGRESS"]
    notes: str = Field(min_length=5, max_length=1000)


class JobEventOut(ORM):
    event_id: uuid.UUID
    actor_id: uuid.UUID
    event_type: str
    event_metadata: dict | None
    created_at: datetime


class JobOut(BaseModel):
    job_id: uuid.UUID
    request_id: uuid.UUID
    artisan_id: uuid.UUID
    customer_id: uuid.UUID
    agreed_price: int
    status: str
    customer_confirmed: bool
    artisan_confirmed: bool
    created_at: datetime
    completed_at: datetime | None
    counterpart_phone: str | None = Field(description="Shown to the two parties once the job is accepted")
    events: list[JobEventOut]


# ------------------------------------------------------------------ reviews
class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewOut(ORM):
    review_id: uuid.UUID
    job_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime
