# Payments (customer Payments tab and the money model)

On the customer side, the Payments tab shows the price the artisan agreed to, lets the customer pick MTN MoMo or Orange Money and type a phone number, waits while a simulated provider answers, then shows either a "payment received" receipt or a "payment failed" screen with a retry button. Behind the screen sits a double-entry ledger in whole FCFA: when a payment succeeds the platform commission is booked at once and the artisan's share waits as a pending payout until the job code is entered.

Everything here is a **sandbox**: no real money moves. The "provider" is a `setTimeout` in the store that settles the payment after 5 seconds.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/Payments.tsx` | The customer Payments tab: 5 screens (price card, method + phone keypad, waiting, result, receipt). |
| `apps/web/src/domain/ledger.ts` | Pure money rules: `postTx`, `balances`, `unbalancedTransactions`, `paymentSucceededLines`, `payoutPaidLines`, `checkPayStart`, `isPaid`, `checkHold`, `checkRelease`, `reconcile`, sandbox constants. |
| `apps/web/src/domain/money.ts` | `computeCommission` (rate check, rounding, price = commission + payout), `agreedPrice`, `netRange`. |
| `apps/web/src/config.ts` | `COMMISSION_RATE` (5%), `MIN_COMMISSION_RATE` (3%), `MAX_COMMISSION_RATE` (7%) and the reasoning comment. |
| `apps/web/src/store/reducer.ts` | Reducer actions `payStart`, `paySettle`, `payoutHold`, `payoutRelease`, and the payout "paid" step inside `complete`. |
| `apps/web/src/store/index.tsx` | `startPayment`, `scheduleSettle` (the sandbox provider), and the effect that resumes a pending payment after a page refresh. |
| `apps/web/src/api/bridge.ts` | `payJob`: mirrors a successful payment to the backend in API mode. |
| `apps/web/src/api/client.ts` | `api.pay` (sends `Idempotency-Key`) and `api.approvePayment` (sandbox approval). |
| `apps/web/src/domain/types.ts` | `PaymentRec`, `Payout`, `LedgerLine`, `Job` types. |
| `apps/web/src/screens/Tracking.tsx` | Reads `isPaid` to show or lock the artisan's phone number; links to the Payments tab. |
| `PAYMENTS.md` (repo root) | Specification of the backend payments module this code mirrors. |
| `backend/app/services/ledger_service.py`, `payout_service.py`, `payment_service.py` | Backend ledger, payout and payment rules. |
| `backend/app/routers/jobs.py`, `backend/app/routers/payments.py` | `POST /jobs/{id}/pay`, `POST /payments/{id}/simulate-approval`, signed webhook. |

## How it works

1. **Entry.** On the Tracking screen the "pay" button (`pay.open`) appears when the job status is `ACCEPTED` or `COMPLETED`; it calls `actions.go('payments')`. `Payments` finds the job via `state.ui.jobId`, plus its artisan, its request and all `state.payments` for that job. `latest` is the last payment of that job.
2. **Screen 1, agreed price card** (local `step === 'card'`, no live payment). Shows artisan name and trade, job description, `job.price` twice (`pay.price`, `pay.youPay`), the sentence `pay.instruction`, the fee note `pay.fee` ("ACbridge keeps a small service fee from the artisan's share, not from you") and `pay.protect`. The "Pay now" button (`pay.now`) is disabled unless `job.status === 'ACCEPTED'`; otherwise the notice `pay.notReady` is shown. The amount is `job.price`; there is no amount input anywhere.
3. **Screen 2, method + phone** (`step === 'method'`). Two radio-style buttons from `METHODS` (`mtn`, `orange`), a phone text input that strips everything except digits and `+` and caps at 13 characters, and a numeric keypad (`press` appends up to 12 digits, the backspace key removes one). Submit calls `start`.
4. `start` calls `actions.startPayment(job.id, method, phone)`. If it returns `{ ok: false, reason }` the screen maps the reason to a message: `bad_phone` to `pay.errPhone`, `bad_method` to `pay.errMethod`, `already_live` to `pay.errLive`, anything else to `pay.errNotReady`. With no method chosen the screen shows `pay.errMethod` itself before calling the store.
5. **Store `startPayment`** (`store/index.tsx`): normalises the phone with `normalizePhone`, runs `checkPayStart(job, payments, method, normalized)`, and returns the refusal if any. Otherwise it generates `id = uid('pay')`, a reference `SIM-` plus 8 random upper-case characters, dispatches `payStart`, then calls `scheduleSettle(id, normalized === SANDBOX_DECLINED_PHONE ? false : true, SANDBOX_APPROVE_AFTER_MS)`.
6. **Reducer `payStart`** re-runs `checkPayStart` (the UI is not trusted) and creates a `PaymentRec` with `amount: job.price`, `status: 'pending'`. It appends an audit entry `kind: 'payment'`, `event: 'started'`. No ledger entry yet.
7. **Screen 3, waiting** (`latest.status === 'pending'`). Shows `pay.waiting` and `pay.waitingHint` ("We check every 3 seconds, for up to 3 minutes"). An effect starts `setInterval(..., POLL_EVERY_MS)` that only bumps a `tick` counter to re-render; it does not call a server. `timedOut` becomes true when `Date.now() - latest.createdAt > POLL_MAX_MS` and the screen then adds the alert `pay.timeout` ("Nothing was charged. Try again.").
8. **Sandbox settle.** After 5 s the `setTimeout` in `scheduleSettle` dispatches `paySettle` with `ok`, a fresh six-digit job code from `generateJobCode()`, a timestamp and 4 ids.
9. **Reducer `paySettle`, failure** (`ok === false`): payment becomes `failed` with `settledAt`; SMS `sms.payFailed` to the customer; audit `payment/failed`. No ledger lines, no payout, no job code.
10. **Reducer `paySettle`, success:**
    - `paymentSucceededLines(payment.amount)` returns the three ledger lines plus `commission` and `payout`.
    - A `Payout` is created: `status: 'PENDING'`, `amount = payout`, `commission`.
    - The payment becomes `succeeded`.
    - `postTx(s.ledger, 'payment-succeeded:<paymentId>', lines, at)` books the money.
    - A system chat message `chat.sysClosed` is added (chat closes after payment).
    - The job gets `codeHash: hashCode(a.code)`, `commissionRate`, `commission`, `payout`. The plain code is not stored on the job; it only goes into the SMS `sms.jobCode` to the customer.
    - SMS `sms.paymentReceived` to the artisan tells them price, rate, commission and payout.
    - Audit `payment/succeeded` with the figures.
11. **Screens 4 and 5, result and receipt.** When `latest.status` is `succeeded` (or `failed` while `step === 'card'`) the screen shows a badge (`pay.success` / `pay.failed`). On success it shows `pay.notified` and a receipt `<dl aria-label="pay.receipt">` with `pay.ref` (the `SIM-` reference), `pay.date` (`settledAt` in the UI language), `pay.amount`, `pay.artisan` (first name only) and `pay.status.succeeded`. On failure it shows `pay.failedWhy` and a "Try again" button (`pay.again`) that sets `step = 'method'` and clears the form; the next `checkPayStart` passes because failed payments are not "live".
12. **Unlocking.** Tracking shows the artisan's phone only when `isPaid(job, payments)`, otherwise `🔒 pay.contactLocked`. The artisan cannot finish the job until the code exists: the inbox and the completion screen show `complete.waitPay` while there is no `codeHash`.
13. **Completing.** When the artisan enters the right code, the reducer's `complete` action sets the job `COMPLETED`, and if the payout is still `PENDING` marks it `PAID`, posts `payout-paid:<payoutId>` (`artisan_pending` DEBIT, `artisan_paid` CREDIT), sends `sms.payoutPaid` and an audit `payout/paid`. A `HELD` payout is not paid (see Rules).
14. **API mode.** After `paySettle` dispatches, if `ok` the store calls `mirror(() => bridge.payJob(job, payment.phone))`.

## File by file

### `apps/web/src/screens/Payments.tsx`
- Purpose: the whole customer payments UI as one component, `Payments()`.
- Local state: `step` (`'card' | 'method'`), `method`, `phone`, `error` (an i18n `Key`), and a throw-away `tick` used only to re-render on the polling interval.
- Branch order matters: missing job or artisan gives an empty screen with `tracking.none`; then `waiting` (screen 3); then succeeded / failed-with-`step==='card'` (screens 4-5); then `step === 'method'` (screen 2); otherwise the price card (screen 1).
- After a failure the user is on the result screen until they press "Try again"; this works because the failed branch is only taken while `step === 'card'`.
- The input is sanitised in the UI (`replace(/[^\d+]/g, '')`, `slice(0, 13)`), but the real validation is `normalizePhone` in the store.
- No commission is shown anywhere. The only fee text is `pay.fee`, a generic sentence saying the fee is taken from the artisan's share.
- Every screen ends with the sandbox disclaimer `pay.sandbox`.
- Methods are hard coded: `🟡 pay.mtn`, `🟠 pay.orange`.

### `apps/web/src/domain/ledger.ts`
Pure functions, no I/O. Exports:

| Export | Takes / returns |
|---|---|
| `Account`, `ACCOUNTS` | `'collection' \| 'platform_revenue' \| 'artisan_pending' \| 'artisan_paid' \| 'refund_payable'`. |
| `Line` | Tuple `[account, 'DEBIT' \| 'CREDIT', amount]`. |
| `postTx(ledger, txKey, lines, at)` | Returns a new ledger array. Throws `RangeError` if any amount is not a positive integer or debits differ from credits. If a line with the same `txKey` already exists it returns the ledger unchanged (idempotent). Line ids are `<txKey>#<index>`. |
| `balances(ledger)` | Per-account balance. `collection` is debit-normal (DEBIT adds); every other account is credit-normal (CREDIT adds). |
| `unbalancedTransactions(ledger)` | `txKey`s whose debit total differs from credit total; must be `[]`. |
| `paymentSucceededLines(price)` | `{ lines, commission, payout }` from `computeCommission(price)`. |
| `payoutPaidLines(amount)` | `[artisan_pending DEBIT, artisan_paid CREDIT]`. |
| `PAY_METHODS`, `PayMethod` | `'mtn'`, `'orange'`. |
| `SANDBOX_APPROVE_AFTER_MS` | `5000`. |
| `POLL_EVERY_MS` | `3000`. |
| `POLL_MAX_MS` | `3 * 60 * 1000`. |
| `SANDBOX_DECLINED_PHONE` | `'+237600000000'`, always declined so the failure screen can be demoed. |
| `checkPayStart(job, payments, method, phone)` | `{ ok: true }` or `{ ok: false, reason }` with `no_job`, `not_accepted`, `no_price`, `already_live`, `bad_method`, `bad_phone`, checked in that order. "Live" means a payment of the same job with status `pending` or `succeeded`. |
| `isPaid(job, payments)` | True when a `succeeded` payment exists for the job. |
| `maskPhone` | Re-exported from `@acbridge/core`: `+237670123456` becomes `+237 6******56`; fewer than 8 digits becomes `***`. |
| `MIN_REASON` | `5`. |
| `checkHold(payout, reason)` | See Rules. |
| `checkRelease(payout, job, reason)` | See Rules. |
| `reconcile(ledger, payments, payouts, jobs, providerCollectedOverride = null)` | Returns `{ ledger, provider: {collected, disbursed}, differences, unbalanced, mismatch, unpaidCompleted }`. Provider "collected" is the sum of succeeded payments (or the override), "disbursed" is the sum of `PAID` payouts. Differences are provider minus ledger (`collection`, `artisan_paid`). `mismatch` is true if either difference is non-zero or any transaction is unbalanced. `unpaidCompleted` counts `COMPLETED` jobs without a succeeded payment, grouped by artisan. |

