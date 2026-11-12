"""Build a browsable SQLite copy of the ACbridge backend database, filled with simulated demo data.

    python scripts/build_database.py [output_folder]        (default: ../frontend/database)

It creates the SAME tables as the real backend (app/models.py), seeds the catalogue and demo artisans (app/seed.py), and then
plays several complete scenarios through the real API (in-process), so the file contains registered artisans, customers,
requests, offers, chat messages, payments, the double-entry ledger, payouts, audit trail, an expired offer, a held payout...
EVERYTHING IS SIMULATED: no real people, no real money. Demo password for every seeded account: Demo-Pass-123!

Output: acbridge.db, schema.sql, views.sql and one CSV per table / view in csv/.
"""
import csv
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (BACKEND.parent / "frontend" / "database")
OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "acbridge.db"
for suffix in ("", "-journal", "-wal", "-shm"):
    (OUT / f"acbridge.db{suffix}").unlink(missing_ok=True)

# Settings must be in place BEFORE the app is imported (the engine is created at import time).
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB.as_posix()}", "ENVIRONMENT": "development", "RATE_LIMIT_ENABLED": "false",
    "PROBATION_HOURS": "0", "COMMISSION_MODEL": "customer_split", "EVIDENCE_UPLOAD_DIR": str(OUT / "_uploads"),
})
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Job  # noqa: E402
from app.seed import DEMO_PASSWORD, ADMIN_PHONE, VERIFIER_PHONE, seed  # noqa: E402

Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed(db)

client = TestClient(app)


