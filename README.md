# ACbridge

A local reputation and service-matching platform for informal artisans (electricians, plumbers,
carpenters, mechanics, tailors, masons, hairdressers...) in Cameroon. Artisans prove their skill
through **other people** (community endorsements + an authorised verifier + confirmed completed jobs),
and customers can trust what they see because **reviews only exist for jobs both sides confirmed**.

> ⚠️ **Payments are SIMULATED too.** The payment flow (commission, assignment fee, escrow, payouts) is fully
> implemented behind a provider interface, but the only provider is a simulator: **no real money moves**.
> Going live needs MTN MoMo / Orange Money merchant accounts and a provider class (see §6b).
>
> ⚠️ **Verification is SIMULATED in this prototype.** No real-world identity check or practical skill
> assessment takes place. Every verification API response says so (`simulated: true` + a notice) and the
> seed data is labelled fake. Do not present it as real verification.

This repository currently contains the **backend MVP** (`backend/`). A frontend (low-data, mobile-first,
local-language/voice friendly) will live beside it.

```
ACbridge/
├── README.md
└── backend/
    ├── app/
    │   ├── main.py            # FastAPI app, error handler, router wiring
    │   ├── config.py          # settings from environment variables
    │   ├── database.py        # engine + per-request session
    │   ├── models.py          # the 10 SQLAlchemy tables + constraints + indexes + audit triggers
    │   ├── schemas.py         # Pydantic input validation / output shaping
    │   ├── errors.py          # domain errors -> HTTP status codes
    │   ├── init_db.py         # create tables
    │   ├── seed.py            # simulated demo data
    │   ├── routers/           # HTTP only: auth, skills, artisans, verification, requests,
    │   │                      #            matching, jobs, reviews, admin
    │   ├── services/          # business rules: verification, matching, reputation, job (state machine)
    │   └── security/          # authentication (Argon2id, JWT), permissions (RBAC), rate_limit
    ├── scripts/demo.py        # runs the whole John & Mary journey against a live API
    ├── tests/                 # pytest suite (84 tests)
    ├── requirements.txt  .env.example  docker-compose.yml  pytest.ini
```

**Changes from the brief (all deliberate and small):** project renamed to ACbridge; code lives under
`backend/`; added `config.py`, `errors.py`, `init_db.py`, `seed.py`, `rate_limit.py`, `skills.py`, `admin.py`;
and a handful of extra columns the rules need: `skills.safety_critical`, `artisan_skills.typical_price`
(price matching), `artisan_profiles.is_suspended`, `verification_checks.skill_id` (verification is
per-skill) and `verification_checks.evidence_file_path` (private uploads). `jobs` are created by the
customer choosing an artisan (`POST /jobs`) because `jobs.status` starts at `REQUESTED`.

## Using this with your existing frontend

Recommended layout: **one folder, two apps**, so they travel together in one git repo.

```
ACbridge/
├── frontend/     <- your existing frontend (move/copy it here)
└── backend/      <- this repo's backend
```

**Get the backend onto your computer** (pick one):

* *Already have the repo cloned:* `git fetch origin && git checkout feature/backend-mvp` (or `git pull`).
* *Starting from your frontend folder:* put the frontend in `frontend/`, `git init` / clone ACbridge around it,
  then `git checkout feature/backend-mvp` and keep both folders committed together.
* *No git:* download the zip from GitHub (**Code → Download ZIP**, with the branch `feature/backend-mvp`
  selected) and copy its `backend/` folder next to your `frontend/` folder.

**Keeping them in sync**

1. **Base URL.** The API runs at `http://localhost:8000`. Point the frontend at it with an env variable,
   e.g. Vite `VITE_API_URL=http://localhost:8000` / Next.js `NEXT_PUBLIC_API_URL=http://localhost:8000`.
2. **CORS.** The browser blocks calls to another port unless the backend allows the frontend's origin.
   Defaults already allow `localhost`/`127.0.0.1` on ports **5173** (Vite) and **3000** (CRA/Next).
   Any other port or domain: set `CORS_ORIGINS` in `backend/.env` (exact scheme+host+port) and restart.
3. **Auth.** `POST /auth/login` → `access_token`. Send `Authorization: Bearer <token>` on every other call.
   Store the token in memory/`sessionStorage`; on `401` send the user back to login.
