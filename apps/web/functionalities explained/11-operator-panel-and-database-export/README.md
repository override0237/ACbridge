# Operator panel and database export

The Operator screen is the back office of the demo. After typing a PIN the operator can approve or reject artisans waiting for verification, see trust scores, platform earnings and the vouch-ledger integrity check, read the audit log, review payments, ledger balances and payouts (Hold / Release with a required reason), run the payments reconciliation (including a button that fakes a mismatch), reset the whole demo, and download all stored data as `acbridge-demo-data.json`. A separate Node script turns that file into a SQLite database and a browsable HTML page.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/Operator.tsx` | The screen: PIN gate, pending verifications, earnings, vouch ledger card, trust scores, audit log, reset and export buttons. |
| `apps/web/src/components/OperatorPayments.tsx` | Payments panel embedded in the Operator screen: payments table, ledger balances, payouts with Hold/Release, reconciliation, unpaid completed jobs. |
| `apps/web/src/domain/export.ts` | `exportSnapshot(state)` builds the flat-table snapshot; `downloadSnapshot(state)` downloads it as `acbridge-demo-data.json`. |
| `apps/web/src/store/reducer.ts` | `operator`, `payoutHold`, `payoutRelease` actions and every audit entry the log shows. |
| `apps/web/src/store/index.tsx` | `operator`, `holdPayout`, `releasePayout`, `reset` actions (and API mirroring for `operator`). |
| `apps/web/src/store/persistence.ts` | `clearState` used by Reset. Storage key `acbridge.demo.v2`. |
| `apps/web/src/config.ts` | `OPERATOR_PIN = '1234'` (demo PIN), `VOUCHES_REQUIRED = 2`. |
| `apps/web/src/data/seed.ts` | `SEED_OPERATOR = { name: 'Operator', pin: OPERATOR_PIN }`. Also the nine seeded artisans (one pending candidate, Samuel). |
| `apps/web/src/i18n/format.ts` | `renderParams` converts stored audit parameters (trade, urgency, method, amounts) to display text; `money`. |
| `apps/web/src/domain/ledger.ts` | `balances`, `unbalancedTransactions`, `reconcile`, `maskPhone`, `checkHold`, `checkRelease` used by the panel. |
| `apps/web/src/domain/security.ts` | `verifyLedger(vouches)` for the vouch ledger integrity card. |
| `apps/web/database/README.md` | User guide for the `database/` folder. |
| `apps/web/database/build-demo-db.mjs` | Node script: snapshot JSON to `demo-from-browser.db`, views, CSVs and an HTML browser. |
| `apps/web/database/make-browser.mjs` | Node script: any SQLite file to one self-contained HTML page. |
| `backend/scripts/build_database.py` | Builds the separate `acbridge.db` (backend schema, demo stories played through the real API). Not the browser export. |
| `apps/web/package.json` | Scripts `db:browse` and `db:from-browser`. |

## How it works

### PIN gate
1. `Operator()` starts with local state `unlocked = false`, `pin = ''`, `wrong = false`, `confirmReset = false`.
2. Locked view: a form with a password-type numeric input (`operator.pin`, `maxLength` 8, non-digits stripped) and an unlock button (`operator.unlock`).
3. On submit: `pin === SEED_OPERATOR.pin` sets `unlocked = true`; otherwise `wrong = true`, the field is cleared and the alert `operator.wrongPin` is shown.
4. The "Lock" button (`operator.lock`) sets `unlocked = false`. Leaving the screen also loses the unlock because it is component state, not stored.

### Unlocked view, section by section
1. **Pending verifications.** `pending = artisans.filter(a => !a.rejected && !isVerified(a, vouches, artisans))`. Each row shows name, trade, phone, a badge `operator.vouchCount` with `min(countValidVouches, VOUCHES_REQUIRED)` of `VOUCHES_REQUIRED`, and two buttons: Approve and Reject (both call `actions.operator(id, approve)`). Empty list: `operator.pendingNone`.
2. **Reducer `operator`.** Approve sets `operatorApproved: true, rejected: false`; reject sets `rejected: true`. It adds SMS `sms.verified` (approve) or `sms.rejected` (reject) to the artisan and an audit entry `verification` with `event: 'approved' | 'rejected'`. In API mode `bridge.operatorDecision` mirrors it (see Backend connection).
3. **Earnings.** `earnings = balances(state.ledger).platform_revenue`, shown with `operator.earningsLine`: "{amount} FCFA from {n} completed jobs", where `n` is the number of `COMPLETED` jobs. Note: the amount is booked at payment time, the count is of completed jobs, so the two can differ for a paid but unfinished job.
4. **Vouch ledger card** (`ledger.title`). `verifyLedger(state.vouches)` recomputes the hash chain. OK shows the badge `ledger.intact`; failure shows the alert `ledger.broken` with `index + 1`. Then the list of vouches "voucher to artisan" with the seal code, or `ledger.empty`. This is the vouch chain, not the money ledger.
5. **`<OperatorPayments />`** (below).
6. **Trust scores.** For every verified artisan: `formatScore(trustFor(a, vouches, ratings, artisans))`.
7. **Audit log.** A table of time and event for every entry of `state.audit` in insertion order (not reversed), see the rendering table below.
8. **Reset demo.** First click sets `confirmReset`; a confirm group shows `operator.resetAsk` with Yes (`operator.resetYes`) and Cancel. Yes calls `actions.reset()` then `setUnlocked(false)`. `reset()` calls `clearState()` (removes `acbridge.demo.v2`) and dispatches `reset` with the current language, giving `initialState()` (seed artisans, nothing else).
9. **Export data.** Button `operator.export` calls `downloadSnapshot(state)`; the hint `operator.exportHint` shows the node command.

### Audit rendering (`describe` in `Operator.tsx`)
The i18n key is chosen from the entry kind and parameters, then `t(key, renderParams(params, t, lang))`:

| `AuditEntry.kind` | Key used | Created by (reducer action) |
|---|---|---|
| `verification` | `audit.<params.event>`: `audit.registered`, `audit.vouch`, `audit.verified`, `audit.approved`, `audit.rejected` | `register`, `vouch`, `operator` |
| `security` | `audit.<params.event>`: `audit.vouch_blocked` | `vouchBlocked` (a repeated vouch attempt) |
| `expiry` | `audit.job_expired` | `expireStale` |
| `payment` | `audit.pay_<event>`: `audit.pay_started`, `audit.pay_succeeded`, `audit.pay_failed` | `payStart`, `paySettle` |
| `payout` | `audit.payout_<event>`: `audit.payout_paid`, `audit.payout_held`, `audit.payout_released` | `complete` (paid), `payoutHold`, `payoutRelease` |
| any other | `audit.<kind>`: `audit.job_accepted`, `audit.job_completed`, `audit.price`, `audit.rating`, `audit.trust` | `answer`, `complete`, `chat`, `rate` |

`audit.transaction` exists in the translations and `'transaction'` is in the `AuditKind` type, but no reducer action creates it now.

`renderParams` (in `i18n/format.ts`) converts: `urgency` to `urgency.<value>` text; `trade` to the translated trade label in lower case; `method` to `pay.<method>` (MTN / Orange); and any numeric `price`, `commission`, `payout`, `amount` through `money()` (thousands separators for the language). Other params (names, rate, seal, reason, score, trust) are passed through unchanged. Because the key is stored with params and not as text, switching language re-renders the whole log (the UI journey test checks "Journal d'audit" becomes "Audit log").

### Payments panel (`OperatorPayments`)
Local state: `reasons` (text per payout id), `errors` (message key per payout id), `override` (number or null).

1. **Payments table.** All `state.payments`: status badge (`pay.status.<status>`), amount, reference with the phone masked by `maskPhone` (`+237 6******56`), creation time. Empty: `opay.none`.
2. **Ledger balances.** `balances(state.ledger)` for all five accounts, labels `acct.collection`, `acct.platform_revenue`, `acct.artisan_pending`, `acct.artisan_paid`, `acct.refund_payable`, in a `<dl data-testid="ledger">`. A status line shows `opay.balanced` when `unbalancedTransactions(ledger)` is empty, otherwise `opay.unbalanced` in red.
3. **Payouts.** One block per `state.payouts`: artisan name, amount, status badge (`payout.PENDING|HELD|PAID|FAILED`, with tones warn/bad/good/info) and the `note` if any. For `PENDING` or `HELD` payouts there is a reason input (`opay.reason`, "Reason (required)") and two buttons: Hold (`opay.hold`, disabled when already `HELD`) and Release (`opay.release`). `act(kind, payoutId)` calls `actions.holdPayout` or `actions.releasePayout` with the typed reason; on failure the error key is shown in an alert under the buttons, on success the reason field is cleared. Error mapping: `bad_reason` to `opay.errReason`; `not_completed` to `opay.errNotCompleted`; `not_holdable`, `not_releasable`, `no_payout` to `opay.errState`.
4. **Reconciliation.** `reconcile(ledger, payments, payouts, jobs, override)`. If `mismatch` is true: alert `opay.mismatch` ("Mismatch") with a warning sign; otherwise the badge `opay.reconOk`. A table compares "Provider says" with "Ledger says" and the "Difference" for Collected (`succeeded` payments vs `collection` balance) and Paid out (`PAID` payouts vs `artisan_paid` balance). Non-zero differences get a warning sign and the `diff-bad` class.
5. **Simulate mismatch.** The button sets `override = rec.ledger.collection + 500`, which makes the "provider" claim 500 FCFA more than the ledger, so `differences.collected = 500` and the Mismatch warning appears. "Clear" (`opay.clearSim`, disabled when no override) sets `override = null`. The override lives only in component state; it is never written to the ledger.
6. **Completed jobs without payment.** `rec.unpaidCompleted` lists, per artisan, jobs that are `COMPLETED` with no succeeded payment (`opay.unpaidWarn`, possible payment outside the app), or `opay.unpaidNone`.

### Reducer payout actions
- `payoutHold`: re-checks `checkHold`; sets payout `HELD` and `note = reason.trim()`; audit `payout/held` with `{ artisan, payout, reason }`. No ledger entry.
- `payoutRelease`: re-checks `checkRelease` (needs completed job); sets `PAID`, `paidAt`, `note`; posts `payout-paid:<payoutId>` to the ledger; SMS `sms.payoutPaid` to the artisan; audit `payout/released`.
- The artisan completing the job (`complete`) pays only `PENDING` payouts; a held one stays held until released (UI test).

### Export
1. `exportSnapshot(state, now = new Date())` returns `{ format: 'acbridge-demo-export', version: 1, exportedAt, tables }`.
2. `tables` contains: `artisans`, `customers`, `vouches`, `requests`, `jobs`, `chats`, `payments`, `payouts`, `ledger`, `ratings`, `sms`, `audit`.
3. `downloadSnapshot(state)` serialises with `JSON.stringify(..., null, 2)`, creates a `Blob` of type `application/json`, an object URL and a temporary `<a download="acbridge-demo-data.json">`, clicks it, removes it, and revokes the URL after 1 second.

### Turning the file into a database (`build-demo-db.mjs`)
Run `node --no-warnings database/build-demo-db.mjs <acbridge-demo-data.json> [output-folder]` (or `pnpm db:from-browser`). Requires Node 22.5+ for built-in `node:sqlite`.
1. Exits with code 1 and a usage message if no existing file is given; exits 1 with "This is not an ACbridge demo export" if `format !== 'acbridge-demo-export'` or `tables` is not an object.
2. Deletes and recreates `demo-from-browser.db` in the output folder (default: the `database/` folder).
3. For each table it takes the union of keys over all rows as columns and infers a SQL type from the first non-null value (`INTEGER`, `REAL`, or `TEXT`; booleans become `INTEGER` 0/1; objects become JSON text). An empty table becomes `(id TEXT)`.
4. Creates views if the needed tables exist: `v_requests` (request + job + artisan), `v_payments` (payment + artisan), `v_ledger_balances` (balance per account, `collection` debit-normal, others credit-normal).
5. Writes one UTF-8 CSV (with BOM) per table and view in `csv-from-browser/`.
6. Runs `make-browser.mjs` to produce `demo-from-browser.html`: a single page with a table list, search box and row counts, data embedded as JSON, database opened read-only, columns named like `password` truncated, at most 5,000 rows per table loaded.

## File by file

### `apps/web/src/screens/Operator.tsx`
Single component `Operator()`. Key derived values: `pending`, `verified`, `ledger` (vouch chain check), `doneJobs`, `earnings`. `describe(e)` builds the audit text. Security note: the PIN comparison is in the browser and the bundle contains the PIN.

### `apps/web/src/components/OperatorPayments.tsx`
Component `OperatorPayments()`. Pure presentation plus the three local state objects. All checks run again in the store and reducer, so the panel's disabled Hold button is a convenience, not the rule.

### `apps/web/src/domain/export.ts`
- `Row`, `Snapshot` types.
- `exportSnapshot` field choices:
  - `artisans`: id, name, username, phone, trade, neighbourhood, description, `seedAccount` (from `isSeed`), `seedVerified`, `operatorApproved`, `rejected`, base rating/jobs, price range, average response, `backendId` (`remoteId`). **`salt` and `passwordHash` are deliberately left out.**
  - `customers`: derived, one row per distinct `customerPhone` in requests (`phone`, `name`).
  - `vouches`, `requests`, `jobs`, `payments`, `payouts`, `ledger`, `ratings`: shallow copies of the state rows. Vouches include `seal`, `prevHash`, `hash`. Jobs include `codeHash` (a one-way hash of the job code, never the code).
  - `chats`: id, jobId, from, text (already contact-masked), key, params as JSON string, price, at.
  - `sms`: id, to, key, params as JSON string, at. SMS rows contain the simulated messages, which include job codes in `sms.jobCode` params, and phone numbers.
  - `audit`: id, kind, params as JSON string, at.
- Not exported: password hashes and salts, UI state (`ui`), language.
- Phone numbers are exported in clear (`artisans.phone`, `customers.phone`, `payments.phone`, `sms.to`); only the operator screen masks payment phones.

### `apps/web/src/i18n/format.ts`
`MONEY_PARAMS = {price, commission, payout, amount}`; `renderParams(params, t, lang)` as described above; `money(n, lang)` delegates to `formatAmount` in `@acbridge/core`.

### `apps/web/src/config.ts` and `data/seed.ts`
`OPERATOR_PIN = '1234'`. `SEED_OPERATOR.pin` is that value. The seed has one pending candidate, `seed-5` Samuel, which is why the operator list is not empty on a fresh demo.

### `apps/web/database/make-browser.mjs`
`node --no-warnings database/make-browser.mjs <db> <out.html> "<title>"`. Reads table and view names from `sqlite_master`, adds a description from a built-in `DESCRIPTIONS` map (backend tables and browser-export tables), escapes `<` in the embedded JSON, shows `password*` columns as a 14-character prefix plus "(hash)".

### `apps/web/database/build-demo-db.mjs`
See the steps above.

### `backend/scripts/build_database.py`
Builds a different database: `acbridge.db` with the **backend's** tables (`app/models.py`), seeded by `app/seed.py`, then plays scenario stories through the real FastAPI app in-process (a paid and rated plumbing job with chat bargaining; a paid job in progress; a finished job whose payout the operator held with a reason; an open request; an expired offer; a waiting offer; a new artisan collecting endorsements). It sets `COMMISSION_MODEL=customer_split` and `PROBATION_HOURS=0`, writes `schema.sql`, `views.sql` and `csv/`. It is rerun by developers (`python scripts/build_database.py`); the web app never calls it, and it is unrelated to the browser Export button.

### `apps/web/database/README.md`
Explains both databases and the three-step flow for the browser export (Operator PIN `1234`, Export data, run `build-demo-db.mjs`, open `demo-from-browser.html`). States that generated files are git-ignored and that the SQLite file is a viewing copy while the real backend uses PostgreSQL.

## Data and state

Reads from `State`: `artisans`, `vouches`, `jobs`, `ratings`, `payments`, `payouts`, `ledger`, `audit`, `lang`. Writes only through reducer actions:

| Action | Fields changed |
|---|---|
| `operator` | `Artisan.operatorApproved`, `Artisan.rejected`; `sms`; `audit` (verification). |
| `payoutHold` | `Payout.status = 'HELD'`, `Payout.note`; `audit` (payout). |
| `payoutRelease` | `Payout.status = 'PAID'`, `paidAt`, `note`; `ledger` (+2 lines); `sms`; `audit`. |
| `reset` | Entire state replaced by `initialState()` keeping `lang`. |

Not persisted: `unlocked`, PIN text, per-payout reason text, errors, the mismatch `override`, `confirmReset` (component state). Persisted: all `State` in `localStorage` key `acbridge.demo.v2`. Persisted by the export: a downloaded JSON file.

## Rules and edge cases

| Rule | Where | Message key |
|---|---|---|
| PIN must equal `OPERATOR_PIN` | `Operator.tsx` (UI only) | `operator.wrongPin` |
| Hold/release reason at least 5 characters (`MIN_REASON`), trimmed | `checkHold`, `checkRelease` in `ledger.ts`; enforced again in the reducer | `opay.errReason` |
| Only a `PENDING` payout can be held | `checkHold` `not_holdable` | `opay.errState` |
| Release only for `PENDING` or `HELD` payouts | `checkRelease` `not_releasable` | `opay.errState` |
| Release only after the job code was verified (job `COMPLETED`) | `checkRelease` `not_completed` | `opay.errNotCompleted` |
| Unknown payout | `no_payout` | `opay.errState` |
| Reset needs confirmation | UI two-step | `operator.resetAsk` |
| Approving an artisan clears a previous rejection | reducer `operator` | none |
| A rejected artisan disappears from the pending list and is never verified | `pending` filter, `isVerified` | none |
| Export never contains password hashes or salts | `exportSnapshot` | none |

Edge cases: the "Hold" button is disabled for a payout already `HELD`, but "Release" is available for both. A payout `PAID` shows no reason box and no buttons. A `FAILED` payout cannot occur from the UI. A `PENDING` payout can be released by the operator before the artisan finishes only if the job is `COMPLETED`, which implies the code was already used, so in practice release is meaningful for `HELD` payouts. The reason is stored in `Payout.note` and shown under the payout and in the audit entry; `audit.payout_paid` (automatic payout on completion) has an empty reason.

## Tests

| File | Tests |
|---|---|
| `apps/web/src/__tests__/ui-flows.test.tsx` | "registers, gets vouched, ... shows in the operator log": wrong PIN `0000` shows `PIN incorrect` and no audit log, `1234` opens it, audit contains "Note 5/5 pour Joel" and "Commission 5% = 275 FCFA enregistrée", "Chaîne intacte", earnings "275 FCFA sur 1 travaux terminés", ledger shows platform revenue 275 and artisan paid 5 225, "Grand livre équilibré", reconciliation OK, "Simuler un écart" gives the Mismatch alert, "Effacer" clears it, language switch to EN. "the operator can hold a pending payout with a reason, completion does not pay it, and release pays it": empty reason shows "au moins 5 caractères", hold with reason shows status Held and audit "Versement bloqué", artisan completion does not pay, release pays and the ledger moves, ledger still balanced. "survives a refresh (localStorage) and Reset demo clears it": pending artisan listed, reset with confirmation returns to the welcome screen. |
| `apps/web/src/__tests__/payments.test.ts` | "needs a reason, and release needs a completed job" (`checkHold`/`checkRelease`); "shows zero difference normally, a Mismatch when the provider total disagrees, and flags unpaid completed jobs" (`reconcile`, override 6500 gives difference 500); "masks phone numbers like the backend". |
| `apps/web/src/__tests__/export.test.ts` | "never exports password hashes or salts"; "covers accounts, requests, jobs, chat, payments, payouts and the ledger" (9 artisans, 1 request, customer Mary, payment 6000 succeeded, payout 5700 / 300 PENDING, 3 ledger lines); "becomes a real SQLite database through database/build-demo-db.mjs (and a browsable HTML page)" (runs the script, checks `v_requests`, `v_ledger_balances`, `v_payments`, HTML contains the request text and no `passwordHash`); "rejects a file that is not an ACbridge export" (exit code 1 and message). |

## Backend connection

- The operator PIN screen itself has no backend call. In API mode only `actions.operator` mirrors: `bridge.operatorDecision(artisan, approve)` logs in as the artisan, submits a skill verification check (`POST /verifications`), then as the verifier (`+237670000002`) records `UNDER_REVIEW` and `APPROVED` or `REJECTED` (`POST /verifications/{id}/decision`) with the note "SIMULATED operator decision". It returns silently if the artisan has no `remoteId` or the check cannot be submitted.
- Hold, release, reconciliation, ledger and payment lists are **not** called on the backend from the web app. The backend has equivalent endpoints (`GET /operator/payments`, `/operator/ledger`, `/operator/payouts`, `POST /operator/payouts/{id}/hold` and `/release` with a required reason, `GET /operator/reconciliation`, `GET /operator/audit`, see `PAYMENTS.md`), protected by the ADMIN role and JWT instead of a PIN. The web panel computes the same figures locally with the same rules (balanced ledger, reason of 5+ characters, release only after completion, unpaid completed jobs flagged).
- Export/database: separate. `backend/scripts/build_database.py` builds `acbridge.db` from the real backend; `build-demo-db.mjs` builds `demo-from-browser.db` from browser data. Table names differ (backend `ledger_entries`, `payments`, `payouts`, `audit_log`; browser export `ledger`, `payments`, `payouts`, `audit`).

## Known limits and what changes in the production rebuild

- **The PIN is not security.** It is compared in the browser against a constant in the bundle (`1234`). Production uses an administrator account with login and a server-checked role (as the backend already does), with every operator action checked and logged on the server.
- **All operator data is local.** The panel shows what is in this browser's `localStorage`; it is not a view of a shared system. Anyone can edit local state. In production the panel reads the backend's `/operator/*` endpoints.
- **Reconciliation is derived.** The "provider" side is computed from the local payment and payout records, not from a real provider statement, so it only differs when the override button is used. A real build compares provider reports to the ledger.
- **Simulate mismatch** changes only a screen variable; it does not write anything or raise any alert elsewhere.
- **Audit log is mutable** local data, not append-only with hashes like the backend's `audit_log`. The vouch chain check (`verifyLedger`) detects edits to vouches only.
- **Export contains personal data** (phones in clear, SMS texts with job codes) as the demo data is simulated; a production export would need access control and data minimisation. Password material is the one thing deliberately excluded.
- **Reset** wipes browser data irreversibly (after one confirmation).
- **Audit log is not paginated or filtered** and shows every entry in insertion order.
- `build-demo-db.mjs` needs Node 22.5+, infers column types from the first non-null value, and does not define keys or constraints; it is a viewing copy, not a migration into the backend schema.
