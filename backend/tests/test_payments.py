import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Job, Payment
from app.services.payment_service import compute_commission


def _post(world, actor, path, **kw):
    return world.client.post(path, headers=actor.headers, **kw)


def _get_job(world, actor, job_id):
    return world.client.get(f"/jobs/{job_id}", headers=actor.headers).json()


def _types(world, actor, job_id):
    return [e["event_type"] for e in _get_job(world, actor, job_id)["events"]]


def _setup(world, needs_inspection=False, price=9000):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id)
    request_id = world.request(customer, skill_id, needs_inspection=needs_inspection)
    job_id = world.job(customer, john, request_id, None if needs_inspection else price)
    return customer, john, job_id


# ------------------------------------------------------------------ fee policy / commission maths
def test_commission_calculation(monkeypatch):
    assert compute_commission(9000) == 450            # 5%
    assert compute_commission(100_000) == 5000
    assert compute_commission(2000) == 300            # 5% = 100, below the 300 minimum
    assert compute_commission(1) == 300


def test_public_pricing_policy_is_transparent(client):
    body = client.get("/pricing").json()
    assert body["fixed_price_commission_percent"] == 5.0 and body["fixed_price_commission_minimum"] == 300
    assert body["inspection_assignment_fee"] == 1000 and body["fees_paid_by"] == "ARTISAN"
    assert body["provider"] == "SIMULATED" and "no real money" in body["notice"]


# ------------------------------------------------------------------ fixed-price flow
def test_artisan_pays_commission_after_agreeing_to_the_amount(world):
    customer, john, job_id = _setup(world, price=9000)
    body = _post(world, john, f"/jobs/{job_id}/accept").json()
    assert body["status"] == "REQUESTED"                          # NOT assigned until the fee is paid
    assert body["artisan_agreed"] is True and body["agreed_price"] == 9000
    due = world.fee_due(job_id, john)
    assert (due["payment_type"], due["amount"], due["status"]) == ("COMMISSION", 450, "PENDING")
    assert due["simulated"] is True
    # the customer cannot see the artisan's commission or pay it
    assert _get_job(world, customer, job_id)["payment_due"] is None
    assert _post(world, customer, f"/payments/{due['payment_id']}/simulate-approval").status_code == 404

    world.approve(due["payment_id"], john)
    job = _get_job(world, john, job_id)
    assert job["status"] == "ACCEPTED" and job["payment_due"] is None
    assert _types(world, john, job_id)[-2:] == ["PAYMENT_SUCCEEDED", "JOB_ACCEPTED"]


def test_failed_fee_payment_can_be_retried(world):
    customer, john, job_id = _setup(world)
    first = world.fee_due(job_id, john)
    failed = _post(world, john, f"/payments/{first['payment_id']}/simulate-failure").json()
    assert failed["status"] == "FAILED"
    assert _get_job(world, john, job_id)["status"] == "REQUESTED"          # still not assigned
    retry = _post(world, john, f"/jobs/{job_id}/confirm-terms").json()["payment_due"]
    assert retry["payment_id"] != first["payment_id"] and retry["status"] == "PENDING"
    world.approve(retry["payment_id"], john)
    assert _get_job(world, john, job_id)["status"] == "ACCEPTED"


def test_accept_is_idempotent_no_double_charge(world):
    customer, john, job_id = _setup(world)
    a = world.fee_due(job_id, john)
    b = _post(world, john, f"/jobs/{job_id}/confirm-terms").json()["payment_due"]
    _post(world, john, f"/jobs/{job_id}/accept")             # repeating accept restarts nothing
    assert a["payment_id"] == b["payment_id"]
    types = _types(world, john, job_id)
    assert types.count("TERMS_AGREED_BY_ARTISAN") == 1 and types.count("TERMS_CONFIRMED_BY_ARTISAN") == 1


def test_settling_twice_changes_nothing(world):
    customer, john, job_id = _setup(world)
    due = world.fee_due(job_id, john)
    world.approve(due["payment_id"], john)
    world.approve(due["payment_id"], john)               # duplicate callback
    assert _types(world, john, job_id).count("PAYMENT_SUCCEEDED") == 1


