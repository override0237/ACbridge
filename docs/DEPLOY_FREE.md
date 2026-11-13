# Free hosting for ACbridge (Vercel frontend + free API + free database)

Goal: the website at **https://acbridge.vercel.app**. Vercel's free tier hosts the **frontend**. The **API** and
**database** run on other free services, because the API needs things a serverless host does not give it.

| Part | Where (free tier) | Why |
|---|---|---|
| Frontend (your site) | **Vercel**, project named `acbridge` | Gives `acbridge.vercel.app` if the name is still free |
| API (FastAPI) | **Render** web service (Docker) | A real, always-the-same process |
| Database | **Neon** (free PostgreSQL) | Persistent; Render's own free database expires |

**Why the API is not on Vercel.** Vercel runs backends as short-lived serverless functions. ACbridge needs a disk that
survives (uploaded evidence and hardship documents), memory shared between requests (rate limits, the simulated e-mail
outbox), and predictable startup. On serverless those silently break: uploads fail or vanish, brute-force limits reset on
every call, and the demo "outbox" empties. Frontend on Vercel, API elsewhere is the reliable split.

Free-tier limits and names change. Check each provider's current free plan before relying on it.

## 1. Database (Neon)
1. Create a free project at neon.tech. Copy the **connection string** (`postgresql://…?sslmode=require`).
   The app converts it to the right driver automatically.

## 2. API (Render)
1. Push this repo to GitHub (done). In Render: **New → Blueprint**, pick the repo; it reads `render.yaml`
   (or create a Web Service by hand: runtime Docker, root directory `backend`, health check `/health`).
2. Set the variables Render asks for:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon connection string |
| `SEED_PASSWORD` | a **private** password for the seeded admin/verifier/demo users (the app refuses to seed without one) |
| `CORS_ORIGINS` | `https://acbridge.vercel.app` (add other Vercel URLs, comma-separated, if you use preview deployments) |
| `PUBLIC_API_URL` | your Render URL, e.g. `https://acbridge-api.onrender.com` (trade-group e-mail links point here) |
| `JWT_SECRET` | generated for you by `render.yaml` (or run `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |

3. Deploy. Check `https://<your-render-url>/health` returns `{"status":"ok"}` and `/docs` opens.
   First request after idle can take ~30-60 s on a free plan (the service sleeps).

Seed accounts (password = your `SEED_PASSWORD`): admin `+237670000001`, verifier `+237670000002`.
After the first deploy set `SEED_DEMO_DATA` to `false` so it does not try to seed again (it is safe if it does: it skips).

## 3. Frontend (Vercel → acbridge.vercel.app)
1. At vercel.com **Add New → Project**, import your frontend repo/folder. **Project Name: `acbridge`**
   (the URL is `<project-name>.vercel.app`; if "acbridge" is taken you must pick another name, or add your own domain later).
2. Add the environment variable your framework reads, pointing at the API:
   Vite `VITE_API_URL`, Create React App `REACT_APP_API_URL`, Next.js `NEXT_PUBLIC_API_URL`
   = `https://acbridge-api.onrender.com` (your Render URL, no trailing slash).
3. For a single-page app add `vercel.json` in the frontend folder so page refreshes do not 404:
   ```json
   { "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
   ```
4. Deploy. Open https://acbridge.vercel.app and log in.

## 4. Honest limits of this free demo
* **Everything money- and verification-related is SIMULATED**, so the site is a demo. Do not collect real payments or
  present verification as real. The API says so in its responses; keep that wording visible in the UI.
* **E-mail is simulated** (`EMAIL_MODE=console`): trade groups do not receive real messages. For real e-mail set
  `EMAIL_MODE=smtp` and `SMTP_*` (use a provider with a free tier) and test it first.
* **Uploads are lost** when a free Render instance restarts (no persistent disk). Fine for a demo; use object storage later.
* **Do not put real people's data** (phone numbers, ID documents, medical records) in a public demo.
* The first visit after the API slept is slow. Open `/health` once before a live presentation.
* The Dockerfile has not been build-tested in the environment used to write it (no Docker daemon there). If the Render
  build fails, send the log. The same start command (`backend/start.sh`) was run directly and works.
