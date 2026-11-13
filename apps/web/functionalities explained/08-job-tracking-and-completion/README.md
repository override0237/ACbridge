# Job tracking and completion

The customer follows a job on a four-step tracker (Requested, Accepted, Completed, Rated). After the customer pays, a 6-digit job code is sent to the customer by SMS. When the work is done the customer gives the code to the artisan, who types it on a keypad; a correct code completes the job and releases the artisan's payout.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/Tracking.tsx` | Customer tracker: four steps, status message, price and (locked) artisan phone, and the action buttons (pay, chat, choose another, rate, open as artisan, profile). |
| `apps/web/src/screens/ArtisanComplete.tsx` | Artisan screen to finish a job: price breakdown, 6-digit code field, keypad, error line, success state. |
| `apps/web/src/domain/rules.ts` | `generateJobCode`, `hashCode`, `checkCompletion` (and `CompletionCheck`). |
| `apps/web/src/store/reducer.ts` | `paySettle` (creates the job code hash on payment success), `complete` (completes the job and pays out), `answer` (YES/NO that moves the job to `ACCEPTED` or `DECLINED`). |
| `apps/web/src/store/index.tsx` | `actions.complete`, `actions.answer`, and `scheduleSettle` (where the job code is generated). |
| `apps/web/src/components/PriceBreakdown.tsx` | Price, commission and artisan-receives box (`done` variant after completion). |
| `apps/web/src/domain/ledger.ts` | `isPaid(job, payments)` used by Tracking; `payoutPaidLines`, `postTx` used by completion (covered in the payments README). |
| `apps/web/src/api/bridge.ts` | `completeJob`: API-mode mirror of completion. |

## How it works

### Tracker states

1. `Tracking()` finds the job (`state.ui.jobId`), its artisan, and whether a rating exists (`state.ratings.some(r => r.jobId === job.id)`).
2. The current step index is:

```ts
const current = rated ? 3 : job.status === 'COMPLETED' ? 2 : job.status === 'ACCEPTED' ? 1 : 0;
const declined = job.status === 'DECLINED' || job.status === 'EXPIRED';
```

3. The steps (`STEPS`) are `tracking.step.requested`, `.accepted`, `.completed`, `.rated`. A step before `current` is `done` (a check mark); step `current` is `current` (with the "Now" label `tracking.current`, hidden when declined); later steps are `todo`. When rated, step 3 is also `done`.
4. The message (`msgKey`) is chosen in this order: `EXPIRED` -> `tracking.msgExpired`; declined -> `tracking.msgDeclined`; rated -> `tracking.msgRated`; `COMPLETED` -> `tracking.msgCompleted`; `ACCEPTED` -> `tracking.msgAccepted`; otherwise `tracking.msgRequested`. It is shown as the screen instruction and in a `role="status"` notice.
5. If not declined/expired, a facts card shows the price (`pay.price`, `job.price`) and the artisan phone (`pay.contact`). The phone is shown only when `isPaid(job, state.payments)` (some payment for the job is `succeeded`); otherwise `🔒 pay.contactLocked` ("Hidden until you pay").
6. Buttons:
   - `pay.open` (Payments) when the status is `ACCEPTED` or `COMPLETED`.
   - `chat.open` when `isChatOpen(job)` (section 06).
   - `tracking.again` ("Choose another", back to `matches`) when declined or expired.
   - `tracking.rate` when `COMPLETED` and not rated.
   - `tracking.asArtisan` ("Open as artisan") when not declined, not rated and not completed: goes to `artisanInbox` if already logged in as this job's artisan, otherwise to `artisanLogin` with `loginNext: 'artisanInbox'`.
   - `tracking.profile` always.

### From request to job code

1. `choose` creates the job as `REQUESTED` with `codeHash: null` (section 05).
2. The artisan taps YES: `actions.answer(jobId, true)` (after the expiry check, see section 07) dispatches `answer`. The reducer sets `status: 'ACCEPTED'` and `acceptedAt`, adds the system chat message `chat.sysAccepted`, the customer SMS `sms.accepted` and an audit entry `job_accepted`. NO sets `DECLINED`, adds `chat.sysDeclined` and `sms.jobDeclined`. In API mode a YES is mirrored by `bridge.acceptJob`.
3. Still no job code. The artisan inbox shows `complete.waitPay` ("Waiting for the customer to pay. The job code is created after the payment.") instead of a "Finish job" button.
4. The customer pays from the Payments screen (`startPayment`). The sandbox provider settles after a delay. `scheduleSettle` in `store/index.tsx` runs `dispatch({ type: 'paySettle', id, ok, code: generateJobCode(), at, ids: ids(4) })`. The code is generated here, outside the reducer, because it uses `Math.random` (the reducer stays pure).
5. The reducer `paySettle` (success branch) writes the job code hash and the money split in one state update:

```ts
jobs: s.jobs.map((j) => (j.id === job.id
  ? { ...j, codeHash: hashCode(a.code), commissionRate: tx.rate, commission: tx.commission, payout: tx.payout } : j)),
sms: [ ...s.sms,
  sms(a.ids[1], job.customerPhone, 'sms.jobCode', { artisan: artisan.name, code: a.code }, a.at),
  sms(a.ids[2], artisan.phone, 'sms.paymentReceived', { ... }, a.at) ],
```

   The plain code appears only in the customer SMS (`sms.jobCode`); the job stores only the hash. The same step also marks the payment `succeeded`, adds a pending `Payout`, posts the ledger transaction, and adds the system chat message `chat.sysClosed`.
6. The artisan inbox now shows "Finish job" (`inbox.finish`) for this `ACCEPTED` job, because `j.codeHash` is non-null.

### Completing the job

1. The artisan presses "Finish job": `actions.go('artisanComplete', { jobId: j.id })`.
2. `ArtisanComplete()` selects the job:

```ts
const job =
  state.jobs.find((j) => j.id === state.ui.jobId && j.artisanId === actingId && j.status !== 'DECLINED' && j.status !== 'REQUESTED') ??
  state.jobs.find((j) => j.artisanId === actingId && j.status === 'ACCEPTED');
```

   Only the logged-in artisan's own jobs can be reached. Not logged in -> `<ArtisanLogin next="artisanComplete" />`. No job -> `complete.noJob` / `complete.errNone`. A job that is not completed and has no `codeHash` -> `complete.waitPay`.
3. The artisan types the code the customer gives them. Two inputs feed the same `code` state: the numeric text input (`inputMode="numeric"`, `maxLength={6}`, non-digits stripped) and the on-screen keypad (`press(d)` appends a digit while the length is below 6; the back key removes the last digit; the check key calls `submit`).
4. `submit` calls `actions.complete(job.id, code)`. On failure the error key is looked up in `ERRORS` and the field is cleared (`setCode('')`); on success the error is cleared.
5. In the store, `complete(jobId, entered)` returns `{ ok: false, reason: 'not_accepted' }` if the job is missing, runs `checkCompletion(job, entered)` and returns the failure without dispatching. On success it dispatches `{ type: 'complete', jobId, entered, at, ids: ids(4) }`, mirrors `bridge.completeJob` in API mode, and returns the result.
6. The reducer `complete` case re-runs `checkCompletion` (returns `s` unchanged if it fails). On success it:
   - sets the job to `COMPLETED`, `codeUsed: true`, `completedAt`;
   - finds the job's payout; if its status is `PENDING`, sets it to `PAID` with `paidAt` and posts the ledger lines `payoutPaidLines(payout.amount)` under the key `payout-paid:<payoutId>`;
   - adds the customer SMS `sms.jobCompleted` (artisan name and price) and, when the payout was paid, the artisan SMS `sms.payoutPaid`;
   - adds the audit entry `job_completed`, and, when paid, an audit entry of kind `payout` (`event: 'paid'`).
   If an operator has put the payout on hold (`HELD`) the job still completes, but the payout is not paid until an operator releases it.
7. `ArtisanComplete` now sees `job.status === 'COMPLETED'` and shows the success badge `complete.success` ("Job completed. The customer can now rate it.") and a button `complete.toCustomer` that opens Tracking for that job.
8. On Tracking the step moves to "Completed", the message becomes `tracking.msgCompleted` and the "Rate job" button appears. The `rate` action (not covered here) then moves the tracker to "Rated".

## File by file

### `apps/web/src/screens/Tracking.tsx`
- Purpose: customer's view of one job. Pure read of the state; all changes happen through `actions.go`.
- Without a job: empty screen with `tracking.none`.
- The tracker is an `<ol class="steps">` with `aria-current="step"` on the current step.
- The artisan's phone is a business rule, not decoration: the customer only gets contact details after payment (see Rules).

