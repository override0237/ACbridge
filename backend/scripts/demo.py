"""End-to-end demonstration of the ACbridge journey (John the electrician, Mary the customer).

Against a running API (after `python -m app.init_db && python -m app.seed`):
    python -m scripts.demo --base-url http://localhost:8000

All verification here is SIMULATED.
"""
import argparse
import json
import random

import httpx

DEMO_PASSWORD = "Demo-Pass-123!"
VERIFIER_PHONE = "+237670000002"


def run(client, verifier_phone: str = VERIFIER_PHONE, password: str = DEMO_PASSWORD, verbose: bool = True) -> dict:
    def show(step: str, response, keys: tuple[str, ...] = ()) -> dict:
        assert response.status_code < 300, f"{step} failed: {response.status_code} {response.text}"
        body = response.json()
        if verbose:
            shown = {k: body[k] for k in keys if k in body} if keys else body
            print(f"\n[{step}] HTTP {response.status_code}\n{json.dumps(shown, indent=2, default=str)}")
        return body

    def auth(phone: str) -> dict:
        token = client.post("/auth/login", json={"phone": phone, "password": password}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def new_phone() -> str:
        return "+2376" + "".join(str(random.randint(0, 9)) for _ in range(8))

    verifier = auth(verifier_phone)
    skills = {s["skill_name"]: s["skill_id"] for s in client.get("/skills").json()}
    electrical = skills["Electrical Repair"]

    # 1. John registers as an electrician (self-service; role limited to CUSTOMER/ARTISAN)
    john_phone = new_phone()
    show("1. John registers", client.post("/auth/register", json={"phone": john_phone, "password": password, "role": "ARTISAN"}))
    john = auth(john_phone)
    profile = show("1b. John creates his artisan profile", client.post("/artisans", headers=john, json={
        "full_name": "John Fon", "location": "Small Soppo, Buea", "availability_status": "AVAILABLE",
        "description": "Electrician, 10 years' experience"}), ("artisan_id", "full_name", "location", "identity_verified"))
    artisan_id = profile["artisan_id"]

    # 2. John adds the electrical repair skill (starts UNVERIFIED - he cannot set that himself)
    show("2. John adds Electrical Repair", client.post(f"/artisans/{artisan_id}/skills", headers=john, json={
        "skill_id": electrical, "proficiency_level": "INTERMEDIATE", "typical_price": 8000}))

    # 3. Two independent users endorse John
    for i in range(2):
        phone = new_phone()
        client.post("/auth/register", json={"phone": phone, "password": password, "role": "CUSTOMER"})
        show(f"3.{i + 1} independent endorsement", client.post(f"/artisans/{artisan_id}/endorsements", headers=auth(phone), json={
            "evidence_description": "John rewired my shop in 2024 and it has worked perfectly since."}), ("endorsement_id",))

    # 4. John requests skill verification; the verifier reviews and approves (SIMULATED)
    check = show("4a. John submits skill evidence", client.post("/verifications", headers=john, json={
        "check_type": "SKILL", "skill_id": electrical,
        "evidence_description": "Wired 30+ houses in Buea; references available from 2 clients."}),
        ("check_id", "status", "endorsement_count", "review_signals", "simulated"))
    check_id = check["check_id"]
    show("4b. Verifier claims the check", client.post(f"/verifications/{check_id}/decision", headers=verifier,
         json={"decision": "UNDER_REVIEW"}), ("status",))
    show("4c. Verifier approves (SIMULATED)", client.post(f"/verifications/{check_id}/decision", headers=verifier, json={
        "decision": "APPROVED", "decision_notes": "SIMULATED: no real assessment performed"}), ("status", "simulated", "notice"))

    # 5-7. Mary registers and requests an electrical repair in Small Soppo, Buea, budget 10,000 FCFA
    mary_phone = new_phone()
    show("5. Mary registers", client.post("/auth/register", json={"phone": mary_phone, "password": password, "role": "CUSTOMER"}))
    mary = auth(mary_phone)
    request = show("6-7. Mary requests an electrical repair (budget 10,000 FCFA)", client.post("/service-requests", headers=mary, json={
        "skill_id": electrical, "description": "Faulty wiring in the kitchen, sockets sparking",
        "location": "Small Soppo, Buea", "budget": 10000}))

    # 8. The matching engine ranks the eligible electricians
    matches = show("8. Ranked matches", client.get(f"/matches/{request['request_id']}", headers=mary),
                   ("weights", "excluded_summary", "matches"))
    names = [m["full_name"] for m in matches["matches"]]
    assert "John Fon" in names and len(names) >= 2, "expected John plus at least one competitor"

    # 9. Mary books John; John accepts            10. John starts the work
    job = show("9a. Mary selects John", client.post("/jobs", headers=mary, json={
        "request_id": request["request_id"], "artisan_id": artisan_id, "agreed_price": 9000}), ("job_id", "status"))
    job_id = job["job_id"]
    show("9b. John accepts", client.post(f"/jobs/{job_id}/accept", headers=john), ("status", "counterpart_phone"))
    show("10. John starts the job", client.post(f"/jobs/{job_id}/start", headers=john), ("status",))

    # 11-12. Both confirm independently; only then is the job COMPLETED
    show("11a. John confirms completion", client.post(f"/jobs/{job_id}/confirm-completion", headers=john),
         ("status", "customer_confirmed", "artisan_confirmed"))
    done = show("11b. Mary confirms completion", client.post(f"/jobs/{job_id}/confirm-completion", headers=mary),
                ("status", "customer_confirmed", "artisan_confirmed", "completed_at"))
    assert done["status"] == "COMPLETED"

    # 13-14. Mary reviews; John's reputation updates
    show("13. Mary reviews John", client.post(f"/jobs/{job_id}/reviews", headers=mary,
         json={"rating": 5, "comment": "Fixed quickly, fair price."}))
    reputation = show("14. John's updated reputation", client.get(f"/artisans/{artisan_id}/reputation"))
    final_job = client.get(f"/jobs/{job_id}", headers=mary).json()
    if verbose:
        print("\nAudit trail:", " -> ".join(e["event_type"] for e in final_job["events"]))
    return {"artisan_id": artisan_id, "job": final_job, "matches": matches, "reputation": reputation}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--verifier-phone", default=VERIFIER_PHONE)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as http_client:
        run(http_client, args.verifier_phone, args.password)