def test_only_the_payer_can_settle_a_payment(world):
    customer, john, job_id = _setup(world)
    due = world.fee_due(job_id, john)
    stranger = world.user("CUSTOMER")
    for actor in (customer, stranger):
        assert _post(world, actor, f"/payments/{due['payment_id']}/simulate-approval").status_code == 404
    assert _get_job(world, john, job_id)["status"] == "REQUESTED"


# ------------------------------------------------------------------ escrow
def test_work_cannot_start_until_customer_has_paid_into_escrow(world):
    customer, john, job_id = _setup(world)
    world.accept(job_id, john)
    res = _post(world, john, f"/jobs/{job_id}/start")
    assert res.status_code == 409 and "escrow" in res.json()["detail"]
    pay = _post(world, customer, f"/jobs/{job_id}/pay")
    assert pay.status_code == 201 and pay.json()["amount"] == 9000 and pay.json()["payment_type"] == "JOB_PAYMENT"
    assert _post(world, john, f"/jobs/{job_id}/start").status_code == 409     # pending is not enough
    world.approve(pay.json()["payment_id"], customer)
    assert _get_job(world, john, job_id)["escrow_status"] == "HELD"
    assert _post(world, john, f"/jobs/{job_id}/start").status_code == 200


def test_paying_twice_returns_the_same_payment(world):
    customer, john, job_id = _setup(world)
    world.accept(job_id, john)
    a = _post(world, customer, f"/jobs/{job_id}/pay").json()
    b = _post(world, customer, f"/jobs/{job_id}/pay").json()
    assert a["payment_id"] == b["payment_id"]


def test_customer_cannot_pay_before_acceptance_and_artisan_cannot_pay(world):
    customer, john, job_id = _setup(world)
    assert _post(world, customer, f"/jobs/{job_id}/pay").status_code == 409
    world.accept(job_id, john)
    assert _post(world, john, f"/jobs/{job_id}/pay").status_code == 403


def test_escrow_is_released_to_the_artisan_only_after_both_confirm(world):
    customer, john, job_id = _setup(world)
    world.work_started(customer, john, job_id)
    _post(world, customer, f"/jobs/{job_id}/confirm-completion")
    assert _get_job(world, john, job_id)["escrow_status"] == "HELD"          # one side only: still held
    _post(world, john, f"/jobs/{job_id}/confirm-completion")
    job = _get_job(world, john, job_id)
    assert job["status"] == "COMPLETED" and job["escrow_status"] == "RELEASED"
    assert _types(world, john, job_id)[-1] == "PAYOUT_RELEASED"


def test_cancelling_before_commitment_voids_a_pending_fee(world):
    customer, john, job_id = _setup(world)
    due = world.fee_due(job_id, john)                    # fee charged but not yet approved
    assert _post(world, customer, f"/jobs/{job_id}/cancel", json={}).json()["status"] == "CANCELLED"
    assert _post(world, john, f"/payments/{due['payment_id']}/simulate-approval").status_code == 200   # no-op
    job = _get_job(world, john, job_id)
    assert job["status"] == "CANCELLED" and job["payment_due"] is None


def test_dispute_cancelled_by_admin_refunds_the_customer(world):
    customer, john, job_id = world.job_in_progress()
    _post(world, customer, f"/jobs/{job_id}/dispute", json={"reason": "work never finished"})
    assert _get_job(world, customer, job_id)["escrow_status"] == "HELD"       # stays held during a dispute
    res = _post(world, world.admin, f"/admin/jobs/{job_id}/resolve-dispute",
                json={"outcome": "CANCELLED", "notes": "refund the customer"})
    assert res.json()["escrow_status"] == "REFUNDED"


