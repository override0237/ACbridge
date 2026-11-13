# State, persistence and the API bridge

The whole demo runs on one store: a React `useReducer` holding a single `State` object (artisans, vouches, requests, jobs, chats, payments, payouts, ledger, ratings, SMS, audit log, and UI position). The state is saved in the browser after every change so a refresh keeps everything. Optionally, when a backend address is configured ("API mode"), every important step is also replayed against the real FastAPI backend, while the screen keeps working from local state.

This section also covers how the demo is built and run (Vite dev server and proxy, the one-file `acbridge.html` build) and how the new typed client in `packages/core` (used by the production rebuild) differs from the demo's small client.

## Files

| File | Role |
|---|---|
| `apps/web/src/store/reducer.ts` | `State`, `UiState`, `Screen`, the `Action` union, `initialState()`, the pure `reducer`, and `expireStale`. |
| `apps/web/src/store/index.tsx` | `StoreProvider`, `useStore`, the `actions` object (validation, id/time generation, dispatch, mirroring), the 30 s expiry sweep, the sandbox payment settle timer, `waitForRemote`. |
| `apps/web/src/store/persistence.ts` | `STORAGE_KEY`, `loadState`, `saveState`, `clearState`. |
| `apps/web/src/api/client.ts` | The demo's small backend client: `call`, `login`, `rememberPassword`, `ApiError`, the `api` object. |
| `apps/web/src/api/bridge.ts` | One function per mirrored backend step (register, vouch, verify, request, job, pay, complete, review). |
| `apps/web/src/config.ts` | Constants and `readApiBase()` / `API_BASE` / `API_MODE` / `DEMO_PASSWORD`. |
| `apps/web/vite.config.ts` | Dev server proxy `/api` to the backend; vitest settings. |
| `apps/web/scripts/inline.mjs` | Turns the Vite build into the single file `apps/web/acbridge.html`. |
| `apps/web/package.json` | Scripts: `dev`, `build`, `preview`, `test`, `db:browse`, `db:from-browser`. |
| `packages/core/src/api/client.ts` | `createApiClient`: typed, zod-validated client for the production apps. |
| `packages/core/src/schemas/index.ts` | zod schemas for backend payloads and the inferred types. |
| `apps/web/src/App.tsx` | Mounts `StoreProvider`; the footer "Connect backend" button calls `toggleBackend()`. |

## How it works

### One user action, end to end

1. A screen calls a method of `actions` from `useStore()`, for example `actions.choose(artisanId)`.
2. The method reads the latest state from `ref.current` (a ref updated on every render), validates input using the domain rules (`checkVouch`, `checkPayStart`, `checkChatMessage`, ...), and returns a typed result when the screen needs feedback (`{ ok: false, error: Key }`).
3. If valid, it creates the impure values: ids with `uid(prefix)` (`Math.random` + `Date.now`), a timestamp with `now()` (`new Date().toISOString()`), a job code with `generateJobCode()`. It then calls `dispatch({ type, ..., at, ids })`.
4. The reducer (pure) computes the next `State`. It re-validates (the UI is not trusted) and returns the same state unchanged when a rule fails.
5. `useEffect(() => saveState(state), [state])` writes the new state to `localStorage`.
6. In API mode only, the method then runs `void mirror(async () => { ... bridge.xxx(...) })`. `mirror` returns immediately when `API_MODE !== 'api'`; otherwise it awaits the step and on any exception sets `notice` (shown as a red `role="alert"` bar in `App.tsx`) with the text `"<mode.api label>: <message>"`. The local flow is never rolled back.
7. Backend ids come back later: `registerArtisan` returns `artisan_id`, stored via `patchArtisan { remoteId }`; `createRequest` returns `requestId` and a `links` map; `chooseArtisan` returns a job id stored via `patchJob { remoteId }`.

### Why reducers are pure

`reducer(state, action)` never calls `Date.now()`, `Math.random()`, storage or network. Everything non-deterministic (ids, timestamps, the job code, the settle delay) is created in `store/index.tsx` and passed inside the action (`at`, `ids`, `id`, `code`, `stamp`). This makes the reducer testable with fixed inputs (see `journey.test.ts`, `offers.test.ts`), safe under React `StrictMode` (which may call a reducer twice), and replayable. Example: `paySettle` receives `code: generateJobCode()` and the reducer only stores `hashCode(a.code)`.