4. **The contract.** `backend/openapi.json` lists every endpoint, request body and response shape.
   Use it to check the frontend's calls or generate a typed client
   (e.g. `npx openapi-typescript backend/openapi.json -o frontend/src/api-types.ts`).
   A test fails when the API changes without regenerating it:
   `cd backend && python -m scripts.export_openapi`.
5. **Payment flow & breaking change.** `POST /jobs` now takes `proposed_price` (was `agreed_price`); accepting a job returns a `payment_due` the artisan must approve before the job becomes `ACCEPTED`; the customer pays via `POST /jobs/{id}/pay`; match results include `contact` (WhatsApp). See §6b and `openapi.json`.
6. **Errors.** Failures return `{"detail": "..."}`; validation errors (`422`) return `detail` as a list.
   Show the string to the user. IDs are UUID strings; money is integer FCFA; dates are ISO-8601 UTC.
7. **Run both:** terminal 1 `cd backend && uvicorn app.main:app --reload`; terminal 2 `cd frontend && npm run dev`.

> If your frontend already calls endpoints with different names or fields than this API, share its
> folder (or the list of calls it makes) and the two sides can be aligned deliberately.

## 1. Architecture

A **modular monolith**: one deployable FastAPI process, separated into layers with one job each.

| Layer | Responsibility | Never does |
|---|---|---|
| `routers/` | parse HTTP, call a service, shape the response | business rules |
| `schemas.py` | validate input, hide private fields in output | touch the database |
| `services/` | business rules, algorithms, state machine, transactions | import FastAPI |
| `models.py` | tables, relationships, DB-level constraints | contain logic |
| `security/` | who are you (JWT) and what may you do (roles) | |

Why a monolith? Two hours, 2–3 developers: one codebase, one database and ACID transactions across
"job + request + audit event" are worth far more than microservice flexibility we don't need.

### Database relationships

| Relationship | Cardinality | How |
|---|---|---|
| users ↔ artisan_profiles | 1 : 0..1 | `artisan_profiles.user_id` UNIQUE |
| artisan_profiles ↔ skills | **M : N** | junction `artisan_skills`, composite PK `(artisan_id, skill_id)` |
| artisan_profiles → endorsements | 1 : N | UNIQUE `(artisan_id, endorser_id)` stops duplicates |
| artisan_profiles → verification_checks | 1 : N | each SKILL check also points to one skill |
| users → service_requests, skills → service_requests | 1 : N | |
| service_requests ↔ jobs | 1 : 0..1 | `jobs.request_id` UNIQUE (one artisan per request) |
| artisan_profiles → jobs → job_events | 1 : N → 1 : N | events are append-only |
| jobs → reviews | 1 : N | UNIQUE `(job_id, reviewer_id)`; only the customer may review |

Integrity enforced **by the database**, not just Python: PK/FK/UNIQUE on all of the above; `CHECK` on
roles, statuses, `rating BETWEEN 1 AND 5`, `budget >= 0`, `agreed_price >= 0`, and
`jobs.status <> 'COMPLETED' OR (both confirmations AND completed_at)`; a trigger that makes `job_events`
reject `UPDATE`/`DELETE`; indexes on skill, location, verification status, request status, job status.

## 2. Setup

Requires Python 3.11+ and PostgreSQL 14+.

```bash
git clone https://github.com/override0237/ACbridge.git
cd ACbridge/backend
git checkout feature/backend-mvp        # until merged into main
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                    # then edit it (set a real JWT_SECRET)
```

**PostgreSQL** — either Docker:

```bash
docker compose up -d db
```

or an existing server:

```bash
sudo -u postgres psql -c "CREATE USER acbridge WITH PASSWORD 'acbridge' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE acbridge OWNER acbridge;"
sudo -u postgres psql -c "CREATE DATABASE acbridge_test OWNER acbridge;"
```

**Create tables and load the (simulated) demo data, then start the API:**

