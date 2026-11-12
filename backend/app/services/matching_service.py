"""Transparent, deterministic two-stage matching.

STAGE 1 - eligibility (hard filters; a high score can NEVER compensate for failing one):
    * artisan has the skill (the candidate query is by skill)
    * artisan is not suspended
    * availability is not UNAVAILABLE
    * artisan is in the request's town, and that town is a supported service area
    * if the skill is safety-critical: the artisan's verification for THAT skill is VERIFIED
    * the artisan is not the requester themself

STAGE 2 - ranking:  M(a) = 0.35*S + 0.25*L + 0.15*A + 0.15*R + 0.10*P      (each component 0-100)

  S skill       = 0.5 * proficiency(BEGINNER 40 / INTERMEDIATE 70 / EXPERT 100)
                + 0.5 * verification(VERIFIED 100 / PENDING 30 / otherwise 0)
  L location    = 100 same neighbourhood and town; 60 same town (different or unknown neighbourhood)
  A availability= AVAILABLE 100, BUSY 50 (UNAVAILABLE is already excluded)
  R work history= 0.6 * ((bayesian_reputation - 1) / 4 * 100) + 0.4 * (min(completed_jobs, 10) / 10 * 100)
                  (a newcomer with no history gets the platform prior, not zero and not a free pass)
  P price       = 50 if budget or the artisan's typical price is unknown;
                  100 if typical_price <= budget; else 100 * max(0, 2 - typical_price / budget)

The score ranks suitability only. It is NOT a measure of trustworthiness.

Complexity: with n artisans holding the skill and k results requested -
  eligibility + scoring O(n), selecting the top k with a heap O(n log k), memory O(n).
  The skill lookup uses the (skill_id, verification_status) index; reputation uses two grouped queries.
"""
import heapq
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ArtisanProfile, ArtisanSkill, AvailabilityStatus, ProficiencyLevel, ServiceRequest, Skill,
    SkillVerificationStatus,
)
from app.services.reputation_service import Reputation, get_reputations

# ---- tunable knobs: change here, everything else follows -------------------------------------
WEIGHTS: dict[str, float] = {"skill": 0.35, "location": 0.25, "availability": 0.15, "work_history": 0.15, "price": 0.10}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "matching weights must sum to 1"

PROFICIENCY_POINTS = {
    ProficiencyLevel.BEGINNER.value: 40.0, ProficiencyLevel.INTERMEDIATE.value: 70.0, ProficiencyLevel.EXPERT.value: 100.0,
}
VERIFICATION_POINTS = {
    SkillVerificationStatus.VERIFIED.value: 100.0, SkillVerificationStatus.PENDING.value: 30.0,
}
AVAILABILITY_POINTS = {AvailabilityStatus.AVAILABLE.value: 100.0, AvailabilityStatus.BUSY.value: 50.0}
NEUTRAL_SCORE = 50.0
JOBS_FOR_FULL_HISTORY_CREDIT = 10
DEFAULT_RESULT_LIMIT = 10

DISCLAIMER = (
    "The match score ranks suitability for this request (skill, location, availability, history, price). "
    "It is not proof of trustworthiness. Verification is SIMULATED in this prototype."
)


@dataclass(frozen=True)
class Candidate:
    artisan: ArtisanProfile
    artisan_skill: ArtisanSkill


@dataclass
class ScoredCandidate:
    candidate: Candidate
    reputation: Reputation
    breakdown: dict[str, float]
    match_score: float
    sort_key: tuple = field(repr=False, default=())


# ---------------------------------------------------------------------------- location helpers
def parse_location(raw: str) -> tuple[str | None, str]:
    """'Small Soppo, Buea' -> ('small soppo', 'buea'); 'Buea' -> (None, 'buea')."""
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if not parts:
        return None, ""
    return (parts[0] if len(parts) > 1 else None), parts[-1]


# ---------------------------------------------------------------------------- stage 1
def eligibility_failure(candidate: Candidate, request: ServiceRequest, skill: Skill, requester_user_id: uuid.UUID) -> str | None:
    """Return the reason this candidate is excluded, or None if eligible."""
    artisan = candidate.artisan
    if artisan.user_id == requester_user_id:
        return "OWN_PROFILE"
    if artisan.is_suspended:
        return "SUSPENDED"
    if artisan.availability_status not in AVAILABILITY_POINTS:
        return "UNAVAILABLE"
    _, request_town = parse_location(request.location)
    _, artisan_town = parse_location(artisan.location)
    if request_town not in get_settings().supported_town_set or artisan_town != request_town:
        return "OUTSIDE_SERVICE_AREA"
    if skill.safety_critical and candidate.artisan_skill.verification_status != SkillVerificationStatus.VERIFIED.value:
        return "SKILL_NOT_VERIFIED_FOR_SAFETY_CRITICAL_WORK"
    return None


