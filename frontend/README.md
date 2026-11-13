# ACbridge front end (demo)

Mobile-first React 18 + TypeScript + Vite demo of the ACbridge journey: **any trade** (plumber, electrician, tailor, or whatever the customer types), **Neighbourhood A**,
French / English. No UI library, no external fonts/images/CDN, no network needed after first load.

> Everything is **simulated**: people, SMS and verification. Nothing real is sent or checked.

## Just open it

**Double-click `frontend/acbridge.html`.** It is one self-contained file (JS and CSS inlined), so it works from a plain file with no server and no internet.
(The old `index.html` is only the Vite dev entry point; opened directly it shows a blank page because browsers block its module script.)
Rebuild it with `npm run build`.

## Setup

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run test     # Vitest: rules, translations, full journey
npm run build    # type-check + production build
```

**Operator PIN (demo): `1234`** (link in the footer).

## Two modes

| Mode | How | What it does |
|---|---|---|
| **Offline demo** (default) | `npm run dev` | Everything runs in the browser, state in `localStorage`. This is the mode the acceptance criteria refer to. |
| **Backend sync** | `VITE_API_MODE=api npm run dev` | Same UI, and every step is mirrored to the FastAPI backend in `../backend` through a Vite proxy (`/api` → `http://localhost:8000`, override with `VITE_BACKEND_URL`). Through the dev proxy no CORS setting is needed. |

**Easiest way to connect:** start the backend, open `acbridge.html`, click **Connect backend** in the footer (default `http://localhost:8000`). Or open `acbridge.html?api=http://localhost:8000`; use `?api=off` to go back offline. The backend only allows the origins in its `CORS_ORIGINS` setting (default: localhost:5173 and :3000), and a page opened from a file has the origin `null`, so start the backend with `CORS_ORIGINS=*` (or `null`) for local demos, e.g. `CORS_ORIGINS='*' uvicorn app.main:app`.

Backend sync prerequisites: run the backend (`uvicorn app.main:app`), then `python -m app.init_db && python -m app.seed`.
If a backend call fails, the demo keeps working offline and shows a red notice.

### How the front end maps to the backend