```bash
python -m app.init_db
python -m app.seed
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs (click **Authorize** and paste a token from `/auth/login`).

> Migrations: the MVP creates tables with `create_all`. For a real deployment adopt Alembic
> (`alembic revision --autogenerate`); the explicit constraint names in `models.py` are ready for it.

## 3. Run the tests

```bash
pytest                                   # in-memory SQLite, no setup, ~35 s
TEST_DATABASE_URL=postgresql+psycopg://acbridge:acbridge@localhost:5432/acbridge_test pytest   # real PostgreSQL
```

Both modes pass (**84 on PostgreSQL; SQLite runs 83 and skips the concurrency test**, because
row locks need PostgreSQL). The tests cover every rule in the brief: auth, self-endorsement,
unauthorised verification, the approval workflow, eligibility/ranking maths, job state machine,
duplicate/unrelated confirmations, review rules, Bayesian reputation, DB-level constraints
and the whole demo journey (`tests/test_demo_journey.py`).

## 4. Demonstration (John the electrician, Mary the customer)

With the API running and the seed loaded:

```bash
python -m scripts.demo --base-url http://localhost:8000
```

Seeded **simulated** staff: admin `+237670000001`, verifier `+237670000002`, password `Demo-Pass-123!`
(local demos only). Seeded competitors for "Electrical Repair": **Paul** (Molyko, 8 completed jobs),
**Samuel** (unverified), **Esther** (unavailable), **Ngu** (Limbe, outside the service area), plus a plumber and a tailor.

The script performs exactly the 14 steps of the brief. Real output (trimmed):

| # | Action | Result |
|---|---|---|
| 1–2 | John registers, creates profile in *Small Soppo, Buea*, adds Electrical Repair | skill is `UNVERIFIED` (he cannot set that) |
| 3 | Two independent users endorse him | `201` ×2 |
| 4 | John submits evidence → verifier claims → verifier approves | `PENDING → UNDER_REVIEW → APPROVED`, `simulated: true` |
| 5–7 | Mary registers, requests repair in *Small Soppo, Buea*, budget 10 000 FCFA | request `OPEN` |
| 8 | `GET /matches/{request_id}` | John **86.50**, Paul **85.05**; 3 excluded with reasons |
| 9–10 | Mary books John, John accepts and starts | `REQUESTED → ACCEPTED → IN_PROGRESS` |
| 11–12 | John confirms → `PENDING_CONFIRMATION`; Mary confirms → `COMPLETED` | |
| 13–14 | Mary reviews 5★ | reputation **4.0909**, 1 verified review |

Match response excerpt (John):

```json
{ "full_name": "John Fon", "skill_verification_status": "VERIFIED", "match_score": 86.5,
  "breakdown": { "skill": 85.0, "location": 100.0, "availability": 100.0, "work_history": 45.0, "price": 100.0 } }
```
`"excluded_summary": {"UNAVAILABLE": 1, "SKILL_NOT_VERIFIED_FOR_SAFETY_CRITICAL_WORK": 1, "OUTSIDE_SERVICE_AREA": 1}`

Audit trail: `JOB_REQUESTED → JOB_ACCEPTED → JOB_STARTED → COMPLETION_CONFIRMED → JOB_PENDING_CONFIRMATION → COMPLETION_CONFIRMED → JOB_COMPLETED`.

## 5. API summary

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login` |
| Skills | `GET /skills`, `POST /skills` (admin) |
| Artisans | `POST /artisans`, `GET/PATCH /artisans/{id}`, `POST /artisans/{id}/skills`, `POST /artisans/{id}/endorsements`, `GET /artisans/{id}/reputation` |
| Verification | `POST/GET /verifications`, `GET /verifications/{id}`, `POST /verifications/{id}/decision`, `POST/GET /verifications/{id}/evidence` |
| Requests / matching | `POST /service-requests`, `GET /service-requests/{id}`, `GET /matches/{request_id}` |
| Jobs | `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/accept`, `/pay`, `/quote`, `/quote/respond`, `/start`, `/confirm-completion`, `/cancel`, `/dispute` |
| Payments | `GET /pricing`, `GET /jobs/{id}/payments`, `GET /payments/{id}`, `POST /payments/{id}/simulate-approval`, `/simulate-failure` (simulated mode only) |
| Reviews | `POST /jobs/{id}/reviews`, `GET /reviews/mine` |
| Admin | `POST /admin/users/{id}/role`, `/admin/artisans/{id}/suspend`, `/unsuspend`, `/admin/jobs/{id}/resolve-dispute` |

There is **no endpoint that sets a job status directly**; each action is one validated transition.

## 6. Key engineering decisions

