import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Job, JobEvent
from tests.conftest import IS_POSTGRES


def _post(world, actor, path, **kwargs):
    return world.client.post(path, headers=actor.headers, **kwargs)


def test_valid_job_creation_and_acceptance(world):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), None
    john = world.artisan(skill_id)
    request_id = world.request(customer, skill_id)
    job_id = world.job(customer, john, request_id)

    job = world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()
    assert job["status"] == "REQUESTED" and job["counterpart_phone"] is None   # no contact details before acceptance

    res = _post(world, john, f"/jobs/{job_id}/accept")
    # Agreeing is not enough: the job is only ACCEPTED after the artisan pays the platform fee.
    assert res.status_code == 200 and res.json()["status"] == "REQUESTED"
    assert res.json()["payment_due"]["payment_type"] == "COMMISSION"
    accepted = world.accept(job_id, john)
    assert accepted["status"] == "ACCEPTED"
    assert accepted["counterpart_phone"] == customer.phone
    assert world.client.get(f"/service-requests/{request_id}", headers=customer.headers).json()["status"] == "MATCHED"


def test_customer_cannot_accept_and_artisan_cannot_create_job(world):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id)
    request_id = world.request(customer, skill_id)
    job_id = world.job(customer, john, request_id)
    assert _post(world, customer, f"/jobs/{job_id}/accept").status_code == 403
    assert _post(world, john, "/jobs", json={"request_id": request_id, "artisan_id": john.artisan_id,
                                             "proposed_price": 1}).status_code == 403


def test_other_artisan_cannot_accept_someone_elses_job(world):
    skill_id = world.skill()
    customer, john, rival = world.user("CUSTOMER"), world.artisan(skill_id), world.artisan(skill_id)
    job_id = world.job(customer, john, world.request(customer, skill_id))
    assert _post(world, rival, f"/jobs/{job_id}/accept").status_code == 403


def test_customer_cannot_hire_an_ineligible_artisan(world):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    unverified = world.artisan(skill_id, verified=False)
    request_id = world.request(customer, skill_id)
    res = _post(world, customer, "/jobs", json={"request_id": request_id, "artisan_id": unverified.artisan_id,
                                                "proposed_price": 5000})
    assert res.status_code == 400 and "SKILL_NOT_VERIFIED" in res.json()["detail"]


def test_one_job_per_request(world):
    skill_id = world.skill()
    customer, a, b = world.user("CUSTOMER"), world.artisan(skill_id), world.artisan(skill_id)
    request_id = world.request(customer, skill_id)
    world.job(customer, a, request_id)
    res = _post(world, customer, "/jobs", json={"request_id": request_id, "artisan_id": b.artisan_id, "proposed_price": 1})
    assert res.status_code == 409


@pytest.mark.parametrize("action", ["start", "confirm-completion"])
def test_invalid_transitions_rejected(world, action):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id)
    job_id = world.job(customer, john, world.request(customer, skill_id))
    # job is still REQUESTED: cannot start or complete it
    res = _post(world, john, f"/jobs/{job_id}/{action}")
    assert res.status_code == 409
    assert world.client.get(f"/jobs/{job_id}", headers=john.headers).json()["status"] == "REQUESTED"


def test_cannot_accept_twice_or_restart(world):
    customer, john, job_id = world.job_in_progress()
    assert _post(world, john, f"/jobs/{job_id}/accept").status_code == 409     # already in progress
    assert _post(world, john, f"/jobs/{job_id}/start").status_code == 409


def test_there_is_no_generic_status_update_endpoint(world):
    customer, john, job_id = world.job_in_progress()
    for method in ("put", "patch"):
        res = getattr(world.client, method)(f"/jobs/{job_id}", headers=customer.headers, json={"status": "COMPLETED"})
        assert res.status_code in (404, 405)
    assert world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()["status"] == "IN_PROGRESS"


def test_unrelated_users_cannot_confirm_or_view(world):
    customer, john, job_id = world.job_in_progress()
    stranger, other_artisan = world.user("CUSTOMER"), world.artisan(world.skill())
    for actor in (stranger, other_artisan):
        assert _post(world, actor, f"/jobs/{job_id}/confirm-completion").status_code == 403
        assert world.client.get(f"/jobs/{job_id}", headers=actor.headers).status_code == 403
    job = world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()
    assert job["status"] == "IN_PROGRESS" and not job["customer_confirmed"] and not job["artisan_confirmed"]


def test_one_confirmation_does_not_complete_the_job(world):
    customer, john, job_id = world.job_in_progress()
    res = _post(world, customer, f"/jobs/{job_id}/confirm-completion")
    body = res.json()
    assert res.status_code == 200
    assert body["status"] == "PENDING_CONFIRMATION"
    assert body["customer_confirmed"] is True and body["artisan_confirmed"] is False
    assert body["completed_at"] is None