### `apps/web/src/screens/ArtisanComplete.tsx`
- Local state: `code` (string, up to 6 digits), `error` (an i18n key).
- `ERRORS` map: `wrong_code -> complete.errWrong`, `bad_format -> complete.errFormat`, `not_accepted -> complete.errNone`, `already_used -> complete.errUsed`.
- The error is shown in a `role="alert"` div; a keypad group is labelled `complete.keypad`; field label is `complete.codeField`; confirm buttons use `complete.confirm`; the delete key uses `complete.delete`.
- `autoComplete="one-time-code"` is set on the field.
- The same price breakdown is shown with the `done` flag after completion.

### `apps/web/src/domain/rules.ts` (job code part)
- `hashCode(code, salt = 'acbridge')`: salted FNV-1a over `"<salt>:<code>"`, returns 8 hex digits. The comment states it is simple and non-cryptographic: it only keeps the code out of storage in plain text.
- `generateJobCode(rand = Math.random)`: six digits, leading zeros kept; `rand` is injectable for tests.
- `checkCompletion(job, entered)` returns `{ ok: true }` or `{ ok: false, reason }`. The checks run in this order:
  1. `job.status !== 'ACCEPTED' || !job.codeHash` -> `not_accepted` (also true before payment);
  2. `job.codeUsed` -> `already_used`;
  3. not exactly six digits (`/^\d{6}$/`) -> `bad_format`;
  4. `hashCode(entered) !== job.codeHash` -> `wrong_code`.
  Because check 1 runs first and a completed job has status `COMPLETED`, `already_used` cannot normally be reached from the UI; a replay on a completed job gives `not_accepted`.

### `apps/web/src/store/reducer.ts`
- `paySettle`: see above. It is a no-op if the payment is missing or not `pending` (a repeated provider callback does nothing). The failed branch (`ok: false`) marks the payment `failed` and does not create a code.
- `complete`: see above. A second `complete` with the correct code is ignored (status is no longer `ACCEPTED`), so the payout cannot be paid twice and the audit log gets one `job_completed` entry.
- `answer`: see "From request to job code".

### `apps/web/src/store/index.tsx`
- `complete(jobId, entered): CompletionCheck`. `answer(jobId, accept): { expired: boolean }`.
- `scheduleSettle(paymentId, ok, delayMs)`: after the delay dispatches `paySettle` with a fresh `generateJobCode()`, and in API mode mirrors `bridge.payJob`.

### `apps/web/src/components/PriceBreakdown.tsx`
- Props `price`, `rate` (default `COMMISSION_RATE`), `done`. Used here with `rate={job.commissionRate}` so a paid job shows the rate that was applied.

### `apps/web/src/api/bridge.ts` (`completeJob`)
- Logs in as the artisan and calls `jobAction('start')` and `jobAction('confirm-completion')`; then logs in as the customer and calls `confirm-completion`. The header comment: the correct job code stands for both parties confirming.

## Data and state

- `Job` (`types.ts`): `status` (`REQUESTED | ACCEPTED | DECLINED | EXPIRED | COMPLETED`), `codeHash: string | null` (null until payment succeeds), `codeUsed: boolean`, `price`, `commissionRate?`, `commission?`, `payout?` (set at payment success), `acceptedAt?`, `completedAt?`, `remoteId?`.
- `State.payouts`: `Payout` rows with status `PENDING | HELD | PAID`; completion changes `PENDING -> PAID`.
- `State.ledger`: appended by `postTx`.
- `State.ratings`: determines the "Rated" step.
- `State.sms`, `State.audit`, `State.chats`: appended as listed above.
- Persistence: everything is part of `State` and saved to `localStorage`. The plain job code is never stored on the job; it exists only in the text of the customer SMS (`params.code`) in `State.sms`.

## Rules and edge cases