| Front end | Backend (`feature/backend-mvp`) |
|---|---|
| Artisan registers | `POST /auth/register` (ARTISAN) → `POST /artisans` → `POST /artisans/{id}/skills` (the artisan's trade, typical price) |
| "Simulate vouch from Seed Artisan 1 / 2" | `POST /artisans/{id}/endorsements`, logged in as the seeded artisans Grace (`+237690000015`) and Paul (`+237690000011`) |
| Verified after the 2nd vouch | `POST /verifications` (SKILL) + simulated verifier (`+237670000002`) `UNDER_REVIEW` → `APPROVED`. The backend itself refuses approval with fewer than 2 endorsements. |
| Operator Approve / Reject | verifier decision on the artisan's check |
| Customer request | `POST /service-requests` as seeded customer Mary (`+237690000030`), then `GET /matches/{id}` to link local artisans to backend ids |
| Choose artisan | `POST /jobs` |
| Artisan taps YES | `POST /jobs/{id}/accept` |
| Correct job code | `start`, then `confirm-completion` for the artisan **and** the customer (the code stands for both confirmations) |
| Rate | `POST /jobs/{id}/reviews` (one per job; backend enforces UNIQUE) |

Seed names and phones in `src/data/seed.ts` mirror `backend/app/seed.py` (Grace, Paul, Esther, Peter, Samuel, Rose) plus three offline-only artisans (Daniel carpentry, Fabrice mechanics, Blaise plumbing).

### Known gaps between the brief and the backend (please read)

1. **Job code is front-end only.** The backend has no code endpoint; it completes a job when both sides call
   `confirm-completion`. The code is generated, hashed and checked in the browser, and a correct code triggers both
   confirmations. A real code needs a small backend addition (`code_hash` on `jobs`, `POST /jobs/{id}/complete-with-code`).
2. **Trust score is local.** The backend uses a Bayesian-smoothed `reputation_score`; the brief asks for
   "average weighted by job count + 0.2 per vouch, capped at 5.0". The UI follows the brief (`src/domain/rules.ts`).
3. **Trades.** Artisans and customers type a trade (suggestions: plumber, electrician, carpenter, mason, mechanic, tailor, hairdresser; free text such as "welder" also works offline). The backend only knows the seven catalogue skills and only admins can add skills, so a free-text trade stays local in sync mode (a notice explains it). The backend seed has Grace (plumbing), Paul, Esther, Peter (electrical) and Rose (tailoring, unverified there); Daniel, Fabrice and Blaise exist only in the offline seed. Vouchers may be verified artisans of any trade.
4. **Vouch needs a "worked together" attestation.** The brief says a vouch must come from someone who completed a
   job with the artisan, but also that two seeded artisans vouch for a brand-new one. The demo button records the
   vouch with that attestation set; the rule rejects a vouch without it.
5. **Phone/password for the demo accounts** is the backend's local demo password. Real auth is out of scope.
6. **Commission model.** The demo uses the payments module's `customer_split` model: the customer pays the full agreed price and the 5% commission is booked at that moment. Start the backend with `COMMISSION_MODEL=customer_split` in sync mode (the default `artisan_upfront` charges the artisan before assignment and the offline demo would not match). The backend also has a 300 FCFA minimum commission, so amounts under 6,000 FCFA differ from the demo's plain 5%.
7. **Usernames are front-end only.** The backend logs in with phone + password, so in sync mode the front end uses the artisan's phone and the password they typed (kept in memory for the session only). Seeded artisans use the backend's demo password.

## 60-second walkthrough

1. Home → **I am an artisan** → **I am new** → name, phone (`670123456`), trade (e.g. Plumber), username, password (8+ characters), description → **Register** (returning artisans choose **I have an account** and log in with username + password; demo accounts are `grace`, `paul`, … with password `Demo-Pass-123!`). The SMS panel shows two vouch requests.
2. Tap **Simulate vouch 1**: still "1 of 2". Tap **Simulate vouch 2**: **Verified**, SMS sent.
3. Back to Home → **I need a service** → type the artisan you need (e.g. Plumber), pick urgency → **Find artisans**. The list appears instantly and only shows verified artisans of that trade; your new artisan is in it.
4. Tap **Choose** on any artisan (e.g. yours) → **Confirm** (the price breakdown with the 5% commission is shown first).
5. Job tracking → **Connect flexibly** to bargain (the customer bargains; the artisan ends a message with the final price, e.g. `9000 FCFA`) → **Open as artisan** → **YES**. The price is now agreed but there is **no job code yet**.
6. Home → **My job** → **Payments** → **Pay now** → MTN or Orange + a phone number → the sandbox approves after 5 seconds (number `600000000` is always declined, to show the failure screen). Only now is the **job code** sent (SMS panel, to the customer) and the artisan's phone shown.
7. Artisan → **Job inbox** → **Finish job** → type a wrong code (error, nothing happens) → type the right code → completed and the payout is paid.
8. Tracking → **Rate job** → pick stars → **Send rating** → "Thank you. Your rating is recorded." Rating again is rejected.
9. Open the artisan's **profile** (trust score and rating) and the **Operator** panel (PIN `1234`): payments, ledger balances (platform revenue 275, artisan paid 5 225 for a 5 500 FCFA job), payouts with Hold/Release (a reason is required), reconciliation (try **Simulate mismatch**) and the audit log.

## Acceptance criteria → where to see them

| # | Criterion | Where |
|---|---|---|
| 1 | install / dev / test succeed | terminal: `npm install`, `npm run dev`, `npm run test` |
| 2 | Full journey in one session | Home → … → Rate (walkthrough above) |
| 3 | Wrong job code errors, job not completed | Artisan complete-job screen (keypad) |
| 4 | Second rating on same job rejected | Rate screen (reopen after rating shows the error); `rules.test.ts` |
| 5 | One vouch ≠ verified, second = verified | Artisan status / vouch panel |
| 6 | ≤ 5 matches, none unverified | Match results (Samuel, pending, never shown; other trades never shown); `rules.test.ts` |
| 7 | Works at 375 px | every screen, single column; SMS log collapses under the page |
| 8 | FR/EN updates every string incl. SMS labels | language toggle (top right), SMS panel re-renders in the chosen language |
| 9 | SMS log shows every message with recipient, in order | Simulated SMS panel |
| 10 | Wrong operator PIN blocked | Operator panel (footer link) |

## Structure

```
src/
  domain/rules.ts      pure business rules (tested)      data/seed.ts   seed artisans, customer, operator
  store/               reducer, persistence, provider    i18n/          fr.ts, en.ts, local.ts (placeholder → French)
  api/                 backend client + bridge           components/    Button, Card, StarRating, SmsLog, LanguageToggle, SpeakButton, Screen
  screens/             one file per screen               config.ts      commission rate, PIN, limits, API mode
```

## Putting it online

- **Front end:** `.github/workflows/pages.yml` builds and publishes `acbridge.html` as the site root on GitHub Pages.
  In the repo go to *Settings → Pages → Source: GitHub Actions*. If Pages refuses deployments from the feature branch,
  allow it under *Settings → Environments → github-pages → Deployment branches*, or merge to the default branch.
- **Back end:** `render.yaml` (repo root) is a Render Blueprint: PostgreSQL + the FastAPI service. In Render choose
  *New → Blueprint*, select this repo and branch. It seeds the database on start (demo accounts share the password
  `Demo-Pass-123!`, so treat the deployment as a throwaway demo).
- **Connect them:** open `https://<your-pages-site>/?api=https://<your-render-service>.onrender.com`, or use the
  **Connect backend** button. Then set `CORS_ORIGINS` on Render to your Pages origin (for example `https://override0237.github.io`).
- Render's free tier sleeps when idle, so the first request can take about a minute.

## Platform commission: 5%

The platform keeps **5%** of each completed job, taken from the **artisan's** payment (the customer pays only the agreed price).
The allowed band is 3% to 7% inclusive; `computeCommission` throws outside it. Why 5%:

- Typical jobs are 3,000 to 8,000 FCFA, so the cut is 150 to 400 FCFA: artisans keep about 95%, which gives them no reason to
  take repeat customers off the platform (the main revenue risk for a matching service).
- It still pays for SMS, verification and support.
- Mobile-money cash-out costs the artisan roughly 1-2% more, so going above 5% would push their total cost over 8%.
- At 3-4% almost nothing is left after payment-processing costs.

The cut is shown at every price point: match cards (net range), the confirm step before choosing (breakdown), the artisan's inbox and
complete-job screen, the customer's tracking receipt, both completion SMS, the operator audit log and the operator earnings total.
The rate is the single constant `COMMISSION_RATE` in `src/config.ts`.

## Artisan accounts

New artisans choose a username (unique, 3-20 characters) and a password (8+ characters, typed twice). Only a salted hash is stored,
never the password. Returning artisans log in with username + password; one generic error message is shown for a wrong password and for
an unknown username. Artisan screens (status, inbox, complete job) need a login, so one artisan cannot act as another. Hashing here is
demo-grade (stretched FNV); the real backend uses Argon2id.

## Vouch Seal (one vouch per artisan, forever)

A verified artisan can vouch for another artisan **once**. The rule is enforced in layers:

1. **Rules:** `checkVouch` refuses a second vouch for the same pair (by artisan id or phone).
2. **Store action:** a refused repeat is also written to the audit log as a **security event** ("BLOCKED: X tried to vouch for Y a second time").
3. **Reducer:** re-validates, so state can never gain a duplicate even if the UI is bypassed.
4. **Sealed and chained:** every vouch gets a seal code (`VS-XXXXXXXX`) and is hash-chained to the previous vouch. The operator panel's
   *Vouch ledger* re-computes the chain; an edited, deleted, reordered or duplicated vouch shows a red "TAMPERING DETECTED" alert.
5. **Backend:** `UNIQUE(artisan_id, endorser_id)` on endorsements is the last line of defence in sync mode.

There is no withdraw button by design. The vouch panel shows a confirmation with a "this is final" warning, and a sealed row keeps a
Vouch button so the refusal can be demonstrated live.

## Connect flexibly (chat and bargaining)

After choosing an artisan, the customer taps **Connect flexibly** (the artisan taps **Chat** in the inbox) to talk about the job and bargain.
The **customer bargains and the artisan states the final price**: when they agree, the **artisan writes the final price with the currency at the end**, for example `OK, my final price is 9000 FCFA` (also `9 000 XAF`,
`9.000 fcfa`, `1 250 000 CFA`). The amount is read from the chat (`src/domain/chat.ts`) and becomes the job price; the commission is then
computed from it and shown in the chat, in the inbox and in the operator audit log; the customer is told the final price by SMS.

- Only the **artisan** can fix the price. An amount typed by the customer is only an offer in the conversation and never changes the price.
- A number without the currency fixes nothing and the artisan is reminded to add it. Amounts must be 500 to 5,000,000 FCFA.
- The artisan's **YES** accepts the job at the price he stated; after it the price is locked. The customer's consent is **paying** (or withdrawing during the cooling-off period). Backend: the artisan's chat amount becomes `proposed_price` (`proposed_by = ARTISAN`) and `accept` agrees it.
- Phone numbers (9+ digits or +CC...) are hidden as `[number hidden]` so the deal stays on the platform.
- The chat closes when the job is declined, expires, or completed, and **as soon as the customer's payment succeeds** (the app then holds the money): the Connect flexibly / Chat buttons disappear for both sides, no message can be sent (the backend answers 409), and the history stays readable. A pending or failed payment does not close it.
- Backend: `POST/GET /jobs/{id}/messages` (branch `feature/backend-chat`, rules identical to the front end). In sync mode every message is mirrored and the
  backend reads the amount itself into `proposed_price`.

Known difference: the backend charges the artisan's commission with a **300 FCFA minimum** (and rounds down), paid when the artisan
confirms the terms, with escrow and a 24h cooling-off. The offline demo takes a plain 5% at completion (no minimum), so shown amounts can differ
from the backend's for prices under 6,000 FCFA in sync mode.

## Secure payments (sandbox) in the demo

SANDBOX: no real money moves. The offline demo simulates the payments module described in `../PAYMENTS.md` (the real implementation is in the FastAPI backend):

- **Customer Payments tab** (from Job tracking): agreed price card -> method (MTN MoMo / Orange Money) + phone on a numeric keypad -> waiting screen (polls every 3 s, up to 3 min) -> result -> receipt. The amount is always taken from the job, never typed; the receipt and the card show **no commission breakdown** for the customer.
- **When the payment succeeds:** the full price goes to the `collection` account, the commission is booked as `platform_revenue` at once, and the artisan's share waits in `artisan_pending` as a PENDING payout. The job code (stored hashed) and the artisan's phone are unlocked only now.
- **Correct job code:** the payout is released and PAID (`artisan_pending` -> `artisan_paid`). A wrong code changes nothing. An operator-held payout is not paid by completion.
- **Operator panel:** payments list (phones masked), ledger balances with a balanced/unbalanced indicator, payouts with Hold / Release (reason of 5+ characters required, written to the audit log), and a reconciliation table with a red **Mismatch** warning, plus completed jobs that have no payment (possible off-platform payment).
- **Not in the offline demo:** signed webhooks, idempotency keys and per-phone rate limits live in the backend. In sync mode the demo starts the payment with an `Idempotency-Key` and approves the simulated prompt.
- **Bundle check:** the built `acbridge.html` contains no provider keys or webhook secret. It does contain the demo operator PIN `1234` because the offline demo gates its operator screen on the client; the backend operator endpoints require an administrator login instead.

## Offers expire if the artisan does not accept in time

A job offer that the artisan has not answered is **nullified** after a window that depends on the request's urgency:

| Urgency | The artisan must accept within |
|---|---|
| Today (urgent) | 1 hour |
| This week | 1 day |
| Not urgent | 5 days |

- The artisan's inbox shows the deadline and a countdown. After it passes the offer shows **Offer expired**, YES/NO disappear, a late YES lapses instead of accepting, the chat and Payments close, the customer is told by SMS to choose another artisan and the artisan is told the offer was lost. An `expiry` entry is written to the operator audit log.
- Only an unanswered offer expires: once the artisan has said YES (or NO) the offer is answered and never expires later.
- Rule: `src/domain/offers.ts` (checked on load, every 30 seconds, and again at the moment of answering). Backend: `urgency` on service requests, `OFFER_TTL_HOURS_TODAY/_THIS_WEEK/_NOT_URGENT`, `offer_expires_at` on jobs, lazy expiry when a job is read or accepted (`JOB_OFFER_EXPIRED` event, job `CANCELLED`) and `POST /admin/expire-offers` to sweep all stale offers.

## Database folder

See [database/README.md](database/README.md): a browsable SQLite copy of the backend database (accounts, requests, payments, ledger...), `database/browse.html` to read it by double-click, and an **Export data** button in the Operator screen that turns what you create in the demo into its own database.