### Startup

1. `useReducer(reducer, undefined, loadState)`: initial state is the saved one or `initialState()`.
2. The expiry effect runs `sweep()` once and then every 30 000 ms (see below).
3. A second effect finds payments still `pending` after a refresh and calls `scheduleSettle` with the remaining sandbox delay `Math.max(0, SANDBOX_APPROVE_AFTER_MS - (Date.now() - createdAt))`, so a payment never stays stuck after a reload.

### Expiry sweep

`sweep()` checks `s.jobs.some(j => isOfferExpired(j, request, Date.now()))` and, if any offer is overdue, dispatches `{ type: 'expire', at: now(), stamp: uid('exp') }`. `expireStale` then marks those jobs `EXPIRED`, appends system chat lines, two SMS and an audit entry per job. Deadlines: 1 hour (`today`), 24 hours (`week`), 5 days (`later`). `answer()` also checks before dispatching and returns `{ expired: true }`, and the `answer` reducer case calls `expireStale` first.

### Sandbox payment

`startPayment` validates with `checkPayStart`, dispatches `payStart` (status `pending`, reference `SIM-XXXXXXXX`) and calls `scheduleSettle(id, ok, SANDBOX_APPROVE_AFTER_MS)` with `ok = false` only for the phone `+237600000000` (`SANDBOX_DECLINED_PHONE`). `scheduleSettle` uses `setTimeout`, dispatches `paySettle` with a fresh job code, and in API mode mirrors `bridge.payJob`.

### Reset and language

`reset()` calls `clearState()` then dispatches `{ type: 'reset', lang }`, producing `{ ...initialState(), lang }`.

## All reducer actions

| Action (`type`) | Key fields | Effect on state |
|---|---|---|
| `setLang` | `lang` | Sets `state.lang`. |
| `nav` | `screen`, `patch?` | Merges `patch` into `ui` and sets `ui.screen`. |
| `register` | `artisan`, `at`, `ids[4]` | Appends the artisan; 2 `sms.vouchRequest` (to seed-1, seed-2) and `sms.welcome`; audit `verification/registered`; logs the artisan in (`ui.actingArtisanId`) and goes to `artisanStatus`. |
| `login` | `artisanId`, `next` | Sets `ui.actingArtisanId`, `ui.screen = next`, clears `loginNext`. |
| `logout` | none | Clears `actingArtisanId` and `loginNext`, goes to `home`. |
| `vouchBlocked` | `artisanId`, `voucherId`, `at`, `id` | Audit entry `security/vouch_blocked` for a repeated vouch attempt; nothing else. |
| `vouch` | `artisanId`, `voucherId`, `workedTogether`, `vouchId`, `at`, `ids[5]` | Re-checks `checkVouch`; appends a vouch sealed with `sealVouch(lastHash(...))`; SMS `vouchRecorded` and `vouchSealed`; audit `vouch`; if it makes the artisan verified, SMS `verified` and audit `verified`. |
| `request` | `request` | Appends the request, sets `ui.requestId`, goes to `matches`. |
| `choose` | `jobId`, `requestId`, `artisanId`, `price`, `at`, `ids[1]` | Creates a `REQUESTED` job (`priceSource: 'estimate'`); SMS `jobRequest` to the artisan; goes to `tracking`. |
| `expire` | `at`, `stamp` | Runs `expireStale`: overdue `REQUESTED` jobs become `EXPIRED`, chat line, 2 SMS, audit `expiry`. |
| `answer` | `jobId`, `accept`, `at`, `ids[3]` | Runs `expireStale` first; only for a `REQUESTED` job: NO gives `DECLINED`, chat line, SMS `jobDeclined`; YES gives `ACCEPTED` (+`acceptedAt`), chat line, SMS `accepted`, audit `job_accepted`. |
| `payStart` | `id`, `jobId`, `method`, `phone`, `ref`, `at`, `ids[1]` | Re-checks `checkPayStart`; appends a `pending` payment whose amount is `job.price`; audit `payment/started`. |
| `paySettle` | `id`, `ok`, `code`, `at`, `ids[4]` | Ignores a non-pending payment. Failure: payment `failed`, SMS `payFailed`, audit. Success: payment `succeeded`, chat closed (`chat.sysClosed`), a `PENDING` payout, ledger lines via `postTx` (idempotent by key `payment-succeeded:<id>`), `job.codeHash` + commission fields, SMS `jobCode` and `paymentReceived`, audit. |
| `payoutHold` | `payoutId`, `reason`, `at`, `id` | Re-checks `checkHold`; payout `HELD` with note; audit `payout/held`. |
| `payoutRelease` | `payoutId`, `reason`, `at`, `ids[2]` | Re-checks `checkRelease`; payout `PAID`; ledger `payout-paid:<id>`; SMS `payoutPaid`; audit. |
| `chat` | `id`, `sysId`, `jobId`, `from`, `text`, `at`, `ids[2]` | Re-checks `checkChatMessage`; stores the message with `maskContacts`; if the artisan's amount applies: system line `chat.sysPrice`, `job.price`/`priceSource: 'chat'`, SMS `priceProposed`, audit `price`. |
| `complete` | `jobId`, `entered`, `at`, `ids[4]` | Re-checks `checkCompletion`; job `COMPLETED`, `codeUsed`; pays a `PENDING` payout (ledger + SMS `payoutPaid` + audit); SMS `jobCompleted`; audit `job_completed`. |
| `rate` | `ratingId`, `jobId`, `score`, `comment`, `at`, `ids[3]` | Re-checks `checkRating`; appends the rating; SMS `rated`; audits `rating` and `trust`. |
| `operator` | `artisanId`, `approve`, `at`, `ids[2]` | Sets `operatorApproved` (and `rejected: false`) or `rejected: true`; SMS `verified` or `rejected`; audit `verification`. |
| `patchArtisan` | `id`, `patch` | Shallow-merges into one artisan (used for `remoteId`). |
| `patchRequest` | `id`, `patch` | Shallow-merges into one request (used for `remoteId`). |
| `patchJob` | `id`, `patch` | Shallow-merges into one job (used for `remoteId`). |
| `reset` | `lang` | Returns `initialState()` with the given language. |