* **Roles.** Only `CUSTOMER` / `ARTISAN` can be chosen at registration. `VERIFIER`/`ADMIN` are granted by an admin. The role is read from the database on every request, never trusted from the token.
* **Verification is per skill.** Approving "Electrical Repair" changes only that `artisan_skills` row; identity is a separate `IDENTITY` check. A SKILL approval additionally requires ≥ 2 distinct community endorsements. A verifier cannot verify themselves nor an artisan they endorsed.
* **Matching** is two-stage and deterministic. *Stage 1* hard filters (skill, not suspended, available, in the supported town, verified for safety-critical skills) — a high score can never buy back a missing qualification. *Stage 2*: `M = 0.35S + 0.25L + 0.15A + 0.15R + 0.10P` with weights in one constant (`WEIGHTS`, asserted to sum to 1):
  * **S** = ½·proficiency (40/70/100) + ½·verification (VERIFIED 100, PENDING 30, else 0)
  * **L** = 100 same neighbourhood, 60 same town (location is the text `"Neighbourhood, Town"` — no geo infrastructure)
  * **A** = AVAILABLE 100, BUSY 50
  * **R** = 0.6·(Bayesian rating mapped to 0–100) + 0.4·(completed jobs ÷ 10, capped); newcomers get a neutral 45
  * **P** = 100 if the artisan's typical price ≤ budget, falling linearly to 0 at 2× budget; **50** if either is unknown
  The response includes the breakdown, the weights, why others were excluded, and a disclaimer that the score is *not* proof of trustworthiness.
* **Reputation:** `R = v/(v+m)·A + m/(v+m)·C`, `m = 10`, `C = 4.0`. Five 5★ reviews → **4.333**; eighty reviews averaging 4.7 → **4.622**, so volume of evidence beats a short perfect record. Identity, skill verification and reputation are returned as three separate fields.
* **Job state machine** (`job_service.ALLOWED_TRANSITIONS`): `REQUESTED → ACCEPTED → IN_PROGRESS → PENDING_CONFIRMATION → COMPLETED`, with `DISPUTED`/`CANCELLED`. Every transition locks the job row (`SELECT … FOR UPDATE`), writes a `job_events` row and commits in **one transaction**. Repeated confirmations are idempotent (safe on flaky mobile networks). A concurrency test fires six simultaneous confirmations at PostgreSQL and checks one `JOB_COMPLETED`.
* **Anti-fraud:** unique phones; duplicate skills/endorsements/reviews blocked by DB constraints (race-safe); reviews only from the customer of a COMPLETED job; completion needs both parties; append-only audit trail; verifiers see *hints* (`review_signals`, e.g. endorsers who registered the same day) for **human** judgement — nothing is auto-flagged as fraud; rate limits on register/login/upload; uploads checked by extension *and* file header, size-capped, stored under server-generated names, served only to the owner/verifiers/admins.
* **Privacy:** password hashes (Argon2id), evidence text/files and phone numbers never appear on public profiles. Phone numbers are exchanged only between the two parties of an accepted job.

## 6b. WhatsApp contact and platform payments

### WhatsApp at the matching stage
Every match in `GET /matches/{request_id}` carries a `contact` object:
`{"channel": "WHATSAPP", "icon": "whatsapp", "label": "Chat on WhatsApp", "link": "https://wa.me/237…?text=…", "tip": "…"}`.
The frontend shows the WhatsApp icon and opens `link` (WhatsApp opens on the customer's phone with a prefilled
message naming the trade, area, budget and request reference, so the artisan knows what it is about).
No WhatsApp Business API is needed.

* **Opt-in:** an artisan only gets a `contact` if they set `whatsapp_number` (on `POST /artisans` or `PATCH /artisans/{id}`). Otherwise `contact` is `null` and the UI hides the icon.
* **Privacy:** the number appears only in the match results of the customer who made the request (never on public profiles; the public profile shows just `whatsapp_available`). The customer's number is not revealed to the artisan until they choose to start the chat. After a job is accepted, both parties get `counterpart_whatsapp_link` on the job.
* The `tip` reminds people to book and pay inside ACbridge: only paid, confirmed jobs earn reviews and escrow protection.

### Payments through the platform
Fees are paid by the **artisan** and are charged when the artisan agrees to the price, as you specified.
`GET /pricing` publishes the policy so artisans see it first. Defaults (env-configurable): **5%** commission,
minimum **300 FCFA**, flat inspection fee **1000 FCFA**.

| | Normal request (price known) | Request flagged `needs_inspection` |
|---|---|---|
| Customer | `POST /jobs` with `proposed_price` | `POST /jobs` **without** a price |
| Artisan agrees | `POST /jobs/{id}/accept` → pays **COMMISSION** (% of the price) | `POST /jobs/{id}/accept` → pays flat **ASSIGNMENT_FEE** |
| Job becomes `ACCEPTED` | only after the fee is paid | only after the fee is paid |
| Price | the proposed amount | artisan `POST /jobs/{id}/quote`, customer `POST /jobs/{id}/quote/respond` (approve/reject; artisan can re-quote) |