### `apps/web/src/domain/money.ts`
- `computeCommission(price, rate = COMMISSION_RATE)`: throws `RangeError` if the rate is outside 3%-7% (with a tiny epsilon) or the price is negative or not finite. Returns `{ price, rate, ratePercent, commission, payout }` with `commission = Math.round(price * rate)` and `payout = price - commission`, so `price = commission + payout` always.
- `agreedPrice(artisan)`: simulated starting price, the middle of the artisan's range rounded to 100 FCFA. Used by `choose` in the store; later replaced if the artisan states an amount in chat.
- `netRange(artisan, rate)`: what the artisan keeps at both ends of their range.

### `apps/web/src/config.ts`
`COMMISSION_RATE = 0.05`, `MIN_COMMISSION_RATE = 0.03`, `MAX_COMMISSION_RATE = 0.07`. The comment gives the reasoning: typical jobs are 3,000-8,000 FCFA so 5% is 150-400 FCFA; artisans keep about 95%, which gives them little reason to take jobs off-platform; mobile-money cash-out costs the artisan about 1-2% more, so above 5% their total cost would pass 8%; 3-4% would leave almost nothing after processing costs. The commission is taken from the artisan's side only.

### `apps/web/src/store/reducer.ts` (money actions)
- `payStart`: see How it works step 6.
- `paySettle`: ignores unknown payments and any payment not in `pending`, so a replayed callback changes nothing.
- `payoutHold` / `payoutRelease`: operator actions, see `11-operator-panel-and-database-export`. `payoutRelease` marks `PAID`, sets `paidAt` and `note`, posts `payout-paid:<payoutId>`, sends `sms.payoutPaid`, audit `payout/released`. `payoutHold` marks `HELD` with `note` and audit `payout/held`.
- `complete`: pays the payout only when its status is exactly `PENDING`.