## File by file

### `apps/web/src/store/reducer.ts`

- `Screen`: union of 15 screen names. `UiState`: `screen`, `actingArtisanId`, `requestId`, `jobId`, `profileId`, `back`, optional `loginNext`, optional `chatAs`.
- `State` (`v: 1`): `lang`, `artisans`, `vouches`, `requests`, `jobs`, `chats`, `payments`, `payouts`, `ledger`, `ratings`, `sms`, `audit`, `ui`.
- `initialState()`: `lang: 'fr'`, `artisans` = copy of `SEED_ARTISANS`, empty collections, `ui.screen = 'home'`.
- Helpers `sms(...)`, `audit(...)`, `byId(list, id)`.
- `expireStale(s, at, stamp)` is exported and used by `expire` and `answer`. Returns the same `s` object when nothing is overdue.
- Exports `URGENCIES` (`['today','week','later']`) and `DEMO_CUSTOMER`.
- Reducers return the unchanged `s` for unknown ids or failed re-validation, so a replayed or forged action is a no-op.

### `apps/web/src/store/index.tsx`

- `StoreProvider({ children })`: holds `state`, `notice`, and `ref`. Provides `{ state, actions, t, notice, clearNotice }` via context. `useStore()` throws if used outside the provider.
- `Actions` interface (what each method validates and returns):

