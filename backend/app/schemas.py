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
    whatsapp_number: str | None = Field(
        default=None, description="Optional. If given, matched customers get a WhatsApp chat link to this number."
    )

    @field_validator("whatsapp_number")
    @classmethod
    def _clean_whatsapp(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else None


class ArtisanProfileUpdate(BaseModel):
    location: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    availability_status: AvailabilityLiteral | None = None
    whatsapp_number: str | None = None

    @field_validator("whatsapp_number")
    @classmethod
    def _clean_whatsapp(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else None


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
    whatsapp_available: bool
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
    needs_inspection: bool = Field(
        default=False, description="True if the artisan must examine the problem before a price can be given"
    )


class ServiceRequestOut(ORM):
    request_id: uuid.UUID
    customer_id: uuid.UUID
    skill_id: uuid.UUID
    description: str
    location: str
    budget: int | None
    needs_inspection: bool
    status: str
    created_at: datetime


# ------------------------------------------------------------------ matching
class ScoreBreakdown(BaseModel):
    skill: float
    location: float
    availability: float
    work_history: float
    price: float


class ContactOut(BaseModel):
    """How the customer can talk to a matched artisan before booking (artisan opt-in)."""

    channel: Literal["WHATSAPP"] = "WHATSAPP"
    icon: str = "whatsapp"
    label: str = "Chat on WhatsApp"
    link: str = Field(description="wa.me click-to-chat link with a prefilled message")
    tip: str


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
    contact: ContactOut | None = Field(description="null when the artisan has not opted in to WhatsApp")


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
    proposed_price: int | None = Field(
        default=None, ge=1, le=100_000_000,
        description="Amount you offer in FCFA. Required for normal requests; must be omitted when the "
                    "request needs inspection.",
    )


class QuoteIn(BaseModel):
    amount: int = Field(ge=1, le=100_000_000, description="Price in FCFA after inspecting the problem")


class QuoteResponseIn(BaseModel):
    approve: bool


class DisputeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class DisputeResolutionIn(BaseModel):
    outcome: Literal["CANCELLED", "IN_PROGRESS"]
    notes: str = Field(min_length=5, max_length=1000)


class HardshipClaimIn(BaseModel):
    kind: Literal["DEATH", "ACCIDENT_OR_SERIOUS_ILLNESS"]
    affected_party: Literal["CUSTOMER", "ARTISAN"] = Field(description="Who died or was seriously hurt/ill")
    description: str = Field(min_length=10, max_length=2000)


class HardshipDecisionIn(BaseModel):
    approve: bool
    notes: str = Field(min_length=5, max_length=2000, description="What document you checked and why")


class HardshipClaimOut(BaseModel):
    claim_id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    affected_party: str
    description: str
    status: str
    has_document: bool
    decision_notes: str | None
    created_at: datetime
    decided_at: datetime | None
    required_proof: str


class JobEventOut(ORM):
    event_id: uuid.UUID
    actor_id: uuid.UUID
    event_type: str
    event_metadata: dict | None
    created_at: datetime


class PaymentOut(BaseModel):
    payment_id: uuid.UUID
    job_id: uuid.UUID
    payment_type: str
    amount: int
    currency: str
    status: str
    provider: str
    description: str | None
    created_at: datetime
    settled_at: datetime | None
    simulated: bool
    notice: str


class PricingPolicyOut(BaseModel):
    currency: str
    fixed_price_commission_percent: float
    fixed_price_commission_minimum: int
    inspection_assignment_fee: int
    fees_paid_by: str
    customer_pays: str
    probation_hours: int
    probation_rule: str
    refund_policy: str
    provider: str
    notice: str


class JobOut(BaseModel):
    job_id: uuid.UUID
    request_id: uuid.UUID
    artisan_id: uuid.UUID
    customer_id: uuid.UUID
    pricing_mode: str = Field(description="FIXED_PRICE or INSPECTION_REQUIRED")
    proposed_price: int | None
    proposed_by: str | None
    agreed_price: int | None
    artisan_agreed: bool
    terms_agreed_at: datetime | None
    probation_ends_at: datetime | None
    probation_active: bool = Field(description="True while both sides can still withdraw for free")
    can_cancel_freely: bool = Field(description="False once confirmed: only a hardship claim or dispute remains")
    escrow_status: str = Field(description="NOT_PAID, AWAITING_PAYMENT, HELD, RELEASED or REFUNDED")
    payment_due: PaymentOut | None = Field(description="The payment YOU still have to approve, if any")
    payments: list[PaymentOut]
    status: str
    customer_confirmed: bool
    artisan_confirmed: bool
    created_at: datetime
    completed_at: datetime | None
    counterpart_phone: str | None = Field(description="Shown to the two parties once the job is accepted")
    counterpart_whatsapp_link: str | None
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