# ------------------------------------------------------------------ inspection flow
def test_inspection_job_flow_assignment_fee_then_quote(world):
    customer, john, job_id = _setup(world, needs_inspection=True)
    job = _get_job(world, customer, job_id)
    assert job["pricing_mode"] == "INSPECTION_REQUIRED" and job["agreed_price"] is None

    due = _post(world, john, f"/jobs/{job_id}/accept").json()["payment_due"]
    assert (due["payment_type"], due["amount"]) == ("ASSIGNMENT_FEE", 1000)    # flat, whatever the final price
    world.approve(due["payment_id"], john)
    job = _get_job(world, john, job_id)
    assert job["status"] == "ACCEPTED" and job["agreed_price"] is None

    # no price yet => cannot pay or start
    assert _post(world, customer, f"/jobs/{job_id}/pay").status_code == 409
    assert _post(world, john, f"/jobs/{job_id}/start").status_code == 409

    assert _post(world, customer, f"/jobs/{job_id}/quote", json={"amount": 15000}).status_code == 403  # not the artisan
    quoted = _post(world, john, f"/jobs/{job_id}/quote", json={"amount": 15000}).json()
    assert quoted["proposed_price"] == 15000 and quoted["proposed_by"] == "ARTISAN" and quoted["agreed_price"] is None
    assert _post(world, john, f"/jobs/{job_id}/quote/respond", json={"approve": True}).status_code == 403

    # customer rejects, artisan re-quotes, customer approves
    _post(world, customer, f"/jobs/{job_id}/quote/respond", json={"approve": False})
    assert _get_job(world, customer, job_id)["proposed_price"] is None
    _post(world, john, f"/jobs/{job_id}/quote", json={"amount": 12000})
    approved = _post(world, customer, f"/jobs/{job_id}/quote/respond", json={"approve": True}).json()
    assert approved["agreed_price"] == 12000

    world.fund(job_id, customer)
    assert _post(world, john, f"/jobs/{job_id}/start").status_code == 200
    world.complete(customer, john, job_id)
    job = _get_job(world, john, job_id)
    assert job["status"] == "COMPLETED" and job["escrow_status"] == "RELEASED"
    payments = {p["payment_type"]: p for p in job["payments"]}
    assert payments["JOB_PAYMENT"]["amount"] == 12000


def test_inspection_rules_on_job_creation(world):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id)
    needs = world.request(customer, skill_id, needs_inspection=True)
    normal = world.request(customer, skill_id)
    body = lambda rid, price: {"request_id": rid, "artisan_id": john.artisan_id, "proposed_price": price}
    assert _post(world, customer, "/jobs", json=body(needs, 5000)).status_code == 400   # price too early
    assert _post(world, customer, "/jobs", json=body(normal, None)).status_code == 400  # price required
    assert _post(world, customer, "/jobs", json=body(normal, 0)).status_code == 422     # must be positive


def test_quote_not_allowed_on_fixed_price_job(world):
    customer, john, job_id = _setup(world)
    world.accept(job_id, john)
    assert _post(world, john, f"/jobs/{job_id}/quote", json={"amount": 5000}).status_code == 409


# ------------------------------------------------------------------ database guarantees
def test_database_allows_only_one_active_payment_per_type(world, session_factory):
    customer, john, job_id = _setup(world)
    world.fee_due(job_id, john)
    with session_factory() as db:
        existing = db.query(Payment).one()
        db.add(Payment(job_id=existing.job_id, payer_id=existing.payer_id, payment_type=existing.payment_type,
                       amount=450, provider="SIMULATED"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_database_refuses_started_job_without_a_price(world, session_factory):
    customer, john, job_id = _setup(world, needs_inspection=True)
    with session_factory() as db:
        db.query(Job).one().status = "IN_PROGRESS"
        with pytest.raises(IntegrityError):
            db.commit()


def test_database_refuses_non_positive_payment(world, session_factory):
    customer, john, job_id = _setup(world)
    with session_factory() as db:
        job = db.query(Job).one()
        db.add(Payment(job_id=job.job_id, payer_id=customer.user_id, payment_type="JOB_PAYMENT", amount=0,
                       provider="SIMULATED"))
        with pytest.raises(IntegrityError):
            db.commit()