| Method | Validates before dispatch | Returns |
|---|---|---|
| `setLang(l)` | none | void |
| `go(screen, patch?)` | none | void |
| `registerArtisan(v)` | name length >= 2 (`signup.errName`); `resolveTrade` (`signup.errTrade`); `checkNewCredentials` (`signup.errUsername`, `signup.errUsernameTaken`, `signup.errPassword`, `signup.errConfirm`); `normalizePhone` (`signup.errPhone`); phone not already used (`signup.errTaken`) | `{ ok: true, id }` or `{ ok: false, error: Key }`. Also calls `rememberPassword(phone, password)` and mirrors `bridge.registerArtisan`. |
| `loginArtisan(username, password, next?)` | `verifyLogin` | `{ ok: true }` or `{ ok: false, error: 'login.errWrong' }` (same message for unknown user and wrong password). Calls `rememberPassword`. |
| `logout()` | none | void |
| `vouch(artisanId, voucherId, workedTogether = true)` | both artisans exist (`status.noArtisan`); `checkVouch` reasons mapped by `VOUCH_ERRORS` (`self`, `not_verified`, `same_phone`, `duplicate`, `no_job_together`). A `duplicate` also dispatches `vouchBlocked` | `VouchResult`. Mirrors: waits for `remoteId`, `bridge.vouch`, and when the artisan has 2 or more vouches `bridge.verifyAfterVouches`. |
| `submitRequest(v)` | `resolveTrade` (`request.errTrade`) | `{ ok: true }` or error. Request uses the fixed demo customer (`SEED_CUSTOMER`) and `NEIGHBOURHOOD`. |
| `choose(artisanId)` | a `ui.requestId` exists and the artisan exists (silently returns otherwise) | void. Price is `agreedPrice(artisan)`. |
| `answer(jobId, accept)` | if the offer is already expired it dispatches `expire` instead | `{ expired: boolean }`. Mirrors only YES (`bridge.acceptJob`). |
| `sendChat(jobId, from, text)` | `checkChatMessage` (`chat.errEmpty`, `chat.errLong`, `chat.errClosed`) | `{ ok: true, price, amount }` or error. |
| `startPayment(jobId, method, phone)` | `normalizePhone`, `checkPayStart` | The `PayCheck`. Starts the settle timer. |
| `holdPayout(id, reason)` / `releasePayout(id, reason)` | `checkHold` / `checkRelease` | `PayoutCheck`. |
| `complete(jobId, entered)` | `checkCompletion` | `CompletionCheck` (`not_accepted` if job missing). Mirrors `bridge.completeJob`. |
| `rate(jobId, score, comment)` | `checkRating` | `RatingCheck`. Mirrors `bridge.review`. |
| `operator(artisanId, approve)` | none (PIN is checked in the screen) | void. Mirrors `bridge.operatorDecision`. |
| `reset()` | none | void; clears storage. |

- `mirror(step)`: no-op outside API mode; otherwise try/catch that sets `notice`.
- `scheduleSettle(paymentId, ok, delayMs)`: `setTimeout` described above.
- `waitForRemote(get)`: polls every 150 ms, up to 40 times (about 6 s), until the artisan has `remoteId`; otherwise throws `Artisan is not registered on the backend yet`. Needed because registration mirrors asynchronously while a vouch may come right after.
- `uid`, `ids(n)`, `now()` are the impure generators. `POLL_MAX_MS` is imported but only referenced with `void POLL_MAX_MS` (not used for polling in the demo).

### `apps/web/src/store/persistence.ts`

- `STORAGE_KEY = 'acbridge.demo.v2'` (bumped from v1 when artisans gained credentials and vouches gained seals; old data is simply ignored).
- `loadState()`: `localStorage.getItem` then `JSON.parse`; valid only if `parsed.v === 1` and `Array.isArray(parsed.artisans)`; result is `{ ...initialState(), ...parsed }` (so a new top-level field gets its default). Any exception returns `initialState()`.
- `saveState(state)`: `localStorage.setItem(KEY, JSON.stringify(state))` inside try/catch (storage full or blocked: the demo works in memory).
- `clearState()`: `removeItem`, try/catch.
- Nested objects are not migrated: a saved state missing a field inside e.g. `ui` is not repaired.

### `apps/web/src/api/client.ts`

- `BASE = API_BASE ?? '/api'`. Module-level `Map`s: `tokens` (phone to bearer token) and `passwords` (phone to password typed this session), memory only.
- `rememberPassword(phone, password)`: stores the password and drops any cached token for the phone, so the next `login` uses the real password. Seeded accounts have no entry and use `DEMO_PASSWORD` (`'Demo-Pass-123!'`).
- `call(method, path, token?, body?, extra headers?)`: `fetch` with JSON; parses JSON (204 gives `null`); on a non-OK status throws `ApiError(status, detail)` where `detail` is the server's string `detail` or `HTTP <status>`.
- `login(phone, password?)`: returns the cached token or `POST /auth/login`.
- `api`: `health`, `register`, `skills`, `createProfile`, `addSkill`, `endorse`, `submitCheck`, `decide`, `createRequest`, `matches`, `createJob`, `jobAction(accept|confirm-terms|start|confirm-completion)`, `pay` (sends header `Idempotency-Key`, no body), `approvePayment` (sandbox `simulate-approval`), `sendMessage`, `review`.
- Responses are cast with generics (`call<T>`); they are not validated at runtime.

