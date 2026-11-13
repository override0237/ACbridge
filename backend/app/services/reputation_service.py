"""Work reputation: Bayesian-smoothed average of reviews that are tied to COMPLETED jobs.

    R = (v / (v + m)) * A + (m / (v + m)) * C

  v = number of verified reviews          A = the artisan's average verified rating
  m = prior strength (default 10)         C = platform-wide prior average (default 4.0)

Why smooth? One 5-star review should not outrank 80 reviews averaging 4.7. With few reviews the
score stays near the platform average C; as evidence (v) grows it converges to the true average A.

A review is "verified" by construction: create_review only accepts reviews from the customer of a
COMPLETED job (both parties confirmed), and the database forbids a second review per (job, reviewer).
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Job, JobStatus, Review, User


@dataclass(frozen=True)
class Reputation:
    artisan_id: uuid.UUID
    reputation_score: float
    verified_reviews: int
    average_rating: float | None
    completed_jobs: int


def bayesian_score(review_count: int, average_rating: float | None, m: float, prior_mean: float) -> float:
    if review_count <= 0 or average_rating is None:
        return prior_mean
    v = review_count
    return (v / (v + m)) * average_rating + (m / (v + m)) * prior_mean


def get_reputations(db: Session, artisan_ids: list[uuid.UUID]) -> dict[uuid.UUID, Reputation]:
    """Reputation for many artisans in TWO grouped queries (avoids an N+1 query per artisan)."""
    settings = get_settings()
    stats: dict[uuid.UUID, tuple[int, float | None]] = {}
    completed: dict[uuid.UUID, int] = {}
    if artisan_ids:
        for artisan_id, count, avg in db.execute(
            select(Job.artisan_id, func.count(Review.review_id), func.avg(Review.rating))
            .join(Review, Review.job_id == Job.job_id)
            .where(Job.status == JobStatus.COMPLETED.value, Job.artisan_id.in_(artisan_ids))
            .group_by(Job.artisan_id)
        ):
            stats[artisan_id] = (count, float(avg))
        for artisan_id, count in db.execute(
            select(Job.artisan_id, func.count())
            .where(Job.status == JobStatus.COMPLETED.value, Job.artisan_id.in_(artisan_ids))
            .group_by(Job.artisan_id)
        ):
            completed[artisan_id] = count

    result = {}
    for artisan_id in artisan_ids:
        count, avg = stats.get(artisan_id, (0, None))
        result[artisan_id] = Reputation(
            artisan_id=artisan_id,
            reputation_score=round(
                bayesian_score(count, avg, settings.reputation_min_evidence, settings.reputation_platform_average), 4
            ),
            verified_reviews=count,
            average_rating=round(avg, 4) if avg is not None else None,
            completed_jobs=completed.get(artisan_id, 0),
        )
    return result


def get_reputation(db: Session, artisan_id: uuid.UUID) -> Reputation:
    return get_reputations(db, [artisan_id])[artisan_id]


def create_review(db: Session, user: User, job_id: uuid.UUID, rating: int, comment: str | None) -> Review:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    # Only the paying customer of THIS job may review it (not the artisan, not strangers).
    if job.request.customer_id != user.user_id:
        raise PermissionDeniedError("Only the customer of this job can review it")
    if job.status != JobStatus.COMPLETED.value:
        raise ConflictError("Reviews are only accepted after both parties have confirmed completion")
    review = Review(job_id=job_id, reviewer_id=user.user_id, rating=rating, comment=comment)
    db.add(review)
    try:
        db.commit()  # UNIQUE(job_id, reviewer_id) makes duplicates impossible even under races
    except IntegrityError:
        db.rollback()
        raise ConflictError("You have already reviewed this job")
    return review
