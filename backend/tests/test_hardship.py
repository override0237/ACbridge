import pytest
from sqlalchemy.exc import IntegrityError

from app.models import HardshipClaim

PDF = b"%PDF-1.4 certificate"
CLAIM = {"kind": "DEATH", "affected_party": "ARTISAN", "description": "The artisan passed away on Monday."}


def _post(world, actor, path, **kw):
    return world.client.post(path, headers=actor.headers, **kw)


def _job(world, actor, job_id):
    return world.client.get(f"/jobs/{job_id}", headers=actor.headers).json()


def _claim(world, actor, job_id, **override):
    return _post(world, actor, f"/jobs/{job_id}/hardship-claims", json={**CLAIM, **override})


def _upload(world, actor, claim_id, name="certificate.pdf", content=PDF):
    return _post(world, actor, f"/hardship-claims/{claim_id}/document", files={"file": (name, content, "application/pdf")})


def _decide(world, actor, claim_id, approve=True, notes="Checked the certificate, it is genuine."):
    return _post(world, actor, f"/admin/hardship-claims/{claim_id}/decision", json={"approve": approve, "notes": notes})


def test_approved_claim_cancels_the_job_and_refunds_fees_and_escrow(world):
    customer, john, job_id = world.job_in_progress()       # commission paid, escrow held, work started
    before = {p["payment_type"]: p["status"] for p in _job(world, customer, job_id)["payments"]}
    assert before["JOB_PAYMENT"] == "SUCCEEDED"

    claim = _claim(world, customer, job_id)                # customer reports the artisan's death
    assert claim.status_code == 201 and claim.json()["required_proof"] == "A death certificate"
    claim_id = claim.json()["claim_id"]
    assert _upload(world, customer, claim_id).json()["has_document"] is True

    decided = _decide(world, world.admin, claim_id)
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED"

    job = _job(world, world.admin, job_id)
    assert job["status"] == "CANCELLED" and job["escrow_status"] == "REFUNDED"
    statuses = {p["payment_type"]: p["status"] for p in job["payments"]}
    assert statuses == {"COMMISSION": "REFUNDED", "JOB_PAYMENT": "REFUNDED"}     # fee refunded too
    types = [e["event_type"] for e in job["events"]]
    assert {"HARDSHIP_CLAIM_FILED", "JOB_CANCELLED_HARDSHIP", "FEE_REFUNDED", "ESCROW_REFUNDED",
            "HARDSHIP_CLAIM_APPROVED"} <= set(types)
    request = world.client.get(f"/service-requests/{job['request_id']}", headers=customer.headers).json()
    assert request["status"] == "CANCELLED"


def test_accident_claim_by_the_artisan_about_themselves(world):
    customer, john, job_id = world.job_in_progress()
    claim = _claim(world, john, job_id, kind="ACCIDENT_OR_SERIOUS_ILLNESS", affected_party="ARTISAN",
                   description="Hospitalised after a road accident.").json()
    assert claim["required_proof"].startswith("Medical records")
    _upload(world, john, claim["claim_id"], "records.pdf")
    assert _decide(world, world.admin, claim["claim_id"]).json()["status"] == "APPROVED"
    assert _job(world, john, job_id)["status"] == "CANCELLED"


def test_cannot_approve_without_a_document(world):
    customer, john, job_id = world.job_in_progress()
    claim_id = _claim(world, customer, job_id).json()["claim_id"]
    res = _decide(world, world.admin, claim_id)
    assert res.status_code == 400 and "document" in res.json()["detail"]
    assert _job(world, customer, job_id)["status"] == "IN_PROGRESS"        # nothing refunded or cancelled


def test_rejected_claim_changes_nothing_and_a_new_claim_can_follow(world):
    customer, john, job_id = world.job_in_progress()
    claim_id = _claim(world, customer, job_id).json()["claim_id"]
    _upload(world, customer, claim_id)
    assert _decide(world, world.admin, claim_id, approve=False, notes="Document does not match.").json()["status"] == "REJECTED"
    job = _job(world, customer, job_id)
    assert job["status"] == "IN_PROGRESS" and job["escrow_status"] == "HELD"
    assert _decide(world, world.admin, claim_id).status_code == 409        # already decided
    assert _claim(world, customer, job_id).status_code == 201              # may try again with proper proof


def test_only_the_two_parties_can_file_and_only_one_open_claim(world):
    customer, john, job_id = world.job_in_progress()
    stranger, other_artisan = world.user("CUSTOMER"), world.artisan(world.skill())
    for actor in (stranger, other_artisan, world.admin):
        assert _claim(world, actor, job_id).status_code == 403
    assert _claim(world, customer, job_id).status_code == 201
    assert _claim(world, john, job_id).status_code == 409                  # one claim at a time
    assert _claim(world, customer, job_id, kind="FLU").status_code == 422


def test_finished_jobs_cannot_have_claims(world):
    customer, john, job_id = world.completed_job()
    assert _claim(world, customer, job_id).status_code == 409


def test_only_admins_decide_claims(world):
    customer, john, job_id = world.job_in_progress()
    claim_id = _claim(world, customer, job_id).json()["claim_id"]
    _upload(world, customer, claim_id)
    for actor in (customer, john, world.verifier):
        assert _decide(world, actor, claim_id).status_code == 403
    assert _job(world, customer, job_id)["status"] == "IN_PROGRESS"


def test_documents_are_validated_and_private(world):
    customer, john, job_id = world.job_in_progress()
    claim_id = _claim(world, customer, job_id).json()["claim_id"]
    assert _upload(world, customer, claim_id, "fake.pdf", b"<html>nope</html>").status_code == 400
    assert _upload(world, customer, claim_id, "virus.exe", b"MZ0000").status_code == 400
    assert _upload(world, john, claim_id).status_code == 404               # the other party cannot attach
    assert _upload(world, customer, claim_id).status_code == 200

    path = f"/hardship-claims/{claim_id}/document"
    assert world.client.get(path, headers=customer.headers).content == PDF
    assert world.client.get(path, headers=world.admin.headers).status_code == 200
    assert world.client.get(path, headers=john.headers).status_code == 404  # not even the other party sees it
    assert world.client.get(f"/hardship-claims/{claim_id}", headers=john.headers).status_code == 404
    pending = world.client.get("/admin/hardship-claims", headers=world.admin.headers).json()
    assert [c["claim_id"] for c in pending] == [claim_id]
    assert world.client.get("/admin/hardship-claims", headers=customer.headers).status_code == 403


def test_normal_dispute_resolution_never_refunds_platform_fees(world):
    customer, john, job_id = world.job_in_progress()
    _post(world, customer, f"/jobs/{job_id}/dispute", json={"reason": "I am unhappy with the work"})
    _post(world, world.admin, f"/admin/jobs/{job_id}/resolve-dispute", json={"outcome": "CANCELLED", "notes": "refund customer"})
    job = _job(world, world.admin, job_id)            # admins see every payment
    statuses = {p["payment_type"]: p["status"] for p in job["payments"]}
    assert statuses["JOB_PAYMENT"] == "REFUNDED"      # customer's escrow protected
    assert statuses["COMMISSION"] == "SUCCEEDED"      # the artisan's fee is not returned


def test_database_refuses_an_approved_claim_without_document(world, session_factory):
    customer, john, job_id = world.job_in_progress()
    claim_id = _claim(world, customer, job_id).json()["claim_id"]
    with session_factory() as db:
        db.get(HardshipClaim, __import__("uuid").UUID(claim_id)).status = "APPROVED"
        with pytest.raises(IntegrityError):
            db.commit()