### `apps/web/src/store/index.tsx` (money parts)
- `startPayment(jobId, method, phone)`: see step 5. Returns the `PayCheck`.
- `scheduleSettle(paymentId, ok, delayMs)`: the sandbox provider. After `delayMs` dispatches `paySettle` (job code generated here because it is impure), then in API mode mirrors success to the backend.
- Resume effect: on mount, every payment still `pending` is rescheduled with delay `max(0, 5000 - (now - createdAt))`, and `ok = p.phone !== SANDBOX_DECLINED_PHONE`. So a refresh during the wait settles the payment correctly (immediately if the 5 s already passed).
- `holdPayout`, `releasePayout` run the `check*` function first and dispatch only on `ok`.

### `apps/web/src/api/bridge.ts` and `client.ts`
See Backend connection.

## Data and state

Read or written (see `apps/web/src/domain/types.ts`):

| Type | Fields relevant here |
|---|---|
| `Job` | `status` (`ACCEPTED` needed to pay), `price`, `priceSource`, `codeHash` (null until paid), `commissionRate`, `commission`, `payout` (set at payment success), `remoteId`. |
| `PaymentRec` | `id`, `jobId`, `method` (`mtn`/`orange`), `phone` (normalised), `amount` (copied from `job.price`), `status` (`pending`/`succeeded`/`failed`), `reference` (`SIM-XXXXXXXX`), `createdAt`, `settledAt`. |
| `Payout` | `id`, `jobId`, `artisanId`, `paymentId`, `amount` (price minus commission), `commission`, `status` (`PENDING`/`HELD`/`PAID`/`FAILED`), `note`, `createdAt`, `paidAt`. `FAILED` is in the type but no code path sets it. |
| `LedgerLine` | `id` (`<txKey>#<i>`), `txKey`, `account`, `direction`, `amount`, `at`. |
| State | `State.payments`, `State.payouts`, `State.ledger`, plus `audit` and `sms`. |

