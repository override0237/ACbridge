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
        "whatsapp_number": john_phone,  # opt-in: matched customers get a WhatsApp chat link
        "description": "Electrician, 10 years' experience"}), ("artisan_id", "full_name", "location", "whatsapp_available"))
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

    # 8b. WhatsApp: the customer can chat with John before booking (he opted in)
    john_match = next(m for m in matches["matches"] if m["full_name"] == "John Fon")
    assert john_match["contact"]["icon"] == "whatsapp" and john_match["contact"]["link"].startswith("https://wa.me/")
    if verbose:
        print("\n[8b. WhatsApp contact for John] ->", john_match["contact"]["label"], "\n   ", john_match["contact"]["link"])

    def approve(payment: dict, headers: dict, label: str) -> dict:
        return show(label, client.post(f"/payments/{payment['payment_id']}/simulate-approval", headers=headers),
                    ("payment_type", "amount", "status", "simulated"))

    # 9. Mary proposes 9,000 FCFA; John agrees and pays the platform COMMISSION; only then is the job ACCEPTED
    show("9-policy. Fee policy (public)", client.get("/pricing"))
    job = show("9a. Mary proposes 9,000 FCFA to John", client.post("/jobs", headers=mary, json={
        "request_id": request["request_id"], "artisan_id": artisan_id, "proposed_price": 9000}),
        ("job_id", "status", "pricing_mode", "proposed_price"))
    job_id = job["job_id"]
    agreed = show("9b. John agrees to the amount -> commission due", client.post(f"/jobs/{job_id}/accept", headers=john),
                  ("status", "agreed_price", "payment_due"))
    approve(agreed["payment_due"], john, "9c. John pays the commission (SIMULATED mobile money)")
    show("9d. Job is now ACCEPTED", client.get(f"/jobs/{job_id}", headers=john),
         ("status", "counterpart_phone", "counterpart_whatsapp_link"))

    # 10. Mary pays the agreed amount INTO ESCROW; John starts the work
    escrow = show("10a. Mary pays 9,000 FCFA to the platform", client.post(f"/jobs/{job_id}/pay", headers=mary),
                  ("payment_type", "amount", "status"))
    approve(escrow, mary, "10b. Mary approves the payment (SIMULATED)")
    show("10c. John starts the job (escrow is HELD)", client.post(f"/jobs/{job_id}/start", headers=john),
         ("status", "escrow_status"))

    # 11-12. Both confirm independently; only then is the job COMPLETED and John paid out
    show("11a. John confirms completion", client.post(f"/jobs/{job_id}/confirm-completion", headers=john),
         ("status", "customer_confirmed", "artisan_confirmed"))
    done = show("11b. Mary confirms completion", client.post(f"/jobs/{job_id}/confirm-completion", headers=mary),
                ("status", "customer_confirmed", "artisan_confirmed", "completed_at", "escrow_status"))
    assert done["status"] == "COMPLETED" and done["escrow_status"] == "RELEASED"

    # 13-14. Mary reviews; John's reputation updates
    show("13. Mary reviews John", client.post(f"/jobs/{job_id}/reviews", headers=mary,
         json={"rating": 5, "comment": "Fixed quickly, fair price."}))
    reputation = show("14. John's updated reputation", client.get(f"/artisans/{artisan_id}/reputation"))

    # ---- Second scenario: a problem that must be INSPECTED before it can be priced ----
    request2 = show("15. Mary posts a problem that needs inspection", client.post("/service-requests", headers=mary, json={
        "skill_id": electrical, "description": "Power keeps tripping, cause unknown", "location": "Small Soppo, Buea",
        "needs_inspection": True}), ("request_id", "needs_inspection"))
    job2 = show("15b. Mary books John (no price yet)", client.post("/jobs", headers=mary, json={
        "request_id": request2["request_id"], "artisan_id": artisan_id}), ("job_id", "pricing_mode", "proposed_price"))
    due2 = show("15c. John agrees -> flat assignment fee due", client.post(f"/jobs/{job2['job_id']}/accept", headers=john),
                ("status", "payment_due"))
    approve(due2["payment_due"], john, "15d. John pays the flat assignment fee")
    show("15e. John inspects and quotes 15,000 FCFA", client.post(f"/jobs/{job2['job_id']}/quote", headers=john,
         json={"amount": 15000}), ("status", "proposed_price", "proposed_by"))
    show("15f. Mary approves the quote", client.post(f"/jobs/{job2['job_id']}/quote/respond", headers=mary,
         json={"approve": True}), ("status", "agreed_price"))
    final_job = client.get(f"/jobs/{job_id}", headers=mary).json()
    if verbose:
        print("\nAudit trail:", " -> ".join(e["event_type"] for e in final_job["events"]))
    return {"artisan_id": artisan_id, "job": final_job, "matches": matches, "reputation": reputation,
            "inspection_job_id": job2["job_id"], "john": john, "mary": mary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--verifier-phone", default=VERIFIER_PHONE)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as http_client:
        run(http_client, args.verifier_phone, args.password)
