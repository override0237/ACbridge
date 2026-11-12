"""An artisan who does not accept a job offer in time loses it: 1 hour (urgent), 1 day (this week), 5 days (not urgent)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Job


def _offer(world, urgency):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    artisan = world.artisan(skill_id, "John Fon")
    job_id = world.job(customer, artisan, world.request(customer, skill_id, urgency=urgency), price=6000)
    return customer, artisan, job_id


def _age(session_factory, job_id, **delta):
    with session_factory() as db:
        job = db.get(Job, uuid.UUID(job_id))
        job.created_at = datetime.now(timezone.utc) - timedelta(**delta)
        db.commit()


def _job(world, actor, job_id):
    return world.client.get(f"/jobs/{job_id}", headers=actor.headers).json()


@pytest.mark.parametrize("urgency,fresh,stale", [
    ("TODAY", {"minutes": 59}, {"minutes": 61}),
    ("THIS_WEEK", {"hours": 23}, {"hours": 25}),
    ("NOT_URGENT", {"days": 4}, {"days": 6}),
])
def test_offer_is_valid_inside_the_window_and_cancelled_after_it(world, session_factory, urgency, fresh, stale):
    customer, artisan, job_id = _offer(world, urgency)
    _age(session_factory, job_id, **fresh)
    job = _job(world, customer, job_id)
    assert job["status"] == "REQUESTED" and job["offer_expires_at"] is not None       # still open, deadline shown
    assert world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers).status_code == 200

    customer2, artisan2, job2 = _offer(world, urgency)
    _age(session_factory, job2, **stale)
    res = world.client.post(f"/jobs/{job2}/accept", headers=artisan2.headers)
    assert res.status_code == 409 and "expired" in res.json()["detail"]
    after = _job(world, customer2, job2)
    assert after["status"] == "CANCELLED" and after["offer_expires_at"] is None
    assert any(e["event_type"] == "JOB_OFFER_EXPIRED" and e["event_metadata"]["urgency"] == urgency for e in after["events"])


def test_just_reading_an_overdue_offer_nullifies_it(world, session_factory):
    customer, artisan, job_id = _offer(world, "TODAY")
    _age(session_factory, job_id, hours=2)
    assert _job(world, customer, job_id)["status"] == "CANCELLED"
    # the artisan can no longer accept, start or chat on it
    assert world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers).status_code == 409
    chat = world.client.post(f"/jobs/{job_id}/messages", headers=customer.headers, json={"body": "hello?"})
    assert chat.status_code == 409


def test_an_offer_the_artisan_already_accepted_never_expires(world, session_factory):
    customer, artisan, job_id = _offer(world, "TODAY")
    assert world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers).status_code == 200
    _age(session_factory, job_id, days=30)
    job = _job(world, customer, job_id)
    assert job["status"] == "REQUESTED" and job["artisan_agreed"] is True and job["offer_expires_at"] is None


def test_default_urgency_is_not_urgent_and_the_deadline_is_five_days(world):
    customer, artisan, job_id = _offer(world, "NOT_URGENT")
    job = _job(world, customer, job_id)
    created = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(job["offer_expires_at"].replace("Z", "+00:00"))
    assert abs((deadline.replace(tzinfo=timezone.utc) - created.replace(tzinfo=timezone.utc)) - timedelta(days=5)) < timedelta(seconds=2)


def test_invalid_urgency_is_rejected_and_the_admin_sweep_expires_overdue_offers(world, session_factory):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    bad = world.client.post("/service-requests", headers=customer.headers, json={
        "skill_id": skill_id, "description": "Fix the tap please", "location": "Small Soppo, Buea", "urgency": "ASAP"})
    assert bad.status_code == 422

    c1, a1, job1 = _offer(world, "TODAY")
    c2, a2, job2 = _offer(world, "NOT_URGENT")
    _age(session_factory, job1, hours=3)
    _age(session_factory, job2, days=1)
    assert world.client.post("/admin/expire-offers", headers=c1.headers).status_code == 403
    res = world.client.post("/admin/expire-offers", headers=world.admin.headers)
    assert res.status_code == 200 and res.json() == {"expired": 1}
    with session_factory() as db:
        assert db.get(Job, uuid.UUID(job1)).status == "CANCELLED"
        assert db.get(Job, uuid.UUID(job2)).status == "REQUESTED"
