"""End-to-end demonstration of the ACbridge journey (John the electrician, Mary the customer).

Against a running API (after `python -m app.init_db && python -m app.seed`):
    python -m scripts.demo --base-url http://localhost:8000

All verification here is SIMULATED.
"""
import argparse
import json
import random
import re

import httpx

DEMO_PASSWORD = "Demo-Pass-123!"
VERIFIER_PHONE = "+237670000002"
ADMIN_PHONE = "+237670000001"


def run(client, verifier_phone: str = VERIFIER_PHONE, password: str = DEMO_PASSWORD, verbose: bool = True,
        admin_phone: str = ADMIN_PHONE) -> dict:
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
    admin = auth(admin_phone)
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

    # 9. Mary proposes 9,000 FCFA; John agrees -> 24h probation -> he confirms and pays the COMMISSION -> ACCEPTED
    show("9-policy. Fee policy (public)", client.get("/pricing"))
    job = show("9a. Mary proposes 9,000 FCFA to John", client.post("/jobs", headers=mary, json={
        "request_id": request["request_id"], "artisan_id": artisan_id, "proposed_price": 9000}),
        ("job_id", "status", "pricing_mode", "proposed_price"))
    job_id = job["job_id"]
    agreed = show("9b. John agrees to the amount -> cooling-off starts, NO money moves yet",
                  client.post(f"/jobs/{job_id}/accept", headers=john),
                  ("status", "agreed_price", "probation_active", "probation_ends_at", "payment_due", "can_cancel_freely"))
    if agreed["probation_active"]:
        # Either side could withdraw for free now. The simulation lets the admin skip the 24 hours for the demo.
        early = client.post(f"/jobs/{job_id}/confirm-terms", headers=john)
        if verbose:
            print(f"\n[9b2. John tries to confirm during probation] HTTP {early.status_code}: {early.json()['detail']}")
        assert early.status_code == 409
        show("9b3. (DEMO ONLY) admin skips the 24h cooling-off", client.post(f"/admin/jobs/{job_id}/skip-probation", headers=admin),
             ("probation_active",))
    confirmed = show("9b4. After probation John makes the FINAL confirmation -> commission due",
                     client.post(f"/jobs/{job_id}/confirm-terms", headers=john), ("status", "payment_due"))
    approve(confirmed["payment_due"], john, "9c. John pays the commission (SIMULATED mobile money)")
    show("9d. Job is now ACCEPTED", client.get(f"/jobs/{job_id}", headers=john),
         ("status", "can_cancel_freely", "counterpart_phone", "counterpart_whatsapp_link"))

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
    approved = show("15f. Mary approves the quote -> cooling-off starts", client.post(f"/jobs/{job2['job_id']}/quote/respond",
                    headers=mary, json={"approve": True}), ("status", "agreed_price", "probation_active"))
    if approved["probation_active"]:
        early = client.post(f"/jobs/{job2['job_id']}/pay", headers=mary)
        assert early.status_code == 409
        if verbose:
            print(f"\n[15g. Mary tries to pay during probation] HTTP {early.status_code}: {early.json()['detail']}")
        client.post(f"/admin/jobs/{job2['job_id']}/skip-probation", headers=admin)
    escrow2 = show("15h. Mary pays the agreed 15,000 FCFA into escrow", client.post(f"/jobs/{job2['job_id']}/pay", headers=mary),
                   ("payment_type", "amount", "status"))
    approve(escrow2, mary, "15i. Mary approves the escrow payment")

    # ---- Third scenario: hardship (the ONLY way fees are refunded) ----
    cancel = client.post(f"/jobs/{job2['job_id']}/cancel", headers=mary, json={})
    if verbose:
        print(f"\n[16. Mary tries to just cancel the confirmed job] HTTP {cancel.status_code}: {cancel.json()['detail']}")
    assert cancel.status_code == 409
    claim = show("17a. Mary files a hardship claim (artisan hospitalised after an accident)", client.post(
        f"/jobs/{job2['job_id']}/hardship-claims", headers=mary, json={
            "kind": "ACCIDENT_OR_SERIOUS_ILLNESS", "affected_party": "ARTISAN",
            "description": "John was admitted to hospital after a road accident."}), ("claim_id", "status", "required_proof"))
    show("17b. She uploads the medical record", client.post(f"/hardship-claims/{claim['claim_id']}/document", headers=mary,
         files={"file": ("medical-record.pdf", b"%PDF-1.4 demo medical record", "application/pdf")}), ("status", "has_document"))
    show("17c. Admin checks the document and approves", client.post(f"/admin/hardship-claims/{claim['claim_id']}/decision",
         headers=admin, json={"approve": True, "notes": "Medical record verified (SIMULATED demo)."}), ("status",))
    refunded = client.get(f"/jobs/{job2['job_id']}", headers=admin).json()
    if verbose:
        print("\n[17d. Result]", refunded["status"], {p["payment_type"]: p["status"] for p in refunded["payments"]})

    # ---- Fourth scenario: "Vouch from Trade-group" (e-mail confirmed; one group, many artisans) ----
    def last_token(to: str) -> str:
        mails = [m for m in client.get("/admin/dev/outbox", headers=admin).json() if m["to"] == to]
        return re.search(r"token=([A-Za-z0-9_\-]+)", mails[-1]["body"]).group(1)

    suffix = random.randint(1000, 9999)
    group_email = f"contact{suffix}@molyko-masons.example"
    group = show("18a. Admin registers a trade group (e-mails its address)", client.post("/admin/trade-groups", headers=admin, json={
        "name": f"Molyko Electricians Guild {suffix}", "email": group_email, "description": "SIMULATED guild"}),
        ("group_id", "status", "email_status"))
    show("18b. Someone at that address confirms the e-mail", client.post("/trade-groups/verify-email", json={
        "token": last_token(group_email)}), ("name",))
    listed = client.get("/trade-groups").json()
    assert all("email" not in g for g in listed)                    # the group's address stays private

    vouched = []
    for n, name in enumerate(("Peter Ayuk", "Quincy Tabe"), start=1):
        phone = new_phone()
        client.post("/auth/register", json={"phone": phone, "password": password, "role": "ARTISAN"})
        headers = auth(phone)
        profile = client.post("/artisans", headers=headers, json={
            "full_name": name, "location": "Molyko, Buea"}).json()
        client.post(f"/artisans/{profile['artisan_id']}/skills", headers=headers, json={
            "skill_id": electrical, "proficiency_level": "INTERMEDIATE", "typical_price": 7000})
        show(f"19.{n}a {name} ticks 'Vouch from Trade-group' -> the group is e-mailed",
             client.post(f"/artisans/{profile['artisan_id']}/trade-group-vouches", headers=headers, json={
                 "group_id": group["group_id"], "skill_id": electrical, "note": f"Member no. {100 + n}"}),
             ("status", "email_status", "message"))
        vouched.append((name, profile["artisan_id"], headers))
    # Each artisan has their OWN e-mail and their OWN link
    mails = [m for m in client.get("/admin/dev/outbox", headers=admin).json() if m["to"] == group_email][-2:]
    tokens = [re.search(r"token=([A-Za-z0-9_\-]+)", m["body"]).group(1) for m in mails]
    assert len(set(tokens)) == 2
    show("20a. The group opens Peter's link (read-only, decides nothing)",
         client.get("/trade-group-vouches/details", params={"token": tokens[0]}), ("artisan_name", "skill_name", "status"))
    show("20b. The group CONFIRMS Peter", client.post("/trade-group-vouches/respond", json={
        "token": tokens[0], "decision": "CONFIRM"}), ("artisan_name", "status"))
    show("20c. ...and DECLINES Quincy (not confirmed => not qualified)", client.post("/trade-group-vouches/respond", json={
        "token": tokens[1], "decision": "REJECT"}), ("artisan_name", "status"))
    peter = client.get(f"/artisans/{vouched[0][1]}").json()
    quincy = client.get(f"/artisans/{vouched[1][1]}").json()
    if verbose:
        print("\n[21. Result] Peter:", peter["skills"][0]["verification_status"], peter["trade_group_vouches"],
              "| Quincy:", quincy["skills"][0]["verification_status"])
    assert peter["skills"][0]["verification_status"] == "VERIFIED" and quincy["skills"][0]["verification_status"] != "VERIFIED"

    final_job = client.get(f"/jobs/{job_id}", headers=mary).json()
    if verbose:
        print("\nAudit trail:", " -> ".join(e["event_type"] for e in final_job["events"]))
    return {"artisan_id": artisan_id, "job": final_job, "matches": matches, "reputation": reputation,
            "inspection_job": refunded, "peter": peter, "quincy": quincy}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--verifier-phone", default=VERIFIER_PHONE)
    parser.add_argument("--admin-phone", default=ADMIN_PHONE)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as http_client:
        run(http_client, args.verifier_phone, args.password, admin_phone=args.admin_phone)
