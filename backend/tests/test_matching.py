import pytest

from app.services import matching_service as m
from app.services.reputation_service import Reputation


def _matches(world, customer, request_id):
    res = world.client.get(f"/matches/{request_id}", headers=customer.headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_weights_sum_to_one_and_follow_the_formula():
    assert sum(m.WEIGHTS.values()) == pytest.approx(1.0)
    assert m.WEIGHTS == {"skill": 0.35, "location": 0.25, "availability": 0.15, "work_history": 0.15, "price": 0.10}
    parts = {"skill": 100, "location": 60, "availability": 100, "work_history": 40, "price": 50}
    assert m.compute_match_score(parts) == pytest.approx(0.35 * 100 + 0.25 * 60 + 0.15 * 100 + 0.15 * 40 + 0.10 * 50)


def test_component_functions_and_missing_data():
    assert m.skill_score("EXPERT", "VERIFIED") == 100
    assert m.skill_score("INTERMEDIATE", "VERIFIED") == 85
    assert m.skill_score("BEGINNER", "UNVERIFIED") == 20
    assert m.location_score("Small Soppo, Buea", "small soppo,  BUEA") == 100
    assert m.location_score("Small Soppo, Buea", "Molyko, Buea") == 60
    assert m.location_score("Buea", "Molyko, Buea") == 60
    assert m.location_score("Small Soppo, Buea", "Bonanjo, Douala") == 0
    assert m.availability_score("AVAILABLE") == 100 and m.availability_score("BUSY") == 50
    assert m.price_score(8000, 10000) == 100
    assert m.price_score(12000, 10000) == pytest.approx(80)
    assert m.price_score(30000, 10000) == 0
    assert m.price_score(None, 10000) == m.price_score(8000, None) == m.price_score(8000, 0) == 50   # no crash
    # newcomer (prior 4.0, no jobs): 0.6 * 75 + 0.4 * 0
    assert m.work_history_score(4.0, 0) == pytest.approx(45)


def test_only_eligible_artisans_are_returned_with_reasons(world):
    skill_id = world.skill("Electrical")
    customer = world.user("CUSTOMER")
    good = world.artisan(skill_id, "Good", "Small Soppo, Buea")
    unverified = world.artisan(skill_id, "Unverified", "Small Soppo, Buea", verified=False)
    unavailable = world.artisan(skill_id, "Away", "Small Soppo, Buea", availability="UNAVAILABLE")
    wrong_town = world.artisan(skill_id, "Limbe guy", "Down Beach, Limbe")
    suspended = world.artisan(skill_id, "Suspended", "Small Soppo, Buea")
    assert world.client.post(f"/admin/artisans/{suspended.artisan_id}/suspend", headers=world.admin.headers).status_code == 200
    other_skill_artisan = world.artisan(world.skill("Plumbing"), "Plumber", "Small Soppo, Buea")

    body = _matches(world, customer, world.request(customer, skill_id))
    names = [x["full_name"] for x in body["matches"]]
    assert names == ["Good"]                      # no unverified, unavailable, out-of-town, suspended or plumber
    assert body["excluded_summary"] == {
        "SKILL_NOT_VERIFIED_FOR_SAFETY_CRITICAL_WORK": 1, "UNAVAILABLE": 1, "OUTSIDE_SERVICE_AREA": 1, "SUSPENDED": 1}
    assert "not proof of trustworthiness" in body["disclaimer"]
    _ = (unverified, unavailable, wrong_town, other_skill_artisan)


def test_unverified_allowed_only_for_non_safety_critical_work(world):
    skill_id = world.skill("Tailoring", safety_critical=False)
    customer = world.user("CUSTOMER")
    tailor = world.artisan(skill_id, "Tailor", verified=False)
    body = _matches(world, customer, world.request(customer, skill_id))
    assert [x["full_name"] for x in body["matches"]] == ["Tailor"]
    assert body["matches"][0]["skill_verification_status"] == "UNVERIFIED"
    _ = tailor


def test_ranking_is_calculated_correctly(world):
    skill_id = world.skill("Electrical")
    customer = world.user("CUSTOMER")
    john = world.artisan(skill_id, "John", "Small Soppo, Buea", price=8000, proficiency="INTERMEDIATE")
    paul = world.artisan(skill_id, "Paul", "Molyko, Buea", price=12000, proficiency="EXPERT")
    busy = world.artisan(skill_id, "Busy", "Molyko, Buea", availability="BUSY", price=None, proficiency="EXPERT")
    body = _matches(world, customer, world.request(customer, skill_id, "Small Soppo, Buea", budget=10000))

    # Hand-computed expectations (newcomers: work_history = 45):
    #  John: S=85  L=100 A=100 R=45 P=100 -> 29.75 + 25 + 15 + 6.75 + 10 = 86.50
    #  Paul: S=100 L=60  A=100 R=45 P=80  -> 35    + 15 + 15 + 6.75 + 8  = 79.75
    #  Busy: S=100 L=60  A=50  R=45 P=50  -> 35    + 15 + 7.5+ 6.75 + 5  = 69.25
    scores = {x["full_name"]: x for x in body["matches"]}
    assert [x["full_name"] for x in body["matches"]] == ["John", "Paul", "Busy"]
    assert scores["John"]["match_score"] == 86.50
    assert scores["Paul"]["match_score"] == 79.75
    assert scores["Busy"]["match_score"] == 69.25
    assert scores["John"]["breakdown"] == {"skill": 85, "location": 100, "availability": 100, "work_history": 45, "price": 100}
    _ = (john, paul, busy)


def test_reputation_improves_ranking(world):
    skill_id = world.skill("Electrical")
    veteran = world.artisan(skill_id, "Veteran", "Molyko, Buea")
    newcomer = world.artisan(skill_id, "Newcomer", "Molyko, Buea")
    customer = world.user("CUSTOMER")
    for _ in range(3):
        c = world.user("CUSTOMER")
        req = world.request(c, skill_id)
        job_id = world.job(c, veteran, req)
        for action in ("accept", "start"):
            world.client.post(f"/jobs/{job_id}/{action}", headers=veteran.headers)
        for who in (c, veteran):
            world.client.post(f"/jobs/{job_id}/confirm-completion", headers=who.headers)
        assert world.client.post(f"/jobs/{job_id}/reviews", headers=c.headers, json={"rating": 5}).status_code == 201
    body = _matches(world, customer, world.request(customer, skill_id, "Molyko, Buea"))
    assert [x["full_name"] for x in body["matches"]] == ["Veteran", "Newcomer"]
    assert body["matches"][0]["verified_reviews"] == 3
    _ = newcomer


def test_tie_break_is_deterministic():
    class FakeArtisan:
        def __init__(self, artisan_id): self.artisan_id = artisan_id
    class FakeCandidate:
        def __init__(self, artisan_id): self.artisan = FakeArtisan(artisan_id)
    def scored(artisan_id, reviews):
        rep = Reputation(artisan_id, 4.0, reviews, None, 0)
        return m.ScoredCandidate(FakeCandidate(artisan_id), rep, {}, 80.0, (80.0, reviews, artisan_id))
    ranked = m.rank_candidates([scored("b", 0), scored("a", 0), scored("c", 5)], limit=3)
    assert [r.sort_key[2] for r in ranked] == ["c", "a", "b"]    # more reviews first, then smaller id


def test_unsupported_town_returns_no_matches(world):
    skill_id = world.skill("Electrical")
    customer = world.user("CUSTOMER")
    world.artisan(skill_id, "Douala guy", "Bonanjo, Douala")
    body = _matches(world, customer, world.request(customer, skill_id, "Bonanjo, Douala"))
    assert body["matches"] == [] and body["service_area_supported"] is False


def test_only_the_owner_can_see_matches(world):
    skill_id = world.skill()
    owner, stranger = world.user("CUSTOMER"), world.user("CUSTOMER")
    request_id = world.request(owner, skill_id)
    assert world.client.get(f"/matches/{request_id}", headers=stranger.headers).status_code == 404
    artisan = world.artisan(skill_id)
    assert world.client.get(f"/matches/{request_id}", headers=artisan.headers).status_code == 403
