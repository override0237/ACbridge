import pytest


def _submit_skill_check(world, artisan, skill_id):
    res = world.client.post("/verifications", headers=artisan.headers, json={
        "check_type": "SKILL", "skill_id": skill_id, "evidence_description": "Ten years wiring houses in Buea."})
    assert res.status_code == 201, res.text
    return res.json()["check_id"]


def _decide(world, actor, check_id, decision):
    return world.client.post(f"/verifications/{check_id}/decision", headers=actor.headers,
                             json={"decision": decision, "decision_notes": "SIMULATED"})


def test_self_endorsement_rejected(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    res = world.client.post(f"/artisans/{john.artisan_id}/endorsements", headers=john.headers,
                            json={"evidence_description": "I am great at my own job, trust me."})
    assert res.status_code == 403
    assert "yourself" in res.json()["detail"]


def test_duplicate_endorsement_rejected(world):
    john = world.artisan(world.skill(), verified=False)
    fan = world.user("CUSTOMER")
    body = {"evidence_description": "He fixed my roof wiring last year."}
    assert world.client.post(f"/artisans/{john.artisan_id}/endorsements", headers=fan.headers, json=body).status_code == 201
    assert world.client.post(f"/artisans/{john.artisan_id}/endorsements", headers=fan.headers, json=body).status_code == 409


def test_unauthorized_users_cannot_decide(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    check_id = _submit_skill_check(world, john, skill_id)
    customer = world.user("CUSTOMER")
    other_artisan = world.artisan(skill_id, verified=False)
    for actor in (customer, other_artisan, john):
        assert _decide(world, actor, check_id, "UNDER_REVIEW").status_code == 403
    assert world.client.post(f"/verifications/{check_id}/decision", json={"decision": "APPROVED"}).status_code == 401


def test_verifier_cannot_verify_own_profile(world):
    """A user holding the VERIFIER role who is also an artisan cannot approve their own check."""
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    check_id = _submit_skill_check(world, john, skill_id)
    # An admin promotes John himself to VERIFIER; he still must not be able to verify himself.
    res = world.client.post(f"/admin/users/{john.user_id}/role", headers=world.admin.headers, json={"role": "VERIFIER"})
    assert res.status_code == 200
    assert _decide(world, john, check_id, "UNDER_REVIEW").status_code == 403


def test_verifier_with_conflict_of_interest_is_blocked(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    check_id = _submit_skill_check(world, john, skill_id)
    verifier = world.new_verifier()
    world.client.post(f"/artisans/{john.artisan_id}/endorsements", headers=verifier.headers,
                      json={"evidence_description": "I know John from church and his work."})
    assert _decide(world, verifier, check_id, "UNDER_REVIEW").status_code == 403


def test_correct_approval_workflow_and_skill_specific_effect(world):
    electrical, plumbing = world.skill("Electrical"), world.skill("Plumbing", safety_critical=False)
    john = world.artisan(electrical, verified=False)
    world.client.post(f"/artisans/{john.artisan_id}/skills", headers=john.headers,
                      json={"skill_id": plumbing, "proficiency_level": "BEGINNER"})
    world.endorse(john, 2)
    check_id = _submit_skill_check(world, john, electrical)

    # cannot jump straight from PENDING to APPROVED
    assert _decide(world, world.verifier, check_id, "APPROVED").status_code == 409
    assert _decide(world, world.verifier, check_id, "UNDER_REVIEW").json()["status"] == "UNDER_REVIEW"
    final = _decide(world, world.verifier, check_id, "APPROVED")
    assert final.status_code == 200 and final.json()["status"] == "APPROVED"
    assert final.json()["simulated"] is True and "SIMULATED" in final.json()["notice"]

    profile = world.client.get(f"/artisans/{john.artisan_id}").json()
    statuses = {s["skill_id"]: s["verification_status"] for s in profile["skills"]}
    assert statuses[electrical] == "VERIFIED"
    assert statuses[plumbing] == "UNVERIFIED"          # verifying one skill does not verify the others
    assert profile["identity_verified"] is False       # nor does it verify identity
    # finished checks are final
    assert _decide(world, world.verifier, check_id, "REJECTED").status_code == 409


def test_approval_requires_community_endorsements(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    world.endorse(john, 1)                              # one is not enough (minimum is 2)
    check_id = _submit_skill_check(world, john, skill_id)
    _decide(world, world.verifier, check_id, "UNDER_REVIEW")
    res = _decide(world, world.verifier, check_id, "APPROVED")
    assert res.status_code == 409 and "endorsement" in res.json()["detail"]


def test_needs_more_evidence_then_resubmit_returns_to_pending(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    world.endorse(john, 2)
    check_id = _submit_skill_check(world, john, skill_id)
    _decide(world, world.verifier, check_id, "UNDER_REVIEW")
    assert _decide(world, world.verifier, check_id, "NEEDS_MORE_EVIDENCE").json()["status"] == "NEEDS_MORE_EVIDENCE"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    res = world.client.post(f"/verifications/{check_id}/evidence", headers=john.headers,
                            files={"file": ("work.png", png, "image/png")})
    assert res.status_code == 200 and res.json()["status"] == "PENDING" and res.json()["has_evidence_file"]


@pytest.mark.parametrize("name,content", [
    ("virus.exe", b"MZ" + b"0" * 50),                 # wrong extension
    ("fake.png", b"<html>not a png</html>"),          # right extension, wrong content
    ("../../etc/passwd.png", b"not-an-image"),        # traversal attempt
])
def test_evidence_upload_rejects_unsafe_files(world, name, content):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    check_id = _submit_skill_check(world, john, skill_id)
    res = world.client.post(f"/verifications/{check_id}/evidence", headers=john.headers,
                            files={"file": (name, content, "application/octet-stream")})
    assert res.status_code == 400


def test_evidence_is_private(world):
    skill_id = world.skill()
    john = world.artisan(skill_id, verified=False)
    check_id = _submit_skill_check(world, john, skill_id)
    stranger = world.user("CUSTOMER")
    assert world.client.get(f"/verifications/{check_id}", headers=stranger.headers).status_code == 404
    assert world.client.get(f"/verifications/{check_id}", headers=john.headers).status_code == 200
    assert world.client.get(f"/verifications/{check_id}", headers=world.verifier.headers).status_code == 200
    public = str(world.client.get(f"/artisans/{john.artisan_id}").json())
    assert "Ten years wiring" not in public        # the private evidence text is not on the public profile
    assert john.phone not in public                # nor is the phone number
