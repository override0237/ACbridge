import re
import smtplib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models import Endorsement, TradeGroup, TradeGroupVouch
from app.services import email_service
from app.services.email_service import OUTBOX


def _post(world, actor, path, **kw):
    return world.client.post(path, headers=actor.headers, **kw)


def _token(email=None):
    """Extract the single-use token from the latest simulated e-mail (to `email` if given)."""
    mails = [m for m in OUTBOX if email is None or m.to == email]
    assert mails, "no e-mail was sent"
    return re.search(r"token=([A-Za-z0-9_\-]+)", mails[-1].body).group(1)


def _group(world, name="Buea Electricians Association", email="contact@buea-electricians.example"):
    """Admin registers the group; someone at that address confirms the e-mail -> ACTIVE."""
    res = _post(world, world.admin, "/admin/trade-groups", json={"name": name, "email": email, "description": "Guild"})
    assert res.status_code == 201, res.text
    token = _token(email)
    assert world.client.post("/trade-groups/verify-email", json={"token": token}).status_code == 200
    return res.json()["group_id"]


def _ask(world, artisan, group_id, skill_id, note=None):
    return _post(world, artisan, f"/artisans/{artisan.artisan_id}/trade-group-vouches",
                 json={"group_id": group_id, "skill_id": skill_id, "note": note})


def _answer(world, token, decision="CONFIRM"):
    return world.client.post("/trade-group-vouches/respond", json={"token": token, "decision": decision})


def _skill_status(world, artisan, skill_id):
    skills = world.client.get(f"/artisans/{artisan.artisan_id}").json()["skills"]
    return next(s["verification_status"] for s in skills if s["skill_id"] == skill_id)