# ---------------------------------------------------------------------------- stage 2 (pure functions)
def skill_score(proficiency_level: str, verification_status: str) -> float:
    return 0.5 * PROFICIENCY_POINTS.get(proficiency_level, 0.0) + 0.5 * VERIFICATION_POINTS.get(verification_status, 0.0)


def location_score(request_location: str, artisan_location: str) -> float:
    req_hood, req_town = parse_location(request_location)
    art_hood, art_town = parse_location(artisan_location)
    if not req_town or req_town != art_town:
        return 0.0
    return 100.0 if (req_hood is not None and req_hood == art_hood) else 60.0


def availability_score(availability_status: str) -> float:
    return AVAILABILITY_POINTS.get(availability_status, 0.0)


def work_history_score(reputation_score: float, completed_jobs: int) -> float:
    quality = (min(max(reputation_score, 1.0), 5.0) - 1.0) / 4.0 * 100.0
    experience = min(completed_jobs, JOBS_FOR_FULL_HISTORY_CREDIT) / JOBS_FOR_FULL_HISTORY_CREDIT * 100.0
    return 0.6 * quality + 0.4 * experience


def price_score(typical_price: int | None, budget: int | None) -> float:
    if typical_price is None or budget is None or budget <= 0:
        return NEUTRAL_SCORE  # missing data -> neutral, never a crash and never a penalty or bonus
    if typical_price <= budget:
        return 100.0
    return 100.0 * max(0.0, 2.0 - typical_price / budget)


def compute_match_score(components: dict[str, float], weights: dict[str, float] = WEIGHTS) -> float:
    return sum(weights[name] * components[name] for name in weights)


def score_candidate(candidate: Candidate, request: ServiceRequest, reputation: Reputation) -> ScoredCandidate:
    breakdown = {
        "skill": skill_score(candidate.artisan_skill.proficiency_level, candidate.artisan_skill.verification_status),
        "location": location_score(request.location, candidate.artisan.location),
        "availability": availability_score(candidate.artisan.availability_status),
        "work_history": work_history_score(reputation.reputation_score, reputation.completed_jobs),
        "price": price_score(candidate.artisan_skill.typical_price, request.budget),
    }
    score = compute_match_score(breakdown)
    # Deterministic tie-break: higher score, then more verified reviews, then stable id order.
    key = (round(score, 6), reputation.verified_reviews, str(candidate.artisan.artisan_id))
    return ScoredCandidate(candidate, reputation, breakdown, score, key)


def rank_candidates(scored: list[ScoredCandidate], limit: int) -> list[ScoredCandidate]:
    """Top-k by (score desc, verified reviews desc, artisan id asc) using a heap: O(n log k).

    heapq.nlargest returns results already sorted best-first. The id is negated through a tuple of
    ordinals' complement so that, among ties, the smaller id wins deterministically.
    """
    return heapq.nlargest(
        limit, scored,
        key=lambda s: (s.sort_key[0], s.sort_key[1], tuple(-ord(ch) for ch in s.sort_key[2])),
    )


# ---------------------------------------------------------------------------- orchestration
@dataclass
class MatchResult:
    ranked: list[ScoredCandidate]
    excluded_summary: dict[str, int]
    service_area_supported: bool


def load_candidates(db: Session, skill_id: uuid.UUID) -> list[Candidate]:
    rows = db.execute(
        select(ArtisanSkill, ArtisanProfile)
        .join(ArtisanProfile, ArtisanProfile.artisan_id == ArtisanSkill.artisan_id)
        .where(ArtisanSkill.skill_id == skill_id)
        .order_by(ArtisanProfile.artisan_id)  # stable input order -> deterministic output
    ).all()
    return [Candidate(artisan=artisan, artisan_skill=a_skill) for a_skill, artisan in rows]


def find_matches(db: Session, request: ServiceRequest, limit: int = DEFAULT_RESULT_LIMIT) -> MatchResult:
    skill = db.get(Skill, request.skill_id)
    _, request_town = parse_location(request.location)
    area_ok = request_town in get_settings().supported_town_set

    eligible: list[Candidate] = []
    excluded: dict[str, int] = {}
    for candidate in load_candidates(db, request.skill_id):
        reason = eligibility_failure(candidate, request, skill, request.customer_id)
        if reason is None:
            eligible.append(candidate)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1

    reputations = get_reputations(db, [c.artisan.artisan_id for c in eligible])
    scored = [score_candidate(c, request, reputations[c.artisan.artisan_id]) for c in eligible]
    return MatchResult(rank_candidates(scored, limit), excluded, area_ok)


def is_eligible_for_request(db: Session, request: ServiceRequest, artisan_id: uuid.UUID) -> str | None:
    """Server-side re-check used when a customer picks an artisan (never trust the client's choice)."""
    skill = db.get(Skill, request.skill_id)
    a_skill = db.get(ArtisanSkill, (artisan_id, request.skill_id))
    artisan = db.get(ArtisanProfile, artisan_id)
    if artisan is None or a_skill is None:
        return "MISSING_SKILL"
    return eligibility_failure(Candidate(artisan, a_skill), request, skill, request.customer_id)