| Rule | Where |
|---|---|
| The job code exists only after the customer's payment succeeds | `paySettle` sets `codeHash`; `ArtisanComplete` and the inbox check `codeHash` |
| The code goes to the customer, not the artisan | `sms.jobCode` addressed to `job.customerPhone`; `sms.paymentReceived` for the artisan does not contain it |
| Only the artisan logged in as the job's artisan can reach the completion screen | `ArtisanComplete` job selection and login gate |
| Code is exactly 6 digits (`complete.errFormat`); wrong code is refused (`complete.errWrong`) and the field is cleared | `checkCompletion`, `ERRORS`, `submit` |
| Completion needs status `ACCEPTED` and a code hash (`complete.errNone`) | `checkCompletion` (`not_accepted`) |
| A code can complete a job once (`complete.errUsed` is defined, but see the note above) | `checkCompletion`, `codeUsed`, reducer ignoring repeats |
| A wrong code changes nothing: job still `ACCEPTED`, payout still `PENDING` | reducer `complete` returns `s` |
| Completion releases the payout unless it is `HELD` by an operator | reducer `complete` (`payout.status === 'PENDING'`) |
| The artisan's phone is hidden from the customer until a payment has succeeded | `Tracking` (`isPaid`) |
| The "Payments" button only appears for `ACCEPTED` or `COMPLETED` jobs | `Tracking` |
| Expired or declined jobs stop the tracker (no "Now" marker) and offer "Choose another" | `Tracking` |
| There is no attempt limit on wrong codes in the web app | not implemented |

## Tests

- `apps/web/src/__tests__/journey.test.ts` > "runs register, 2 vouches, request, choose, YES, PAY, wrong code, right code, payout, rate once": after YES `codeHash` is null and no `sms.jobCode` exists; after `paySettle` the code SMS goes to the customer's phone, contains the code, and the plain code is not in `JSON.stringify(s.jobs)`; a wrong code leaves the job `ACCEPTED` and the payout `PENDING`; the right code makes the job `COMPLETED` and the payout `PAID` with balanced ledger (`artisan_pending: 0`, `artisan_paid: 5700`); a replay is ignored (one `job_completed` audit entry); a second rating is ignored.
- `apps/web/src/__tests__/ui-flows.test.tsx` > "registers, gets vouched, is matched, agrees, is PAID, completes with the job code, gets the payout, is rated, and shows in the operator log": after YES the artisan sees "En attente du paiement du client"; before paying the tracker shows "Caché jusqu'au paiement"; after the 5 s sandbox delay "Paiement reçu" and a 6-digit code in the SMS; the artisan opens "Boîte travaux" then "Finir travail", a wrong code shows "Ce code n'est pas bon" and the job is not completed, the right code shows "Travail terminé. Le client peut maintenant le noter."; the payout SMS appears; the customer can then rate. Other tests in the file: "a declined payment shows the failure screen and can be retried; nothing is booked", "the operator can hold a pending payout with a reason, completion does not pay it, and release pays it".
- `apps/web/src/__tests__/rules.test.ts` > `job code`: "generates 6 digits and hashes without storing plain text"; "completes only on a matching, unused code".
- `apps/web/src/__tests__/ui-chat.test.tsx` and `ui-expiry.test.tsx` also exercise the tracker and the inbox ("Finir travail" after payment; "Choisir un autre" after expiry).

## Backend connection

- YES: `bridge.acceptJob` -> `POST /jobs/{id}/accept` then `confirm-terms`.
- Payment success: `bridge.payJob` (sandbox payment, see the payments README).
- Completion: `bridge.completeJob` -> artisan `start`, artisan `confirm-completion`, customer `confirm-completion` (the backend needs both sides to confirm).
- The 6-digit job code itself is a front-end mechanism: the bridge header states the backend has no code endpoint. The backend completion rule is "both sides confirm"; the web app collapses that into "the artisan typed the code the customer was given".
- The mirror needs `job.remoteId`; without it the step is skipped. A failure sets a notice and the local demo continues.

## Known limits and what changes in the production rebuild

- The job code is generated in the browser with `Math.random` and hashed with a 32-bit non-cryptographic FNV-1a with a fixed salt. With only a million possible codes the hash can be brute-forced; this protects against casual reading of `localStorage`, not against an attacker. There is also no limit on wrong attempts.
- The customer reads the code from the simulated SMS panel inside the same app, which is also where the artisan acts, so the demo cannot show real separation between the two parties' devices.
- Payment settles after a fixed sandbox delay (`scheduleSettle`); no real mobile-money provider is involved.
- The tracker and the completion step rely on local state. In production the job code should be created, stored hashed and verified on the server, with attempt limits and rate limiting, sent to the customer over a real SMS channel, and the payout release should be decided by the server and the real payment provider.
- The "Open as artisan" button on the customer tracker exists only to let one person demonstrate both sides.
