"""Secure payments module: double-entry ledger, payouts, signed webhooks, idempotency, reconciliation.

Most tests run in the CUSTOMER-SPLIT model (the commission is cut from the customer's payment the moment it succeeds).
One test runs the default artisan-upfront model to show the ledger balances there too.
"""
import json

import pytest

from app.config import get_settings
from app.services import ledger_service
from app.services.payment_providers import sign_webhook
from app.services.payment_service import compute_commission
from app.services.privacy import mask_phone


@pytest.fixture
def split(monkeypatch):
    monkeypatch.setenv("COMMISSION_MODEL", "customer_split")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _paid_job(world, price=6000, approve=True):
    """Customer proposes `price`, artisan agrees and confirms (job ACCEPTED), customer starts the payment."""
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    artisan = world.artisan(skill_id, "John Fon")
    job_id = world.job(customer, artisan, world.request(customer, skill_id), price=price)
    assert world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers).status_code == 200
    res = world.client.post(f"/jobs/{job_id}/confirm-terms", headers=artisan.headers)
    assert res.status_code == 200 and res.json()["status"] == "ACCEPTED", res.text   # no artisan fee in this model
    pay = world.client.post(f"/jobs/{job_id}/pay", headers={**customer.headers, "Idempotency-Key": "key-1"})
    assert pay.status_code == 201, pay.text
    payment = pay.json()
    if approve:
        world.approve(payment["payment_id"], customer)
    return customer, artisan, job_id, payment


def _ledger(world):
    return world.client.get("/operator/ledger", headers=world.admin.headers).json()


def _webhook(world, body: dict, signature: str | None = "auto", provider="simulated"):
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if signature == "auto":
        headers["X-Signature"] = sign_webhook(raw)
    elif signature is not None:
        headers["X-Signature"] = signature
    return world.client.post(f"/webhooks/payments/{provider}", content=raw, headers=headers)


# ------------------------------------------------------------------ 1. commission calculation
def test_commission_is_integer_rate_with_a_minimum():
    assert compute_commission(6000) == 300          # 5% (the configured rate), integer FCFA
    assert compute_commission(9999) == 499          # integer arithmetic: floors, never a fraction
    assert compute_commission(2000) == 300          # the minimum applies to small jobs
    assert all(isinstance(compute_commission(p), int) for p in (500, 1234, 6000, 1_000_000))