### `apps/web/src/api/bridge.ts`

| Function | Backend calls | Notes |
|---|---|---|
| `registerArtisan(a)` | `POST /auth/register` (ignore failure), login, `POST /artisans` (`location` = `"Neighbourhood A, Buea"`), `POST /artisans/{id}/skills` (typical price = midpoint of `priceMin`/`priceMax`) | Returns backend `artisan_id`. Free-text trades throw (`skillFor`) because only catalogue trades exist as backend skills. |
| `vouch(artisan, voucher)` | `POST /artisans/{id}/endorsements` as the voucher | Skipped if the artisan has no `remoteId`. |
| `verifyAfterVouches(artisan)` | `POST /verifications` (SKILL) as the artisan, then verifier `+237670000002` decides `UNDER_REVIEW` then `APPROVED` ("SIMULATED") | Simulated verifier. |
| `operatorDecision(artisan, approve)` | same check + decision, `APPROVED` or `REJECTED` | Errors from `submitCheck` are swallowed. |
| `createRequest(req, artisans)` | register customer, login, `POST /service-requests`, `GET /matches/{id}` | Links local artisans to backend ids by matching names (`full_name` starts with the local name). |
| `chooseArtisan(req, artisan, price)` | `POST /jobs` as the customer | Needs both `remoteId`s; returns job id or null. |
| `sendChat(job, from, text, artisan)` | `POST /jobs/{id}/messages` with the sender's own token | The backend parses the price itself. |
| `acceptJob(job, artisan)` | `POST /jobs/{id}/accept`, then `confirm-terms` | Needs backend `COMMISSION_MODEL=customer_split` (per the code comment). |
| `payJob(job, _phone)` | `POST /jobs/{id}/pay` with `Idempotency-Key: ui-<jobId>`, then `POST /payments/{id}/simulate-approval` | No amount is sent. The `_phone` argument is unused. |
| `completeJob(job, artisan)` | artisan `start`, artisan `confirm-completion`, customer `confirm-completion` | The correct job code stands for both confirmations. |
| `review(job, score, comment)` | `POST /jobs/{id}/reviews` as the customer | |

Every function returns early when the needed `remoteId` is missing. The job code itself has no backend endpoint; it exists only in the front end.

### `apps/web/src/config.ts`

- Business constants: `COMMISSION_RATE = 0.05`, `MIN_COMMISSION_RATE = 0.03`, `MAX_COMMISSION_RATE = 0.07`, `OPERATOR_PIN = '1234'`, `NEIGHBOURHOOD`, `CURRENCY`, `VOUCHES_REQUIRED = 2`, `MAX_MATCHES = 5`.
- `readApiBase()`: reads the `?api=` URL parameter. `?api=off` removes `localStorage['acbridge.api']` and returns null. `?api=<url>` stores the URL without trailing slashes and uses it. Otherwise a stored value is used. If nothing is stored, `import.meta.env.VITE_API_MODE === 'api'` gives `'/api'` (dev proxy), else null. Storage errors fall through.
- `API_BASE` and `API_MODE` (`'api'` when `API_BASE` is set, else `'local'`) are computed once at module load, so changing mode needs a page reload; `toggleBackend()` in `App.tsx` does it by setting the `api` query parameter and navigating.

### `apps/web/vite.config.ts`

`defineConfig({ plugins: [react()], server: { proxy: { '/api': { target: process.env.VITE_BACKEND_URL ?? 'http://localhost:8000', rewrite: p => p.replace(/^\/api/, '') } } }, test: { environment: 'node', testTimeout: 30000 } })`. The browser calls same-origin `/api/...` and Vite forwards to the backend without the `/api` prefix, so no CORS configuration is needed in dev. UI test files switch to jsdom with a `// @vitest-environment jsdom` header.

### `apps/web/scripts/inline.mjs`

