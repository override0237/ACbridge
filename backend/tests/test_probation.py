import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models import Job


@pytest.fixture(autouse=True)
def twenty_four_hour_probation(monkeypatch):
    monkeypatch.setattr(get_settings(), "probation_hours", 24)


def _post(world, actor, path, **kw):
    return world.client.post(path, headers=actor.headers, **kw)


def _job(world, actor, job_id):
    return world.client.get(f"/jobs/{job_id}", headers=actor.headers).json()


def _setup(world, needs_inspection=False):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id)
    request_id = world.request(customer, skill_id, needs_inspection=needs_inspection)
    return customer, john, world.job(customer, john, request_id, None if needs_inspection else 9000)


def _end_probation(session_factory, job_id):
    """Simulate 24 hours passing."""
    with session_factory() as db:
        db.query(Job).filter(Job.job_id == uuid.UUID(job_id)).one().probation_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()


def test_policy_publishes_probation_and_refund_rules(client):
    body = client.get("/pricing").json()
    assert body["probation_hours"] == 24
    assert "death" in body["refund_policy"] and "medical records" in body["refund_policy"]


def test_agreeing_starts_a_24_hour_probation_and_no_money_moves(world):
    customer, john, job_id = _setup(world)
    job = _post(world, john, f"/jobs/{job_id}/accept").json()
    assert job["status"] == "REQUESTED" and job["probation_active"] is True and job["can_cancel_freely"] is True
    assert job["payment_due"] is None and job["payments"] == []                  # nothing is charged yet
    started = datetime.fromisoformat(job["terms_agreed_at"])
    ends = datetime.fromisoformat(job["probation_ends_at"])
    assert ends - started == timedelta(hours=24)

    # the artisan's final confirmation and the customer's payment are both locked until it ends
    res = _post(world, john, f"/jobs/{job_id}/confirm-terms")
    assert res.status_code == 409 and "Cooling-off" in res.json()["detail"]
    assert _post(world, customer, f"/jobs/{job_id}/pay").status_code == 409

    again = _post(world, john, f"/jobs/{job_id}/accept").json()            # repeating does not extend it
    assert again["probation_ends_at"].rstrip("Z") == job["probation_ends_at"].rstrip("Z")   # same instant


def test_either_party_can_withdraw_for_free_during_probation(world):
    for withdrawing in ("customer", "artisan"):
        customer, john, job_id = _setup(world)
        _post(world, john, f"/jobs/{job_id}/accept")
        actor = customer if withdrawing == "customer" else john
        res = _post(world, actor, f"/jobs/{job_id}/cancel", json={"reason": "not sure any more"})
        assert res.status_code == 200 and res.json()["status"] == "CANCELLED"
        assert res.json()["payments"] == []                                  # free: nothing was ever charged
        cancelled = next(e for e in res.json()["events"] if e["event_type"] == "JOB_CANCELLED")
        assert cancelled["event_metadata"]["during_probation"] is True


def test_after_probation_artisan_confirms_and_pays_then_job_is_committed(world, session_factory):
    customer, john, job_id = _setup(world)
    _post(world, john, f"/jobs/{job_id}/accept")
    _end_probation(session_factory, job_id)

    due = _post(world, john, f"/jobs/{job_id}/confirm-terms").json()["payment_due"]
    assert (due["payment_type"], due["amount"]) == ("COMMISSION", 450)
    world.approve(due["payment_id"], john)
    job = _job(world, john, job_id)
    assert job["status"] == "ACCEPTED" and job["probation_active"] is False and job["can_cancel_freely"] is False

    # committed: neither party can simply cancel any more
    for actor in (customer, john):
        res = _post(world, actor, f"/jobs/{job_id}/cancel", json={})
        assert res.status_code == 409 and "hardship" in res.json()["detail"]
    world.fund(job_id, customer)
    assert _post(world, customer, f"/jobs/{job_id}/cancel", json={}).status_code == 409
    assert _post(world, john, f"/jobs/{job_id}/start").status_code == 200
    assert _post(world, john, f"/jobs/{job_id}/cancel", json={}).status_code == 409
    assert _job(world, john, job_id)["payments"][0]["status"] in ("SUCCEEDED",)   # fee was not refunded


def test_inspection_job_probation_starts_when_the_quote_is_approved(world, session_factory):
    customer, john, job_id = _setup(world, needs_inspection=True)
    due = _post(world, john, f"/jobs/{job_id}/accept").json()["payment_due"]     # assignment fee: no probation yet
    assert due["payment_type"] == "ASSIGNMENT_FEE"
    world.approve(due["payment_id"], john)
    job = _job(world, john, job_id)
    assert job["status"] == "ACCEPTED" and job["probation_ends_at"] is None

    _post(world, john, f"/jobs/{job_id}/quote", json={"amount": 15000})
    approved = _post(world, customer, f"/jobs/{job_id}/quote/respond", json={"approve": True}).json()
    assert approved["agreed_price"] == 15000 and approved["probation_active"] is True

    assert _post(world, customer, f"/jobs/{job_id}/pay").status_code == 409     # locked during probation
    _end_probation(session_factory, job_id)
    assert _post(world, customer, f"/jobs/{job_id}/pay").status_code == 201


def test_inspection_withdrawal_does_not_refund_the_assignment_fee(world):
    customer, john, job_id = _setup(world, needs_inspection=True)
    world.accept(job_id, john)                                                    # fee paid
    res = _post(world, customer, f"/jobs/{job_id}/cancel", json={"reason": "found another artisan"})
    assert res.json()["status"] == "CANCELLED"
    fee = res.json()["payments"]
    assert fee == [] or all(p["status"] != "REFUNDED" for p in fee)               # fee is never refunded here
    payments = _post(world, john, f"/jobs/{job_id}/accept")                      # job is cancelled: cannot reopen
    assert payments.status_code == 409


def test_skip_probation_is_an_admin_only_simulation_tool(world):
    customer, john, job_id = _setup(world)
    _post(world, john, f"/jobs/{job_id}/accept")
    assert _post(world, customer, f"/admin/jobs/{job_id}/skip-probation").status_code == 403
    assert _post(world, john, f"/admin/jobs/{job_id}/skip-probation").status_code == 403
    res = _post(world, world.admin, f"/admin/jobs/{job_id}/skip-probation")
    assert res.status_code == 200 and res.json()["probation_active"] is False
    assert "PROBATION_SKIPPED" in [e["event_type"] for e in res.json()["events"]]
    assert _post(world, john, f"/jobs/{job_id}/confirm-terms").status_code == 200