# ------------------------------------------------------------------ 2. ledger balance + 3rd/2nd acceptance criteria
def test_customer_payment_books_commission_at_once_and_holds_the_artisan_share(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    ledger = _ledger(world)
    b = ledger["balances"]
    assert b["collection"] == 6000
    assert b["platform_revenue"] == 300                     # commission recorded immediately
    assert b["artisan_pending"] == 5700                     # the artisan's share is only pending...
    assert b["artisan_paid"] == 0                           # ...and not paid before completion
    assert ledger["balanced"] is True and ledger["unbalanced_transactions"] == []
    debit = sum(e["amount"] for e in ledger["entries"] if e["direction"] == "DEBIT")
    credit = sum(e["amount"] for e in ledger["entries"] if e["direction"] == "CREDIT")
    assert debit == credit == 6000


def test_every_money_event_is_balanced_through_the_whole_life_of_a_job(world, split, session_factory):
    customer, artisan, job_id, payment = _paid_job(world, price=8000)
    for who in (artisan, customer):                         # start, then both confirm -> payout is paid
        if who is artisan:
            assert world.client.post(f"/jobs/{job_id}/start", headers=artisan.headers).status_code == 200
        assert world.client.post(f"/jobs/{job_id}/confirm-completion", headers=who.headers).status_code == 200
    assert world.client.post(f"/jobs/{job_id}/confirm-completion", headers=artisan.headers).status_code == 200
    ledger = _ledger(world)
    assert ledger["balanced"] is True
    assert ledger["balances"]["artisan_pending"] == 0 and ledger["balances"]["artisan_paid"] == 7600
    with session_factory() as db:
        assert ledger_service.unbalanced_transactions(db) == []


def test_the_ledger_also_balances_in_the_default_artisan_upfront_model(world):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    artisan = world.artisan(skill_id, "John Fon")
    job_id = world.job(customer, artisan, world.request(customer, skill_id), price=9000)
    world.accept(job_id, artisan)                               # artisan pays the commission up front
    pay = world.client.post(f"/jobs/{job_id}/pay", headers=customer.headers).json()
    world.approve(pay["payment_id"], customer)
    ledger = _ledger(world)
    assert ledger["balanced"] is True
    assert ledger["balances"]["platform_revenue"] == compute_commission(9000)   # booked when the artisan paid
    assert ledger["balances"]["artisan_pending"] == 9000                        # the customer's full price is the share


# ------------------------------------------------------------------ 3. idempotency
def test_same_idempotency_key_creates_one_payment_and_one_set_of_entries(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    again = world.client.post(f"/jobs/{job_id}/pay", headers={**customer.headers, "Idempotency-Key": "key-1"})
    assert again.status_code == 201 and again.json()["payment_id"] == payment["payment_id"]
    other = world.client.post(f"/jobs/{job_id}/pay", headers={**customer.headers, "Idempotency-Key": "key-2"})
    assert other.json()["payment_id"] == payment["payment_id"]     # still one live payment per job
    payments = world.client.get("/operator/payments", headers=world.admin.headers).json()
    assert len([p for p in payments if p["job_id"] == job_id]) == 1
    assert _ledger(world)["balances"]["collection"] == 6000


def test_an_idempotency_key_cannot_be_reused_for_another_job(world, split):
    customer, artisan, job_id, payment = _paid_job(world)
    skill_id = world.skill()
    artisan2 = world.artisan(skill_id, "Other")
    job2 = world.job(customer, artisan2, world.request(customer, skill_id), price=5000)
    world.client.post(f"/jobs/{job2}/accept", headers=artisan2.headers)
    world.client.post(f"/jobs/{job2}/confirm-terms", headers=artisan2.headers)
    res = world.client.post(f"/jobs/{job2}/pay", headers={**customer.headers, "Idempotency-Key": "key-1"})
    assert res.status_code == 409


# ------------------------------------------------------------------ 4. quote lock and expiry
def test_agreed_price_is_frozen_and_the_amount_never_comes_from_the_request(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    assert payment["amount"] == 6000
    # a tampered body is ignored: the amount is read from the job in the database
    res = world.client.post(f"/jobs/{job_id}/pay", headers=customer.headers, json={"amount": 1})
    assert res.json()["amount"] == 6000
    job = world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()
    assert job["agreed_price"] == 6000
    # no endpoint changes an agreed price: a chat message cannot reopen it either
    chat = world.client.post(f"/jobs/{job_id}/messages", headers=artisan.headers, json={"body": "now 7000 FCFA"})
    assert chat.status_code == 409                       # the job is paid, so the chat is closed and cannot reopen the price
    assert world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()["agreed_price"] == 6000


def test_an_expired_price_proposal_cannot_be_accepted(world, split, session_factory):
    from datetime import datetime, timedelta, timezone
    from app.models import Job
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    artisan = world.artisan(skill_id, "John Fon")
    job_id = world.job(customer, artisan, world.request(customer, skill_id, urgency="TODAY"), price=6000)
    with session_factory() as db:
        job = db.get(Job, job_id if not isinstance(job_id, str) else __import__("uuid").UUID(job_id))
        job.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
    res = world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers)
    assert res.status_code == 409 and "expired" in res.json()["detail"]
    assert world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()["status"] == "CANCELLED"


# ------------------------------------------------------------------ 5. webhook security
def test_a_webhook_with_a_bad_or_missing_signature_is_refused_and_changes_nothing(world, split):
    customer, artisan, job_id, payment = _paid_job(world, approve=False)
    ref = world.client.get(f"/payments/{payment['payment_id']}", headers=customer.headers).json()
    body = {"event_id": "evt-1", "provider_reference": _reference(world, payment), "status": "SUCCEEDED"}
    assert _webhook(world, body, signature="deadbeef").status_code == 401
    assert _webhook(world, body, signature=None).status_code == 401
    after = world.client.get(f"/payments/{payment['payment_id']}", headers=customer.headers).json()
    assert after["status"] == "PENDING" and ref["status"] == "PENDING"
    assert _ledger(world)["balances"]["collection"] == 0


def _reference(world, payment):
    rows = world.client.get("/operator/payments", headers=world.admin.headers).json()
    return next(p["provider_reference"] for p in rows if p["payment_id"] == payment["payment_id"])


# ------------------------------------------------------------------ 6. webhook replay
def test_a_signed_webhook_marks_the_payment_succeeded_and_a_replay_does_not_double_credit(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000, approve=False)
    body = {"event_id": "evt-9", "provider_reference": _reference(world, payment), "status": "SUCCEEDED"}
    first = _webhook(world, body)
    assert first.status_code == 200 and first.json()["status"] == "processed"
    assert world.client.get(f"/payments/{payment['payment_id']}", headers=customer.headers).json()["status"] == "SUCCEEDED"
    snapshot = _ledger(world)
    assert snapshot["balances"]["platform_revenue"] == 300

    replay = _webhook(world, body)                                         # same event id
    assert replay.status_code == 200 and replay.json()["status"] == "duplicate"
    again = _webhook(world, {**body, "event_id": "evt-10"})                # new event id, payment already settled
    assert again.status_code == 200
    after = _ledger(world)
    assert after["balances"] == snapshot["balances"] and len(after["entries"]) == len(snapshot["entries"])


def test_a_failed_webhook_marks_the_payment_failed_and_books_nothing(world, split):
    customer, artisan, job_id, payment = _paid_job(world, approve=False)
    body = {"event_id": "evt-f", "provider_reference": _reference(world, payment), "status": "FAILED"}
    assert _webhook(world, body).status_code == 200
    assert world.client.get(f"/payments/{payment['payment_id']}", headers=customer.headers).json()["status"] == "FAILED"
    assert _ledger(world)["entries"] == []


# ------------------------------------------------------------------ 7. payout hold / release rules
def _complete(world, customer, artisan, job_id):
    assert world.client.post(f"/jobs/{job_id}/start", headers=artisan.headers).status_code == 200
    for who in (artisan, customer):
        assert world.client.post(f"/jobs/{job_id}/confirm-completion", headers=who.headers).status_code == 200


def _payout(world, job_id):
    rows = world.client.get("/operator/payouts", headers=world.admin.headers).json()
    return next(p for p in rows if p["job_id"] == job_id)


def test_payout_waits_for_completion_then_is_paid_and_moves_in_the_ledger(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    assert _payout(world, job_id)["status"] == "PENDING" and _payout(world, job_id)["amount"] == 5700
    # an operator cannot release before the job is confirmed complete
    early = world.client.post(f"/operator/payouts/{_payout(world, job_id)['payout_id']}/release",
                              headers=world.admin.headers, json={"reason": "please pay early"})
    assert early.status_code == 409
    _complete(world, customer, artisan, job_id)
    paid = _payout(world, job_id)
    assert paid["status"] == "PAID" and paid["provider_reference"].startswith("SIM-PAYOUT")
    b = _ledger(world)["balances"]
    assert b["artisan_pending"] == 0 and b["artisan_paid"] == 5700 and b["platform_revenue"] == 300


def test_a_dispute_holds_the_payout_and_a_held_payout_cannot_be_released_while_disputed(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    assert world.client.post(f"/jobs/{job_id}/start", headers=artisan.headers).status_code == 200
    assert world.client.post(f"/jobs/{job_id}/dispute", headers=customer.headers, json={"reason": "work is bad"}).status_code == 200
    payout = _payout(world, job_id)
    assert payout["status"] == "HELD" and payout["note"].startswith("dispute")
    res = world.client.post(f"/operator/payouts/{payout['payout_id']}/release", headers=world.admin.headers,
                            json={"reason": "release it anyway"})
    assert res.status_code == 409 and "dispute" in res.json()["detail"]
    assert _ledger(world)["balances"]["artisan_paid"] == 0


def test_operator_hold_and_release_need_a_reason_and_are_audited(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    payout_id = _payout(world, job_id)["payout_id"]
    assert world.client.post(f"/operator/payouts/{payout_id}/hold", headers=world.admin.headers, json={}).status_code == 422
    assert world.client.post(f"/operator/payouts/{payout_id}/hold", headers=world.admin.headers, json={"reason": "no"}).status_code == 422
    held = world.client.post(f"/operator/payouts/{payout_id}/hold", headers=world.admin.headers,
                             json={"reason": "customer reported a problem"})
    assert held.status_code == 200 and held.json()["status"] == "HELD"
    # completion while held does not pay
    _complete(world, customer, artisan, job_id)
    assert _payout(world, job_id)["status"] == "HELD" and _ledger(world)["balances"]["artisan_paid"] == 0
    released = world.client.post(f"/operator/payouts/{payout_id}/release", headers=world.admin.headers,
                                 json={"reason": "problem solved, job confirmed"})
    assert released.status_code == 200 and released.json()["status"] == "PAID"
    assert _ledger(world)["balances"]["artisan_paid"] == 5700
    # customers and artisans cannot use the operator endpoints
    assert world.client.get("/operator/payouts", headers=customer.headers).status_code == 403
    assert world.client.post(f"/operator/payouts/{payout_id}/hold", headers=artisan.headers,
                             json={"reason": "i am the artisan"}).status_code == 403
    # every action is in the audit log as a hash, never the raw payload
    audit = world.client.get("/operator/audit", headers=world.admin.headers).json()
    actions = [a["action"] for a in audit]
    assert "PAYOUT_HELD" in actions and "PAYOUT_RELEASE_REQUESTED" in actions and "PAYMENT_SUCCEEDED" in actions
    assert all(len(a["payload_hash"]) == 64 for a in audit)


# ------------------------------------------------------------------ 8. unlock rule
def test_contact_details_stay_hidden_until_the_payment_has_succeeded(world, split):
    customer, artisan, job_id, payment = _paid_job(world, approve=False)
    for who in (customer, artisan):
        job = world.client.get(f"/jobs/{job_id}", headers=who.headers).json()
        assert job["counterpart_phone"] is None and job["counterpart_whatsapp_link"] is None
    # starting work is also locked until the payment succeeded
    assert world.client.post(f"/jobs/{job_id}/start", headers=artisan.headers).status_code == 409
    world.approve(payment["payment_id"], customer)
    assert world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()["counterpart_phone"] == artisan_phone(world, artisan)
    assert world.client.get(f"/jobs/{job_id}", headers=artisan.headers).json()["counterpart_phone"] == customer.phone


def artisan_phone(world, artisan):
    return artisan.phone


def test_phone_numbers_are_masked_in_operator_views():
    assert mask_phone("+237670123456") == "+237 6******56"
    assert "670123456" not in mask_phone("+237670123456")


# ------------------------------------------------------------------ 9. reconciliation
def test_reconciliation_is_clean_for_a_normal_flow_and_flags_a_mismatch(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    _complete(world, customer, artisan, job_id)
    clean = world.client.get("/operator/reconciliation", headers=world.admin.headers).json()
    assert clean["status"] == "OK" and clean["mismatch"] is False
    assert clean["differences"] == {"collected": 0, "disbursed": 0, "refunds": 0}
    assert clean["provider"]["collected"] == 6000 and clean["provider"]["disbursed"] == 5700

    bad = world.client.get("/operator/reconciliation", params={"provider_collected_override": 6500},
                           headers=world.admin.headers).json()
    assert bad["status"] == "MISMATCH" and bad["mismatch"] is True and bad["differences"]["collected"] == 500


def test_reconciliation_flags_completed_jobs_that_were_never_paid_through_the_app(world, split, session_factory):
    from app.models import Job
    customer, artisan, job_id, payment = _paid_job(world, price=6000, approve=False)   # never paid
    with session_factory() as db:                                                       # force a completed, unpaid job
        job = db.get(Job, __import__("uuid").UUID(job_id))
        job.status, job.customer_confirmed, job.artisan_confirmed = "COMPLETED", True, True
        from datetime import datetime, timezone
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    flagged = world.client.get("/operator/reconciliation", headers=world.admin.headers).json()["completed_jobs_without_payment"]
    assert flagged and flagged[0]["artisan_name"] == "John Fon" and flagged[0]["jobs"] == 1


# ------------------------------------------------------------------ security extras
def test_starting_payments_is_rate_limited_per_phone_number(world, split, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("PAY_RATE_LIMIT_CALLS", "3")
    get_settings.cache_clear()
    from app.security.rate_limit import reset_rate_limits
    reset_rate_limits()
    customer, artisan, job_id, payment = _paid_job(world)       # call 1
    statuses = [world.client.post(f"/jobs/{job_id}/pay", headers=customer.headers).status_code for _ in range(4)]
    assert statuses[:2] == [201, 201] and statuses[2] == 429    # the 4th call in total is refused
    reset_rate_limits()


def test_refund_requests_are_recorded_in_refund_payable_and_stay_balanced(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000)
    assert world.client.post(f"/jobs/{job_id}/cancel", headers=customer.headers, json={"reason": "changed my mind"}).status_code in (200, 409)
    # cancelling is only free before commitment; use the dispute path to cancel an escrowed job
    assert world.client.post(f"/jobs/{job_id}/start", headers=artisan.headers).status_code == 200
    assert world.client.post(f"/jobs/{job_id}/dispute", headers=customer.headers, json={"reason": "no show"}).status_code == 200
    res = world.client.post(f"/admin/jobs/{job_id}/resolve-dispute", headers=world.admin.headers,
                            json={"outcome": "CANCELLED", "notes": "artisan never came, refund the customer"})
    assert res.status_code == 200
    ledger = _ledger(world)
    assert ledger["balanced"] is True
    assert ledger["balances"]["refund_payable"] == 6000
    assert ledger["balances"]["artisan_pending"] == 0 and ledger["balances"]["platform_revenue"] == 0
    assert _payout(world, job_id)["status"] == "FAILED"


def test_the_chat_closes_once_the_customers_payment_has_gone_through(world, split):
    customer, artisan, job_id, payment = _paid_job(world, price=6000, approve=False)
    # before the payment succeeds the parties can still talk
    assert world.client.post(f"/jobs/{job_id}/messages", headers=customer.headers, json={"body": "see you soon"}).status_code == 201
    world.approve(payment["payment_id"], customer)                      # the app now holds the money
    for who in (customer, artisan):
        res = world.client.post(f"/jobs/{job_id}/messages", headers=who.headers, json={"body": "one more thing"})
        assert res.status_code == 409 and "payment has been received" in res.json()["detail"]
    history = world.client.get(f"/jobs/{job_id}/messages", headers=customer.headers).json()   # but the history stays readable
    assert [m["body"] for m in history] == ["see you soon"]