# ------------------------------------------------------------------ group onboarding by e-mail
def test_group_must_confirm_its_email_before_it_can_be_used(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    created = _post(world, world.admin, "/admin/trade-groups",
                    json={"name": "Molyko Masons", "email": "Boss@Masons.EXAMPLE", "description": "x"})
    assert created.status_code == 201
    group = created.json()
    assert group["status"] == "PENDING_EMAIL_VERIFICATION" and group["email"] == "boss@masons.example"
    assert group["email_status"] == "SENT"
    assert OUTBOX[-1].to == "boss@masons.example" and "Molyko Masons" in OUTBOX[-1].body

    # not usable and not listed until the address is confirmed
    assert world.client.get("/trade-groups").json() == []
    assert _ask(world, john, group["group_id"], skill_id).status_code == 404

    token = _token()
    assert world.client.post("/trade-groups/verify-email", json={"token": token}).status_code == 200
    listed = world.client.get("/trade-groups").json()
    assert [g["name"] for g in listed] == ["Molyko Masons"] and "email" not in listed[0]   # e-mail stays private
    assert world.client.post("/trade-groups/verify-email", json={"token": token}).status_code == 404   # single use


def test_only_admins_register_groups_and_duplicates_are_rejected(world):
    body = {"name": "Guild One", "email": "one@guild.example"}
    for actor in (world.user("CUSTOMER"), world.user("ARTISAN"), world.verifier):
        assert _post(world, actor, "/admin/trade-groups", json=body).status_code == 403
    assert _post(world, world.admin, "/admin/trade-groups", json=body).status_code == 201
    assert _post(world, world.admin, "/admin/trade-groups", json=body).status_code == 409
    assert _post(world, world.admin, "/admin/trade-groups",
                 json={"name": "Other", "email": "ONE@guild.example"}).status_code == 409
    assert _post(world, world.admin, "/admin/trade-groups", json={"name": "Bad", "email": "nope"}).status_code == 422


def test_invalid_expired_or_resent_group_links(world):
    assert world.client.post("/trade-groups/verify-email", json={"token": "x" * 40}).status_code == 404
    res = _post(world, world.admin, "/admin/trade-groups", json={"name": "Slow Guild", "email": "slow@guild.example"})
    group_id, old = res.json()["group_id"], _token()
    again = _post(world, world.admin, f"/admin/trade-groups/{group_id}/resend-verification")
    assert again.status_code == 200
    new = _token()
    assert new != old
    assert world.client.post("/trade-groups/verify-email", json={"token": old}).status_code == 404   # old link dead
    with world.factory() as db:
        db.get(TradeGroup, uuid.UUID(group_id)).verification_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    assert world.client.post("/trade-groups/verify-email", json={"token": new}).status_code == 410


# ------------------------------------------------------------------ vouch request -> email -> confirmation
def test_confirmed_trade_group_vouch_automatically_qualifies_the_artisan(world):
    skill_id = world.skill("Electrical Repair")
    group_id = _group(world)
    john = world.artisan(skill_id, "John Fon", verified=False)
    customer = world.user("CUSTOMER")
    request_id = world.request(customer, skill_id)
    matches = lambda: world.client.get(f"/matches/{request_id}", headers=customer.headers).json()
    assert matches()["matches"] == []                       # safety-critical + unverified => excluded

    OUTBOX.clear()
    res = _ask(world, john, group_id, skill_id, note="Member no. 42")
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "PENDING_CONFIRMATION" and body["email_status"] == "SENT" and body["simulated_email"] is True
    mail = OUTBOX[-1]
    assert mail.to == "contact@buea-electricians.example"
    assert "John Fon" in mail.body and "Electrical Repair" in mail.body and "Member no. 42" in mail.body
    assert john.phone not in mail.body and "/trade-group-vouches/confirm-page?token=" in mail.body

    # NOT qualified until the group confirms
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"
    assert world.client.get(f"/artisans/{john.artisan_id}").json()["trade_group_vouches"] == []

    token = _token()
    details = world.client.get("/trade-group-vouches/details", params={"token": token}).json()
    assert details["artisan_name"] == "John Fon" and "phone" not in str(details)
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"      # merely viewing the link changes nothing

    done = _answer(world, token)
    assert done.status_code == 200 and done.json()["status"] == "CONFIRMED"
    assert _skill_status(world, john, skill_id) == "VERIFIED"        # automatic qualification
    profile = world.client.get(f"/artisans/{john.artisan_id}").json()
    assert [(v["group_name"], v["skill_name"].split("-")[0]) for v in profile["trade_group_vouches"]] == [
        ("Buea Electricians Association", "Electrical Repair")]
    assert [m["full_name"] for m in matches()["matches"]] == ["John Fon"]    # now matchable for safety-critical work

    # the audit trail: an approved check with no human verifier, explaining why
    with world.factory() as db:
        vouch = db.query(TradeGroupVouch).one()
        assert vouch.status == "CONFIRMED" and vouch.token_hash is None and vouch.verification_check_id is not None
    assert _answer(world, token).status_code == 404                  # the link works once only


def test_group_can_decline_and_artisan_must_wait_before_asking_again(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    _ask(world, john, group_id, skill_id)
    assert _answer(world, _token(), "REJECT").json()["status"] == "REJECTED"
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"
    again = _ask(world, john, group_id, skill_id)
    assert again.status_code == 409 and "recently declined" in again.json()["detail"]


def test_one_trade_group_can_vouch_for_many_artisans_each_needs_its_own_confirmation(world):
    skill_id = world.skill()
    group_id = _group(world)
    artisans = [world.artisan(skill_id, f"Artisan {i}", verified=False) for i in range(3)]
    tokens = []
    for artisan in artisans:
        OUTBOX.clear()
        assert _ask(world, artisan, group_id, skill_id).status_code == 201
        assert len(OUTBOX) == 1                                      # one e-mail PER artisan
        tokens.append(_token())
    assert len(set(tokens)) == 3

    assert _answer(world, tokens[0]).status_code == 200              # confirming one...
    assert [_skill_status(world, a, skill_id) for a in artisans] == ["VERIFIED", "UNVERIFIED", "UNVERIFIED"]
    assert _answer(world, tokens[2]).status_code == 200              # ...does not qualify the others
    assert [_skill_status(world, a, skill_id) for a in artisans] == ["VERIFIED", "UNVERIFIED", "VERIFIED"]

    admin_view = world.client.get("/admin/trade-groups", headers=world.admin.headers).json()[0]
    assert (admin_view["confirmed_vouches"], admin_view["pending_vouches"]) == (2, 1)


def test_individuals_can_vouch_for_only_one_artisan(world):
    skill_id = world.skill()
    a, b = world.artisan(skill_id, verified=False), world.artisan(skill_id, verified=False)
    fan = world.user("CUSTOMER")
    body = {"evidence_description": "He repaired my roof wiring last year."}
    assert _post(world, fan, f"/artisans/{a.artisan_id}/endorsements", json=body).status_code == 201
    res = _post(world, fan, f"/artisans/{b.artisan_id}/endorsements", json=body)
    assert res.status_code == 409 and "Only trade groups" in res.json()["detail"]
    assert _post(world, fan, f"/artisans/{a.artisan_id}/endorsements", json=body).json()["detail"] == \
        "You have already endorsed this artisan"


def test_database_enforces_one_artisan_per_individual_endorser(world, session_factory):
    skill_id = world.skill()
    a, b = world.artisan(skill_id, verified=False), world.artisan(skill_id, verified=False)
    fan = world.user("CUSTOMER")
    world.client.post(f"/artisans/{a.artisan_id}/endorsements", headers=fan.headers,
                      json={"evidence_description": "A long enough description."})
    from sqlalchemy.exc import IntegrityError
    with session_factory() as db:
        db.add(Endorsement(artisan_id=uuid.UUID(b.artisan_id), endorser_id=fan.user_id, evidence_description="again"))
        with pytest.raises(IntegrityError):
            db.commit()


# ------------------------------------------------------------------ request rules
def test_request_rules(world):
    skill_id, other_skill = world.skill(), world.skill("Plumbing", False)
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    stranger = world.artisan(skill_id, verified=False)
    assert _post(world, stranger, f"/artisans/{john.artisan_id}/trade-group-vouches",
                 json={"group_id": group_id, "skill_id": skill_id}).status_code == 403   # not your profile
    assert _post(world, world.user("CUSTOMER"), f"/artisans/{john.artisan_id}/trade-group-vouches",
                 json={"group_id": group_id, "skill_id": skill_id}).status_code == 403
    assert _ask(world, john, group_id, other_skill).status_code == 400                   # skill not on profile
    assert _ask(world, john, str(uuid.uuid4()), skill_id).status_code == 404            # unknown group
    assert _ask(world, john, group_id, skill_id).status_code == 201
    assert _ask(world, john, group_id, skill_id).status_code == 409                      # already pending
    verified = world.artisan(skill_id, verified=True)
    assert _ask(world, verified, group_id, skill_id).status_code == 409                  # already verified


def test_suspended_group_cannot_receive_requests(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    assert _post(world, world.admin, f"/admin/trade-groups/{group_id}/suspend").json()["status"] == "SUSPENDED"
    assert _ask(world, john, group_id, skill_id).status_code == 404
    assert world.client.get("/trade-groups").json() == []
    assert _post(world, world.admin, f"/admin/trade-groups/{group_id}/activate").json()["status"] == "ACTIVE"
    assert _ask(world, john, group_id, skill_id).status_code == 201


def test_my_vouches_are_private(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    _ask(world, john, group_id, skill_id)
    path = f"/artisans/{john.artisan_id}/trade-group-vouches"
    assert len(world.client.get(path, headers=john.headers).json()) == 1
    assert world.client.get(path, headers=world.admin.headers).status_code == 200
    assert world.client.get(path, headers=world.user("CUSTOMER").headers).status_code == 404
    assert world.client.get(path).status_code == 401


# ------------------------------------------------------------------ expiry and resend
def test_expired_link_and_resend(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    vouch_id = _ask(world, john, group_id, skill_id).json()["vouch_id"]
    old = _token()
    with world.factory() as db:
        db.get(TradeGroupVouch, uuid.UUID(vouch_id)).token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert world.client.get("/trade-group-vouches/details", params={"token": old}).status_code == 410
    assert _answer(world, old).status_code == 410
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"

    path = f"/artisans/{john.artisan_id}/trade-group-vouches/{vouch_id}/resend"
    assert _post(world, john, path).json()["status"] == "PENDING_CONFIRMATION"
    new = _token()
    assert new != old and _answer(world, old).status_code == 404            # the old link is dead for good
    assert _answer(world, new).status_code == 200 and _skill_status(world, john, skill_id) == "VERIFIED"
    assert _post(world, john, path).status_code == 409                       # a confirmed vouch cannot be re-sent
    assert _post(world, world.artisan(skill_id), path).status_code in (403, 404)


# ------------------------------------------------------------------ configurable: threshold-only mode
def test_without_auto_verify_a_vouch_only_satisfies_the_community_proof(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "trade_group_vouch_auto_verifies", False)
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    _ask(world, john, group_id, skill_id)
    _answer(world, _token())
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"             # a verifier must still decide
    check = _post(world, john, "/verifications", json={
        "check_type": "SKILL", "skill_id": skill_id, "evidence_description": "Ten years wiring houses."}).json()
    for decision in ("UNDER_REVIEW", "APPROVED"):                            # no 2 endorsements needed
        res = _post(world, world.verifier, f"/verifications/{check['check_id']}/decision", json={"decision": decision})
        assert res.status_code == 200, res.text
    assert _skill_status(world, john, skill_id) == "VERIFIED"


# ------------------------------------------------------------------ revocation
def test_admin_can_revoke_a_vouch(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    vouch_id = _ask(world, john, group_id, skill_id).json()["vouch_id"]
    _answer(world, _token())
    assert _skill_status(world, john, skill_id) == "VERIFIED"
    path = f"/admin/trade-group-vouches/{vouch_id}/revoke"
    assert _post(world, john, path, json={"notes": "fraud suspected"}).status_code == 403
    assert _post(world, world.verifier, path, json={"notes": "fraud suspected"}).status_code == 403
    res = _post(world, world.admin, path, json={"notes": "group vouched without knowing him"})
    assert res.status_code == 200 and res.json()["status"] == "REVOKED"
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"
    assert world.client.get(f"/artisans/{john.artisan_id}").json()["trade_group_vouches"] == []
    assert _post(world, world.admin, path, json={"notes": "second time"}).status_code == 409


def test_revoking_keeps_the_skill_verified_if_a_verifier_also_approved_it(world, monkeypatch):
    """Vouch confirmed while a verifier separately approves the same skill: revoking the vouch must not strip it."""
    monkeypatch.setattr(get_settings(), "trade_group_vouch_auto_verifies", False)
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    vouch_id = _ask(world, john, group_id, skill_id).json()["vouch_id"]
    _answer(world, _token())
    check = _post(world, john, "/verifications", json={
        "check_type": "SKILL", "skill_id": skill_id, "evidence_description": "Ten years wiring houses."}).json()
    for decision in ("UNDER_REVIEW", "APPROVED"):
        _post(world, world.verifier, f"/verifications/{check['check_id']}/decision", json={"decision": decision})
    monkeypatch.setattr(get_settings(), "trade_group_vouch_auto_verifies", True)
    assert _skill_status(world, john, skill_id) == "VERIFIED"
    assert _post(world, world.admin, f"/admin/trade-group-vouches/{vouch_id}/revoke",
                 json={"notes": "group withdrew its support"}).status_code == 200
    assert _skill_status(world, john, skill_id) == "VERIFIED"               # the verifier's approval still stands


# ------------------------------------------------------------------ the no-login pages
def test_confirmation_page_flow_and_security_headers(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, "John <b>Fon</b>", verified=False)
    _ask(world, john, group_id, skill_id, note="<script>alert(1)</script>")
    token = _token()

    page = world.client.get("/trade-group-vouches/confirm-page", params={"token": token})
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text and "&lt;script&gt;" in page.text    # XSS-safe
    assert "John &lt;b&gt;Fon&lt;/b&gt;" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert page.headers["cache-control"] == "no-store" and page.headers["x-frame-options"] == "DENY"
    assert _skill_status(world, john, skill_id) == "UNVERIFIED"             # opening the page decides nothing

    done = world.client.post("/trade-group-vouches/confirm-page", data={"token": token, "decision": "CONFIRM"})
    assert done.status_code == 200 and "vouched for" in done.text
    assert _skill_status(world, john, skill_id) == "VERIFIED"
    reuse = world.client.post("/trade-group-vouches/confirm-page", data={"token": token, "decision": "CONFIRM"})
    assert reuse.status_code == 404 and "already been used" in reuse.text
    assert world.client.get("/trade-group-vouches/confirm-page", params={"token": "z" * 40}).status_code == 404


def test_group_verification_page(world):
    res = _post(world, world.admin, "/admin/trade-groups", json={"name": "Page Guild", "email": "p@guild.example"})
    token = _token()
    assert "Page Guild" in world.client.get("/trade-groups/verify-page", params={"token": token}).text
    done = world.client.post("/trade-groups/verify-page", data={"token": token})
    assert done.status_code == 200 and "now active" in done.text
    assert world.client.get("/admin/trade-groups", headers=world.admin.headers).json()[0]["status"] == "ACTIVE"
    assert res.json()["status"] == "PENDING_EMAIL_VERIFICATION"


def test_token_is_not_stored_in_clear(world):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    _ask(world, john, group_id, skill_id)
    token = _token()
    with world.factory() as db:
        stored = db.query(TradeGroupVouch).one().token_hash
    assert stored and token not in stored and len(stored) == 64


def test_admin_dev_outbox_is_admin_only(world):
    _post(world, world.admin, "/admin/trade-groups", json={"name": "Outbox Guild", "email": "o@guild.example"})
    assert world.client.get("/admin/dev/outbox", headers=world.user("CUSTOMER").headers).status_code == 403
    mails = world.client.get("/admin/dev/outbox", headers=world.admin.headers).json()
    assert mails and mails[-1]["to"] == "o@guild.example"


# ------------------------------------------------------------------ e-mail transport
def test_email_header_injection_is_neutralised():
    OUTBOX.clear()
    email_service.send_email("a@b.example", "Hello\r\nBcc: evil@x.example", "body")
    assert "\n" not in OUTBOX[-1].subject and "\r" not in OUTBOX[-1].subject


def test_smtp_mode_sends_and_failures_are_reported_not_raised(monkeypatch):
    settings = get_settings()
    for key, value in {"email_mode": "smtp", "smtp_host": "smtp.test", "smtp_from": "noreply@acbridge.test",
                       "smtp_username": "u", "smtp_password": "p"}.items():
        monkeypatch.setattr(settings, key, value)
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout): sent.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): sent.append("tls")
        def login(self, user, password): sent.append(("login", user))
        def send_message(self, message): sent.append(("to", message["To"], message["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    assert email_service.send_email("g@guild.example", "Subject", "Body") is True
    assert ("to", "g@guild.example", "Subject") in sent and "tls" in sent and ("login", "u") in sent

    class BrokenSMTP(FakeSMTP):
        def send_message(self, message): raise smtplib.SMTPException("down")

    monkeypatch.setattr(smtplib, "SMTP", BrokenSMTP)
    assert email_service.send_email("g@guild.example", "Subject", "Body") is False       # reported, not raised


def test_failed_email_is_flagged_and_can_be_resent(world, monkeypatch):
    skill_id = world.skill()
    group_id = _group(world)
    john = world.artisan(skill_id, verified=False)
    monkeypatch.setattr(email_service, "send_email", lambda *a, **k: False)
    res = _ask(world, john, group_id, skill_id).json()
    assert res["email_status"] == "FAILED" and "resend" in res["message"].lower()
    monkeypatch.undo()
    resent = _post(world, john, f"/artisans/{john.artisan_id}/trade-group-vouches/{res['vouch_id']}/resend").json()
    assert resent["email_status"] == "SENT"