Run after `vite build` (`npm run build` = `tsc --noEmit && vite build && node scripts/inline.mjs`). It reads the one `.js` and one `.css` file from `dist/assets/` and writes `apps/web/acbridge.html`: a complete HTML document with the CSS in a `<style>` and the JS in `<script type="module">`, no external files. It prints the size in kB. Why: a page opened by double-click has the origin `file://`; the normal build's `<script type="module" src="/assets/...">` uses absolute paths and a module fetch that browsers block from `file://`, giving a blank page (this is also why `index.html` alone shows nothing). The inlined file needs no server. Implementation detail: the line that escapes `</script` in the JS is written `js.replace(/<\/script/gi, '<\/script')`; inside a JS string `'<\/script'` is the same text as `'</script'`, so as written it does not change anything (not verified in a browser). In API mode from `file://` the backend must allow the `null` origin (see Backend connection).

### `apps/web/package.json` (scripts)

| Script | Command | Purpose |
|---|---|---|
| `dev` | `vite` | Dev server on port 5173 with the `/api` proxy. |
| `build` | `tsc --noEmit && vite build && node scripts/inline.mjs` | Type-check, production build, single-file `acbridge.html`. |
| `preview` | `vite preview` | Serves `dist/`. |
| `test` | `vitest run` | All web tests. |
| `db:browse` | `node ... database/make-browser.mjs ...` | Builds `database/browse.html` from `database/acbridge.db` (see section 11). |
| `db:from-browser` | `node ... database/build-demo-db.mjs` | Rebuilds the demo database file. |

### `packages/core/src/api/client.ts` and `packages/core/src/schemas/index.ts`

`createApiClient({ baseUrl, getToken?, fetchImpl?, credentials?, onUnauthorized? })` returns an object of typed calls: `request` (generic), `health`, `skills`, `createRequest`, `matches`, `job`, `pay`, `payment`, `messages`, `sendMessage`, and `operator.ledger/payouts/reconciliation`. Each call passes a zod schema from `schemas/index.ts` (`SkillSchema`, `ServiceRequestSchema`, `MatchesSchema`, `JobSchema`, `PaymentSchema`, `ChatMessageSchema`, `ChatSendSchema`, `LedgerSchema`, `PayoutSchema`, `ReconciliationSchema`, plus `TokenSchema`, `ArtisanSchema`, enums for roles, urgency and statuses). Schemas use `.passthrough()` so extra backend fields are tolerated, and are strict on the fields the apps use.

How it differs from `apps/web/src/api/client.ts`:

| Aspect | Demo client (`apps/web/src/api`) | Typed client (`packages/core/src/api`) |
|---|---|---|
| Response checking | TypeScript casts only | `schema.safeParse`; failure throws `SchemaError(path, issues)` |
| Errors | `ApiError(status, message)` | `ApiError` whose message is passed through `stripPhones`, so phone numbers never reach logs |
| Auth | Per-phone bearer tokens kept in module memory; logs in as many different users (seeded accounts, shared demo password) | `getToken()` callback (mobile: secure storage) or session cookie with `credentials: 'include'` (web); one user per client |
| 401 | Not handled | `onUnauthorized()` callback |
| Platform | Uses global `fetch` and `config.ts` | `fetchImpl` injectable; no React, no platform APIs |
| Scope | Whole demo journey, including impersonating other users | A subset: requests, matches, jobs, payments, chat, operator reports |
| Payment | `pay` sends no body | `pay` also sends no body (test asserts it); amount always server-side |

Its tests are `packages/core/src/api/client.test.ts` and `schemas.test.ts` (see below). The demo does not use this client yet.

## Data and state

- Persisted: the entire `State` as JSON under `localStorage['acbridge.demo.v2']` (passwords are never stored; credentials are hashes with a salt, job codes are stored hashed).
- Persisted separately: `localStorage['acbridge.api']` (backend URL, set by `?api=`).
- Memory only: `tokens` and `passwords` Maps in `api/client.ts`, `skillIds` cache in `bridge.ts`, `notice`, running timers.
- Remote link fields: `Artisan.remoteId`, `ServiceRequest.remoteId`, `Job.remoteId` (optional; only set in API mode).

## Rules and edge cases

- The reducer re-validates everything the `actions` layer validated, so a UI bug cannot book money twice or accept an expired offer.
- `paySettle` is idempotent: it returns state unchanged unless the payment is `pending`; the ledger uses idempotency keys.
- `chat` on a closed or expired job is ignored; payments are closed on an expired offer (tests in `offers.test.ts`).
- A second vouch for the same pair is refused and logged as a security event.
- Mirror failures never undo local state; they only show a notice. Free-text trades cannot be mirrored (no backend skill).
- If `localStorage` throws (blocked), the app works for the session but forgets on reload.
- Two tabs on the same origin do not sync: each keeps its own in-memory state and overwrites the other's save.
- `loadState` accepts any JSON with `v: 1` and an `artisans` array; a hand-edited or partially corrupt state is not repaired.