Then, for both: the customer pays the agreed price into **escrow** (`POST /jobs/{id}/pay`); work cannot start until
it is held; when **both** sides confirm completion the escrow is **released** to the artisan (full amount, because the
commission was already paid) and `PAYOUT_RELEASED` is audited. If the job is cancelled, or an admin cancels a dispute,
the escrow is **refunded** and any unapproved charge is voided.

Safeguards: integer FCFA only (no float money errors); a partial unique index allows only **one non-failed payment
per type per job** (no double charges, even under races); `accept`/`pay` are idempotent; settling a payment twice is
harmless; the database refuses a started/completed job with no agreed price; every payment step is a row in `payments`
and an append-only `job_events` entry. Platform fees already paid are **not** refunded automatically (policy: an admin
handles exceptions).

**Simulated mode:** the payer "approves the mobile-money prompt" with `POST /payments/{id}/simulate-approval`
(or `/simulate-failure`). In production these routes disappear and a signed provider webhook calls
`job_service.settle_payment`; the app **refuses to start in production with the simulated provider**.

## 7. Engineering theory — what is implemented vs. only theoretical

| Concept | Where / status |
|---|---|
| **3NF relational design** | Implemented. Facts live in one place: skill names in `skills`, the M:N link in `artisan_skills`, reputation is *derived* (not stored) so it cannot go stale. |
| **Primary / foreign keys, M:N** | Implemented (UUID PKs, composite PK on `artisan_skills`). |
| **Hash tables / indexed lookups** | PostgreSQL B-tree indexes give O(log n) lookups (hash-style point lookups on PK/UNIQUE). Python `dict`/`set` are used for scoring tables and exclusion counts. We do not build custom hash tables. |
| **Priority queue / sorting** | Implemented: `heapq.nlargest(k, …)` selects the top-k candidates in O(n log k) with a deterministic tie-break. |
| **State machine** | Implemented: explicit transition table for jobs, and for verification checks. |
| **ACID transactions** | Implemented: each state change is one transaction with row locks (isolation), CHECK/FK constraints (consistency), commit/rollback (atomicity/durability from PostgreSQL). |
| **Matching complexity** | n = artisans holding the skill, k = results: query by indexed skill, eligibility + scoring **O(n)**, top-k **O(n log k)**, memory **O(n)**; reputation uses two grouped queries (no N+1). Fine for a town; for city scale push the location/availability filters into SQL. |
| **Indexing** | Implemented (see `models.py`), e.g. composite `(skill_id, verification_status)` serves the matcher's first query. |
| **AuthN / RBAC** | Implemented: Argon2id, JWT (HS256, pinned algorithm, expiry), role dependencies, ownership checks in services. |
| **Graph theory for community trust** | **Not implemented — future work.** Endorsements are already edges (user → artisan); a later version could run PageRank/TrustRank or detect closed endorsement rings (collusion) on that graph. |

## 8. Known limitations and next steps

* Verification is simulated; real use needs a legitimate process (in-person assessment, trade-group leaders, ID checks).
* Self-endorsement and "verifier endorsed this artisan" are enforced in the service layer (they span tables); a DB trigger would add defence in depth.
* A cancelled/declined job leaves its request closed (one job per request) — the customer creates a new request.
* Rate limiter is in-memory and per process (use Redis for several workers/servers); behind a proxy run uvicorn with `--proxy-headers`.
* JWTs are not revocable before expiry (60 min); no refresh tokens, password reset or SMS/OTP phone verification yet.
* Evidence files live on local disk; use object storage with malware scanning in production.
* No Alembic migrations yet; money is integer FCFA; currency/payments/commission (the revenue model — e.g. a small customer-paid booking fee) are not built.
* Payments are simulated; real MTN MoMo / Orange Money integration, signed webhooks, payout failures and reconciliation are future work. Charging the artisan at agreement (instead of after the job) means artisans pay before they earn; consider refunding the fee when a job is cancelled by the customer.
* Price negotiation is one-directional for normal jobs (the customer proposes, the artisan accepts or declines); counter-offers are not built.
* WhatsApp links open a chat only; messages are not stored by ACbridge, so chat content cannot be used as evidence in disputes.
* Not yet done for the stated users: USSD/WhatsApp/voice interfaces, local-language strings, completion codes by SMS, offline-tolerant client.