Persisted: the whole `State` is saved to `localStorage` by `saveState` in an effect on every change (`store/persistence.ts`), so payments, payouts and ledger survive a refresh. The plain job code is never in state, only its hash plus the SMS text in the simulated SMS log.

### The ledger, exactly

For a 6,000 FCFA job at 5% (commission 300, payout 5,700):

| Event | txKey | Lines |
|---|---|---|
| Payment succeeds | `payment-succeeded:<paymentId>` | DEBIT `collection` 6000; CREDIT `platform_revenue` 300; CREDIT `artisan_pending` 5700 |
| Payout paid (job code entered, or operator release) | `payout-paid:<payoutId>` | DEBIT `artisan_pending` 5700; CREDIT `artisan_paid` 5700 |

Balances after payment: `collection 6000, platform_revenue 300, artisan_pending 5700, artisan_paid 0`. After payout: `artisan_pending 0, artisan_paid 5700`. `refund_payable` exists as an account but nothing in the web app posts to it (the backend does, for refunds).

`collection` and `artisan_paid` describe the provider side (gross collected and money sent out); the other three are the platform's own books.

## Rules and edge cases

| Rule | Enforced where | Detail |
|---|---|---|
| Amount comes from the job, never the UI | `payStart` reducer sets `amount: job.price`; `startPayment` has no amount parameter | Test: "the amount always comes from the job...". |
| Only an `ACCEPTED` job with `price > 0` can be paid | `checkPayStart` (rules), re-checked in reducer, button disabled in UI | Reasons `not_accepted`, `no_price`. UI shows `pay.notReady`. |
| One live payment per job | `checkPayStart` `already_live` | A second `payStart` is ignored by the reducer. UI message `pay.errLive`. |
| A failed payment can be retried | `checkPayStart` ignores `failed` | "Try again" button. |
| Method must be `mtn` or `orange` | `checkPayStart` `bad_method` | `pay.errMethod`. |
| Phone must normalise | `normalizePhone` returns `null` gives `bad_phone` | `pay.errPhone`. `670123456` becomes `+237670123456`. |
| Replayed callback does nothing | `paySettle` skips non-pending payments, and `postTx` skips a repeated `txKey` | Two layers of idempotency. |
| Unbalanced or non-positive posting is a bug | `postTx` throws `RangeError` | Not a user-facing error. |
| Commission rate in 3%-7% | `computeCommission` throws `RangeError` | Config guard. |
| No commission shown to the customer | `Payments.tsx` and the receipt contain no commission field | Test asserts `queryByText(/Commission de la plateforme/)` is null and the receipt does not match `/ommission/`. |
| Job code and artisan phone unlock only after payment | `paySettle` sets `codeHash` and sends `sms.jobCode`; `Tracking.tsx` uses `isPaid` for the phone | `choose`/`answer` leave `codeHash: null`. The code is stored hashed (`hashCode`). |
| Chat closes after payment | `paySettle` adds `chat.sysClosed` | |
| Payout paid only for `PENDING` | `complete` reducer | A `HELD` payout stays held when the artisan completes. |
| Hold needs reason of 5+ characters and a `PENDING` payout | `checkHold`: `no_payout`, `bad_reason`, `not_holdable` | |
| Release needs reason of 5+ characters, payout `PENDING` or `HELD`, job `COMPLETED` | `checkRelease`: `no_payout`, `bad_reason`, `not_releasable`, `not_completed` | |
| Sandbox: `+237600000000` is always declined | `startPayment` / resume effect | Anything else is approved. |