## Tests

| File | Test names (abridged) | What they check |
|---|---|---|
| `apps/web/src/__tests__/journey.test.ts` | "runs register, 2 vouches, request, choose, YES, PAY, wrong code, right code, payout, rate once" | The whole journey on the pure reducer with fixed ids and times. |
| `apps/web/src/__tests__/offers.test.ts` | "is 1 hour (urgent), 1 day (this week) and 5 days (not urgent)", "expires an urgent offer after an hour...", "a late YES does not accept...", "an on-time YES still works...", "a not-urgent offer survives 4 days and lapses after 5", "chat and payments are closed on an expired offer" | Deadlines and `expireStale`. |
| `apps/web/src/__tests__/payments.test.ts` | "only an accepted job with a price can be paid, once...", "the amount always comes from the job...", "a declined payment books nothing and can be retried" | Payment rules used by `startPayment` and `paySettle`. |
| `apps/web/src/__tests__/ui-flows.test.tsx` | "survives a refresh (localStorage) and Reset demo clears it" and the full journey (reads `STORAGE_KEY`) | Persistence and reset through the rendered app. |
| `apps/web/src/__tests__/ui-expiry.test.tsx` | "an urgent offer lapses after one hour...", "a not-urgent offer is still open after two days" | The 30 s sweep and expiry with fake timers in the rendered app. |
| `apps/web/src/__tests__/bridge.test.ts` | "runs the whole journey and uses the right accounts" | Stubs `fetch`; every mirrored call must be an existing backend route; endorsements by the two seed artisans; completion confirmed by both parties; pay has no body and `Idempotency-Key: ui-j`; chat uses the sender's token; review body `{ rating: 5, comment: 'Good' }`; profile location `"Neighbourhood A, Buea"`. |
| `packages/core/src/api/client.test.ts` | "validates responses, sends the bearer token and never sends an amount when paying", "rejects a response that is not the expected shape", "turns HTTP errors into ApiError, scrubs phone numbers from the message and signals a 401", "web mode sends the session cookie instead of a token" | The typed client. |
| `packages/core/src/schemas/schemas.test.ts` | "token", "skill, service request and matches (price ranges stay integers)", "job, payment, chat, payout, ledger and reconciliation" | Schemas accept backend payloads and reject bad ones. |

## Backend connection

Only in API mode. The mapping (route, who calls it) is in the `bridge.ts` table above. The backend must be running (`uvicorn app.main:app`), initialised and seeded (`python -m app.init_db && python -m app.seed`) so Grace, Paul, Mary, the verifier `+237670000002` and the skills exist. With the dev proxy no CORS setting is needed; with `acbridge.html` opened from a file or any other origin the backend needs `CORS_ORIGINS` to allow it (`*` or `null` for local demos). Rules mirrored: endorsements and verification (backend needs 2 endorsements), job accept and confirm-terms, payment with `Idempotency-Key` and server-side amount, completion needing both parties' confirmation, one review per job, chat price parsing.

## Known limits and what changes in the production rebuild

- The browser state is the system of record in the demo and the backend is only a mirror; production reverses this: the server owns all state and the client is a cache.
- The demo client logs in as every party (customer, artisan, verifier) from one browser using a shared demo password and in-memory tokens. This is impossible and unsafe in production, where each user has one session (httpOnly cookie on web, secure storage on mobile) and the typed `createApiClient` is used.
- Responses are not validated in the demo client; production validates with the zod schemas.
- Ids, timestamps and the job code are generated in the browser. Production generates them on the server; the job code needs a backend endpoint (`code_hash` on jobs and a complete-with-code route), which does not exist yet.
- The sandbox payment is a 5 second `setTimeout`; production uses a real mobile-money provider with a signed webhook.
- Mirroring is best-effort and unordered beyond `waitForRemote` (polling for up to about 6 s); there is no retry queue and no conflict handling.
- Persistence is a single `localStorage` blob per browser, not shared between tabs or devices, with no versioned migrations beyond `v` and the key name.
- Remote link-up of local artisans relies on name matching, which would fail for duplicate names.