def call(method, path, token=None, expect=(200, 201), **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = client.request(method, path, headers=headers, **kw)
    assert res.status_code in expect, f"{method} {path} -> {res.status_code} {res.text}"
    return res.json() if res.content else None


def login(phone, password=DEMO_PASSWORD):
    return call("POST", "/auth/login", json={"phone": phone, "password": password})["access_token"]


def register(phone, role, password=DEMO_PASSWORD):
    call("POST", "/auth/register", json={"phone": phone, "password": password, "role": role})
    return login(phone, password)


skills = {s["skill_name"]: s["skill_id"] for s in call("GET", "/skills")}
admin = login(ADMIN_PHONE)
verifier = login(VERIFIER_PHONE)
GRACE, PAUL, PETER = "+237690000015", "+237690000011", "+237690000014"   # seeded plumber / electricians
artisan_id = {}
for name, phone in (("Grace", GRACE), ("Paul", PAUL), ("Peter", PETER)):
    # the seed does not expose artisan ids by phone, so read them from the database
    with SessionLocal() as db:
        from sqlalchemy import select
        from app.models import ArtisanProfile, User
        artisan_id[name] = str(db.scalar(select(ArtisanProfile.artisan_id).join(User, User.user_id == ArtisanProfile.user_id).where(User.phone == phone)))


def customer_request(token, skill, description, location, budget, urgency):
    return call("POST", "/service-requests", token, json={
        "skill_id": skills[skill], "description": description, "location": location, "budget": budget, "urgency": urgency})["request_id"]


def offer(token, request_id, name, price):
    return call("POST", "/jobs", token, json={"request_id": request_id, "artisan_id": artisan_id[name], "proposed_price": price})["job_id"]


def say(token, job_id, text):
    return call("POST", f"/jobs/{job_id}/messages", token, json={"body": text})


def agree_and_pay(customer, artisan, job_id):
    call("POST", f"/jobs/{job_id}/accept", artisan)
    call("POST", f"/jobs/{job_id}/confirm-terms", artisan)
    res = client.post(f"/jobs/{job_id}/pay", headers={"Authorization": f"Bearer {customer}", "Idempotency-Key": f"demo-{job_id[:8]}"})
    assert res.status_code == 201, res.text
    call("POST", f"/payments/{res.json()['payment_id']}/simulate-approval", customer)
    return res.json()["payment_id"]


def finish(customer, artisan, job_id):
    call("POST", f"/jobs/{job_id}/start", artisan)
    call("POST", f"/jobs/{job_id}/confirm-completion", artisan)
    call("POST", f"/jobs/{job_id}/confirm-completion", customer)


# ---------------------------------------------------------------------------- customers
mary = login("+237690000030")                      # seeded customer with a history of completed jobs
joseph = register("+237670555111", "CUSTOMER")
aline = register("+237670555222", "CUSTOMER")
grace, paul, peter = login(GRACE), login(PAUL), login(PETER)

# S1: a complete, paid, confirmed and reviewed plumbing job (bargained in the chat)
r1 = customer_request(mary, "Plumbing", "The kitchen tap is leaking", "Molyko, Buea", 8000, "TODAY")
j1 = offer(mary, r1, "Grace", 5500)
say(mary, j1, "Hello Grace, can you do it cheaper?")
say(grace, j1, "I can do it for 7 000 FCFA")
say(mary, j1, "Final price: 6000 FCFA")
agree_and_pay(mary, grace, j1)
finish(mary, grace, j1)
call("POST", f"/jobs/{j1}/reviews", mary, json={"rating": 5, "comment": "Fixed quickly, fair price."})

# S2: paid and in progress (the artisan's share waits as a PENDING payout)
r2 = customer_request(joseph, "Electrical Repair", "Sockets sparking in the living room", "Small Soppo, Buea", 15000, "THIS_WEEK")
j2 = offer(joseph, r2, "Paul", 9000)
say(joseph, j2, "Can you come tomorrow? 12000 FCFA")
agree_and_pay(joseph, paul, j2)
call("POST", f"/jobs/{j2}/start", paul)

# S3: finished, but an operator HELD the payout (customer complained), so it stays held
r3 = customer_request(aline, "Electrical Repair", "Rewire the shop", "Down Beach, Limbe", 12000, "NOT_URGENT")
j3 = offer(aline, r3, "Peter", 8000)
agree_and_pay(aline, peter, j3)
payout3 = [p for p in call("GET", "/operator/payouts", admin) if p["job_id"] == j3][0]["payout_id"]
call("POST", f"/operator/payouts/{payout3}/hold", admin, json={"reason": "Customer reported a problem, checking with both sides"})
finish(aline, peter, j3)

# S4: a request nobody has been chosen for yet
customer_request(mary, "Carpentry", "Repair a wooden door", "Great Soppo, Buea", 20000, "NOT_URGENT")

# S5: an offer that expired because the artisan did not accept within the hour (urgent request)
r5 = customer_request(joseph, "Plumbing", "Burst pipe", "Molyko, Buea", 9000, "TODAY")
j5 = offer(joseph, r5, "Grace", 7000)
with SessionLocal() as db:
    job = db.get(Job, uuid.UUID(j5))
    job.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db.commit()
call("GET", f"/jobs/{j5}", joseph)                    # reading an overdue offer nullifies it

# S6: an offer still waiting for the artisan, with a bargaining conversation in progress
r6 = customer_request(aline, "Electrical Repair", "Install two ceiling lights", "Molyko, Buea", 10000, "NOT_URGENT")
j6 = offer(aline, r6, "Paul", 6000)
say(aline, j6, "Hello, are you available this month?")
say(paul, j6, "Yes. I would charge 9 000 FCFA")

# S7: a new artisan registers, adds a skill and collects endorsements; the skill check is waiting for the verifier
john = register("+237670777999", "ARTISAN")
john_profile = call("POST", "/artisans", john, json={"full_name": "John Fon", "location": "Small Soppo, Buea",
                                                       "description": "Plumber, 10 years' experience"})
call("POST", f"/artisans/{john_profile['artisan_id']}/skills", john, json={
    "skill_id": skills["Plumbing"], "proficiency_level": "INTERMEDIATE", "typical_price": 6000})
for phone in ("+237670888111", "+237670888222"):
    endorser = register(phone, "CUSTOMER")
    call("POST", f"/artisans/{john_profile['artisan_id']}/endorsements", endorser, json={
        "evidence_description": "John repaired the pipes in my shop and it has worked perfectly since."})
call("POST", "/verifications", john, json={"check_type": "SKILL", "skill_id": skills["Plumbing"],
                                           "evidence_description": "Ten years fixing pipes and taps in Buea."})
client.close()
engine.dispose()

# ---------------------------------------------------------------------------- views, schema, CSV
VIEWS = """
CREATE VIEW v_accounts AS
SELECT u.user_id, u.phone, u.role, a.full_name AS artisan_name, a.location AS artisan_location,
       a.availability_status, a.is_suspended, u.created_at
FROM users u LEFT JOIN artisan_profiles a ON a.user_id = u.user_id;

CREATE VIEW v_artisans AS
SELECT a.artisan_id, a.full_name, u.phone, a.location, a.availability_status, s.skill_name, k.proficiency_level,
       k.verification_status AS skill_verification, k.typical_price,
       (SELECT COUNT(*) FROM endorsements e WHERE e.artisan_id = a.artisan_id) AS endorsements
FROM artisan_profiles a JOIN users u ON u.user_id = a.user_id
LEFT JOIN artisan_skills k ON k.artisan_id = a.artisan_id LEFT JOIN skills s ON s.skill_id = k.skill_id;

CREATE VIEW v_customer_requests AS
SELECT r.request_id, cu.phone AS customer_phone, s.skill_name, r.description, r.location, r.budget, r.urgency, r.status AS request_status,
       j.job_id, ap.full_name AS artisan_name, j.status AS job_status, j.proposed_price, j.agreed_price, r.created_at
FROM service_requests r JOIN users cu ON cu.user_id = r.customer_id JOIN skills s ON s.skill_id = r.skill_id
LEFT JOIN jobs j ON j.request_id = r.request_id LEFT JOIN artisan_profiles ap ON ap.artisan_id = j.artisan_id;

CREATE VIEW v_payments AS
SELECT p.payment_id, p.job_id, ap.full_name AS artisan_name, cu.phone AS payer_phone, p.payment_type, p.amount, p.currency,
       p.status, p.provider, p.provider_reference, p.created_at, p.settled_at
FROM payments p JOIN jobs j ON j.job_id = p.job_id JOIN artisan_profiles ap ON ap.artisan_id = j.artisan_id
JOIN users cu ON cu.user_id = p.payer_id;

CREATE VIEW v_payouts AS
SELECT po.payout_id, ap.full_name AS artisan_name, po.amount, po.commission, po.status, po.note, po.provider_reference, po.job_id
FROM payouts po JOIN artisan_profiles ap ON ap.artisan_id = po.artisan_id;

CREATE VIEW v_ledger_balances AS
SELECT account,
       CASE WHEN account = 'collection'
            THEN SUM(CASE WHEN direction = 'DEBIT' THEN amount ELSE -amount END)
            ELSE SUM(CASE WHEN direction = 'CREDIT' THEN amount ELSE -amount END) END AS balance
FROM ledger_entries GROUP BY account;

CREATE VIEW v_chat AS
SELECT m.created_at, m.job_id, m.sender_role, m.body, m.proposed_price FROM job_messages m ORDER BY m.created_at;
"""
con = sqlite3.connect(DB)
con.executescript(VIEWS)
con.commit()
(OUT / "views.sql").write_text(VIEWS.strip() + "\n", encoding="utf-8")
schema = [r[0] + ";" for r in con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND type IN ('table', 'index') ORDER BY type DESC, name")]
(OUT / "schema.sql").write_text("-- ACbridge backend schema (SQLite flavour of app/models.py)\n\n" + "\n\n".join(schema) + "\n", encoding="utf-8")

csv_dir = OUT / "csv"
csv_dir.mkdir(exist_ok=True)
for old in csv_dir.glob("*.csv"):
    old.unlink()
names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name")]
counts = {}
for name in names:
    cur = con.execute(f'SELECT * FROM "{name}"')
    rows = cur.fetchall()
    counts[name] = len(rows)
    with open(csv_dir / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        w.writerows(rows)
con.close()
import shutil  # noqa: E402
shutil.rmtree(OUT / "_uploads", ignore_errors=True)
print(f"Wrote {DB}")
for name, n in counts.items():
    print(f"  {name:<22} {n:>4} rows")
