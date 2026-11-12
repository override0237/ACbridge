"""The full demonstration scenario as an automated regression test."""
import pytest

from app.seed import DEMO_PASSWORD, VERIFIER_PHONE, seed
from scripts.demo import run


def test_complete_demo_journey(client, session_factory):
    with session_factory() as db:
        seed(db)
    result = run(client, VERIFIER_PHONE, DEMO_PASSWORD, verbose=False)

    matches = result["matches"]
    names = [m["full_name"] for m in matches["matches"]]
    assert names == ["John Fon", "Paul Tabi"]            # >1 artisan ranked; John edges Paul on location and price
    assert matches["matches"][0]["match_score"] == 86.5
    assert matches["matches"][1]["match_score"] == pytest.approx(85.05, abs=0.01)
    # Samuel (unverified), Esther (unavailable) and Ngu (Limbe) were filtered out with stated reasons
    assert matches["excluded_summary"] == {
        "SKILL_NOT_VERIFIED_FOR_SAFETY_CRITICAL_WORK": 1, "UNAVAILABLE": 1, "OUTSIDE_SERVICE_AREA": 1}

    assert result["job"]["status"] == "COMPLETED"
    reputation = result["reputation"]
    assert reputation["verified_reviews"] == 1
    assert reputation["reputation_score"] == pytest.approx(1 / 11 * 5 + 10 / 11 * 4, abs=1e-3)   # 4.0909
    # Payments: commission (5% of 9000 = 450) was paid by John; Mary's 9000 was escrowed and then released.
    job = result["job"]
    assert job["agreed_price"] == 9000 and job["escrow_status"] == "RELEASED"
    types = {p["payment_type"]: p for p in job["payments"]}
    assert types["JOB_PAYMENT"]["amount"] == 9000 and types["JOB_PAYMENT"]["status"] == "RELEASED"
    events = [e["event_type"] for e in job["events"]]
    assert "PAYMENT_SUCCEEDED" in events and events[-2:] == ["JOB_COMPLETED", "PAYOUT_RELEASED"]
    # WhatsApp: John opted in, Paul did too; Samuel etc. were filtered out anyway
    assert all(m["contact"] is not None for m in matches["matches"])