def test_both_confirmations_complete_the_job_and_are_audited(world):
    customer, john, job_id = world.job_in_progress()
    _post(world, john, f"/jobs/{job_id}/confirm-completion")
    res = _post(world, customer, f"/jobs/{job_id}/confirm-completion")
    body = res.json()
    assert body["status"] == "COMPLETED" and body["completed_at"] is not None
    types = [e["event_type"] for e in body["events"]]
    assert types[0] == "JOB_REQUESTED" and types[-2:] == ["JOB_COMPLETED", "PAYOUT_RELEASED"]
    assert types.count("COMPLETION_CONFIRMED") == 2
    assert all(e["actor_id"] for e in body["events"])
    request_id = body["request_id"]
    assert world.client.get(f"/service-requests/{request_id}", headers=customer.headers).json()["status"] == "COMPLETED"


def test_duplicate_confirmation_is_idempotent(world):
    customer, john, job_id = world.job_in_progress()
    for _ in range(3):
        assert _post(world, customer, f"/jobs/{job_id}/confirm-completion").status_code == 200
    job = world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()
    assert job["status"] == "PENDING_CONFIRMATION"
    assert [e["event_type"] for e in job["events"]].count("COMPLETION_CONFIRMED") == 1   # no duplicate audit rows
    _post(world, john, f"/jobs/{job_id}/confirm-completion")
    _post(world, john, f"/jobs/{job_id}/confirm-completion")        # replay after completion
    job = world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()
    assert job["status"] == "COMPLETED"
    assert [e["event_type"] for e in job["events"]].count("JOB_COMPLETED") == 1


@pytest.mark.skipif(not IS_POSTGRES, reason="row-level locking needs PostgreSQL (TEST_DATABASE_URL)")
def test_simultaneous_confirmations_are_serialised(world):
    customer, john, job_id = world.job_in_progress()
    results = []
    def confirm(actor):
        results.append(world.client.post(f"/jobs/{job_id}/confirm-completion", headers=actor.headers).status_code)
    threads = [threading.Thread(target=confirm, args=(a,)) for a in (customer, john, customer, john, customer, john)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert set(results) == {200}
    job = world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()
    assert job["status"] == "COMPLETED"
    types = [e["event_type"] for e in job["events"]]
    assert types.count("COMPLETION_CONFIRMED") == 2 and types.count("JOB_COMPLETED") == 1


def test_cancel_and_dispute_flow(world):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id)
    job_id = world.job(customer, john, world.request(customer, skill_id))
    assert _post(world, customer, f"/jobs/{job_id}/cancel", json={"reason": "changed my mind"}).json()["status"] == "CANCELLED"
    assert _post(world, john, f"/jobs/{job_id}/accept").status_code == 409        # final state

    customer, john, job_id = world.job_in_progress()
    res = _post(world, customer, f"/jobs/{job_id}/dispute", json={"reason": "work was never finished"})
    assert res.json()["status"] == "DISPUTED"
    assert _post(world, customer, f"/jobs/{job_id}/confirm-completion").status_code == 409
    assert _post(world, customer, f"/admin/jobs/{job_id}/resolve-dispute",
                 json={"outcome": "CANCELLED", "notes": "no"}).status_code == 403          # not an admin
    resolved = _post(world, world.admin, f"/admin/jobs/{job_id}/resolve-dispute",
                     json={"outcome": "IN_PROGRESS", "notes": "artisan will return and finish"})
    assert resolved.json()["status"] == "IN_PROGRESS"


# ---- the database itself protects the audit trail and the completion rule ---------------------------
def test_job_events_are_append_only_at_database_level(world, session_factory):
    customer, john, job_id = world.completed_job()
    with session_factory() as db:
        event = db.query(JobEvent).first()
        event.event_type = "TAMPERED"
        with pytest.raises((DBAPIError, IntegrityError)):
            db.commit()
        db.rollback()
        with pytest.raises((DBAPIError, IntegrityError)):
            db.execute(text("DELETE FROM job_events"))
            db.commit()
        db.rollback()
        assert db.query(JobEvent).filter(JobEvent.event_type == "TAMPERED").count() == 0


def test_database_refuses_completed_job_without_both_confirmations(world, session_factory):
    customer, john, job_id = world.job_in_progress()
    with session_factory() as db:
        job = db.query(Job).one()
        job.status = "COMPLETED"       # bypassing the service layer on purpose
        with pytest.raises(IntegrityError):
            db.commit()


def test_database_refuses_negative_prices(world, session_factory):
    customer, john, job_id = world.job_in_progress()
    with session_factory() as db:
        db.query(Job).one().agreed_price = -5
        with pytest.raises(IntegrityError):
            db.commit()