Error message keys used on this screen: `pay.errPhone`, `pay.errMethod`, `pay.errLive`, `pay.errNotReady`, `pay.timeout`, `pay.failedWhy`.

Timeout note: `POLL_MAX_MS` only controls when the screen shows `pay.timeout`. It does not cancel or fail the payment; the `setTimeout` still settles it. Also `store/index.tsx` has a no-op `void POLL_MAX_MS;` to keep the import.

## Tests

| File | Tests (names) |
|---|---|
| `apps/web/src/__tests__/payments.test.ts` | "every transaction balances and an unbalanced one is refused"; "posting the same transaction twice (a replayed callback) does not double-credit"; "paying the artisan moves the share from pending to paid, still balanced"; "only an accepted job with a price can be paid, once, with a method and a valid phone"; "the amount always comes from the job, and a second live payment is ignored"; "a declined payment books nothing and can be retried"; "needs a reason, and release needs a completed job"; "shows zero difference normally, a Mismatch when the provider total disagrees, and flags unpaid completed jobs"; "masks phone numbers like the backend". |
| `apps/web/src/__tests__/journey.test.ts` | "runs register, 2 vouches, request, choose, YES, PAY, wrong code, right code, payout, rate once": no `codeHash` before payment, ledger `{6000, 300, 5700, 0}` after payment, only the hash stored, wrong code moves nothing, right code pays out, replay ignored. |
| `apps/web/src/__tests__/ui-flows.test.tsx` | "registers, gets vouched, is matched, agrees, is PAID, completes with the job code, ..." (rendered app: phone hidden before paying, no commission text, bad phone alert, 5.2 s wait, receipt shows `SIM-` and artisan first name, code SMS goes to the customer); "a declined payment shows the failure screen and can be retried; nothing is booked" (`600000000`, then Orange, statuses `['failed','succeeded']`); "the operator can hold a pending payout with a reason, completion does not pay it, and release pays it". |
| `apps/web/src/__tests__/security-money.test.ts` | "the chosen platform rate is inside 3%-7% (inclusive)"; "takes the commission from the artisan: price = commission + payout, whole francs"; "accepts 3% and 7% but refuses anything outside the band"; "derives the simulated agreed price and net range from the artisan range". |
| `backend/tests/test_ledger_payments.py` | Backend equivalents, e.g. "test_customer_payment_books_commission_at_once_and_holds_the_artisan_share", "test_every_money_event_is_balanced_through_the_whole_life_of_a_job", "test_same_idempotency_key_creates_one_payment_and_one_set_of_entries", "test_agreed_price_is_frozen_and_the_amount_never_comes_from_the_request", "test_a_signed_webhook_marks_the_payment_succeeded_and_a_replay_does_not_double_credit". |

