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
| **Backend sync** | `VITE_API_MODE=api npm run dev` | Same UI, and every step is mirrored to the FastAPI backend in `../backend` through a Vite proxy (`/api` → `http://localhost:8000`, override with `VITE_BACKEND_URL`). No backend CORS change is needed. |

**Easiest way to connect:** start the backend, open `acbridge.html`, click **Connect backend** in the footer (default `http://localhost:8000`). Or open `acbridge.html?api=http://localhost:8000`; use `?api=off` to go back offline. The backend now allows browser calls (CORS, `CORS_ORIGINS` env var, default `*`).

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
6. **Fee (500 FCFA)** is display-only; the backend has no payments.

## 60-second walkthrough

1. Home → **I am an artisan** → enter name, phone (`670123456`), description → type your trade (e.g. Plumber) → **Register**. The SMS panel shows two vouch requests.
2. Tap **Simulate vouch 1**: still "1 of 2". Tap **Simulate vouch 2**: **Verified**, SMS sent.
3. Back to Home → **I need a service** → type the artisan you need (e.g. Plumber), pick urgency → **Find artisans**. The list appears instantly and only shows verified artisans of that trade; your new artisan is in it.
4. Tap **Choose** on any artisan (e.g. yours) → **Confirm** (the 500 FCFA completion fee is shown first).
5. Job tracking → **Open as artisan** → **YES**. The **job code** appears only in the SMS panel, sent to the customer (`+237690000030`).
6. Artisan → **Finish job** → type a wrong code (error, nothing happens) → type the right code → completed.
7. Tracking → **Rate job** → pick stars → **Send rating** → "Thank you. Your rating is recorded." Rating again is rejected.
8. Open the artisan's **profile** (trust score and rating) and the **Operator** panel (PIN `1234`) for the audit log.

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
  screens/             one file per screen               config.ts      fee, PIN, limits, API mode
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
