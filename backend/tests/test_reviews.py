import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Review
from app.services.reputation_service import bayesian_score


def _review(world, actor, job_id, rating=5, comment="Great work"):
    return world.client.post(f"/jobs/{job_id}/reviews", headers=actor.headers, json={"rating": rating, "comment": comment})


def test_review_rejected_for_incomplete_job(world):
    customer, john, job_id = world.job_in_progress()
    assert _review(world, customer, job_id).status_code == 409
    world.client.post(f"/jobs/{job_id}/confirm-completion", headers=customer.headers)   # only one side confirmed
    assert _review(world, customer, job_id).status_code == 409


def test_review_accepted_after_completion_and_duplicate_rejected(world):
    customer, john, job_id = world.completed_job()
    assert _review(world, customer, job_id, 5).status_code == 201
    assert _review(world, customer, job_id, 1).status_code == 409
    assert world.client.get(f"/artisans/{john.artisan_id}/reputation").json()["verified_reviews"] == 1


def test_unrelated_users_and_the_artisan_cannot_review(world):
    customer, john, job_id = world.completed_job()
    stranger, other_artisan = world.user("CUSTOMER"), world.artisan(world.skill())
    for actor in (stranger, other_artisan):
        assert _review(world, actor, job_id).status_code in (403,)
    assert _review(world, john, job_id).status_code == 403          # artisans cannot review themselves
    assert world.client.get(f"/artisans/{john.artisan_id}/reputation").json()["verified_reviews"] == 0


def test_review_for_nonexistent_job_rejected(world):
    customer = world.user("CUSTOMER")
    assert _review(world, customer, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_rating_bounds_enforced_by_api_and_database(world, session_factory):
    customer, john, job_id = world.completed_job()
    for bad in (0, 6, -1):
        assert _review(world, customer, job_id, bad).status_code == 422
    with session_factory() as db:
        from app.models import Job
        job = db.query(Job).one()
        db.add(Review(job_id=job.job_id, reviewer_id=customer.user_id, rating=9))
        with pytest.raises(IntegrityError):       # the CHECK constraint, bypassing the API
            db.commit()


def test_duplicate_review_blocked_by_database_constraint(world, session_factory):
    customer, john, job_id = world.completed_job()
    assert _review(world, customer, job_id).status_code == 201
    with session_factory() as db:
        from app.models import Job
        job = db.query(Job).one()
        db.add(Review(job_id=job.job_id, reviewer_id=customer.user_id, rating=4))
        with pytest.raises(IntegrityError):
            db.commit()


def test_bayesian_formula_examples():
    # R = v/(v+m) * A + m/(v+m) * C   with m=10, C=4.0
    five_reviews = bayesian_score(5, 5.0, m=10, prior_mean=4.0)
    eighty_reviews = bayesian_score(80, 4.7, m=10, prior_mean=4.0)
    assert five_reviews == pytest.approx(13 / 3, abs=1e-9)           # 4.3333...
    assert eighty_reviews == pytest.approx(4.6222222, abs=1e-6)
    assert eighty_reviews > five_reviews                             # more evidence beats a perfect-but-thin record
    assert bayesian_score(0, None, 10, 4.0) == 4.0                   # no reviews -> the platform prior


def test_reputation_endpoint_uses_only_completed_job_reviews(world):
    skill_id = world.skill()
    john = world.artisan(skill_id)
    for rating in (5, 5, 4):
        customer = world.user("CUSTOMER")
        job_id = world.job(customer, john, world.request(customer, skill_id))
        for action in ("accept", "start"):
            world.client.post(f"/jobs/{job_id}/{action}", headers=john.headers)
        for actor in (customer, john):
            world.client.post(f"/jobs/{job_id}/confirm-completion", headers=actor.headers)
        assert _review(world, customer, job_id, rating).status_code == 201
    # an unfinished job's review attempt does not count
    pending_customer = world.user("CUSTOMER")
    pending_job = world.job(pending_customer, john, world.request(pending_customer, skill_id))
    assert _review(world, pending_customer, pending_job).status_code == 409

    rep = world.client.get(f"/artisans/{john.artisan_id}/reputation").json()
    average = (5 + 5 + 4) / 3
    assert rep["verified_reviews"] == 3 and rep["completed_jobs"] == 3
    assert rep["average_rating"] == pytest.approx(average, abs=1e-3)
    assert rep["reputation_score"] == pytest.approx(3 / 13 * average + 10 / 13 * 4.0, abs=1e-3)