## Backend connection

Local mode: none, everything above runs in the browser. In API mode (`API_MODE === 'api'`, set via `?api=<url>` or `VITE_API_MODE=api`) the store calls `mirror(...)` after a **successful** settle only:

1. `bridge.payJob(job, phone)` returns immediately if `job.remoteId` is missing. It logs in as the customer (`login(job.customerPhone)`), then `api.pay(token, job.remoteId, 'ui-' + job.id)`.
2. `api.pay` is `POST /jobs/{id}/pay` with **no body** and the header `Idempotency-Key: ui-<localJobId>`. The server reads the amount from the job in its database.
3. `api.approvePayment` is `POST /payments/{payment_id}/simulate-approval`, the sandbox stand-in for the provider's signed webhook (`POST /webhooks/payments/{provider}`, HMAC-SHA256 in `X-Signature`).
4. Failures show a notice (`mode.api` prefix) and the demo keeps working offline. Failed local payments are not mirrored.

Backend rules mirrored (see `PAYMENTS.md`):
- `ledger_service.py`: same accounts and entries (`payment-succeeded:<id>`, `payout-paid:<id>`), same idempotent `post` by `tx_key`, same rule that debits equal credits and amounts are positive integers, same `balances` sign convention.
- `payout_service.py`: PENDING payout after payment, release only on completion, hold by operator.
- `payment_service.py` / `job_service.pay_job`: one live payment per job, amount from `agreed_price`, ACCEPTED required, idempotency key returns the same payment, a key reused for another job is a conflict.
- `routers/jobs.py`: `POST /jobs/{id}/pay` with `Idempotency-Key` (max 80 chars), rate limit per phone (5 per 10 minutes).
- `routers/payments.py`: `simulate-approval`, `simulate-failure`, and the signed webhook.

Differences: the backend default commission model is `artisan_upfront`; the web demo always behaves like `customer_split`. The backend commission has a minimum (`COMMISSION_MIN`, 300 FCFA) and uses integer basis points, while the web uses `Math.round(price * 0.05)` with no minimum. The backend has no job-code endpoint: in API mode the job code is a front-end mechanism and `bridge.completeJob` sends both confirmations. The web does not mirror a failed payment, and does not send the customer's phone to the backend (`_phone` is unused in `payJob`).

## Known limits and what changes in the production rebuild

- **Simulated provider.** `scheduleSettle` is a browser timer; real MTN/Orange integration needs a licensed provider, a hosted payment prompt (the app must never see a PIN or OTP), and a signed webhook that the server verifies. Today the local result is decided by the phone number, not a provider.
- **Local-only truth.** In local mode the ledger and payment state live in the browser and can be edited by the user; in production they must live only on the server. The web ledger would then be a read-only view.
- **Client-side checks only.** `checkPayStart`, the amount rule and the code unlock are enforced in the browser; the real guarantee comes from the backend's `pay_job`.
- **Polling is cosmetic.** The 3 s polling does not query anything; it re-renders. A real build polls `GET /payments/{id}` (or listens for the webhook).
- **Timeout does not cancel.** After 3 minutes the screen only warns; a real build must mark the payment failed or expired on the server.
- **Refund and failed payouts.** `refund_payable` and `Payout.status = 'FAILED'` are modelled but unused in the web app.
- **Rounding.** `Math.round` on a floating product is fine for 5%, but the backend uses integer basis points and a minimum fee; the production rebuild should use the backend's `compute_commission` as the only source.
- **Reference.** `SIM-...` references are random local strings, not provider references.
- **Job code.** Generated and hashed in the browser; production should generate and verify it on the server.
