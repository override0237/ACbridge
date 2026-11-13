# Job offers and expiry (the artisan inbox)

When a customer confirms an artisan, the artisan gets an offer in the job inbox with a deadline and a countdown. The artisan answers YES or NO. If the artisan does not accept in time, the offer is nullified: 1 hour for an urgent (Today) request, 1 day for This week, 5 days for Not urgent.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/ArtisanInbox.tsx` | The inbox: one card per job with deadline, countdown, price breakdown, YES / NO, chat and finish buttons; shows the "expired" state and the "too late" message. |
| `apps/web/src/domain/offers.ts` | Pure time rules: `OFFER_TTL_MS`, `offerDeadline`, `isOfferExpired`, `timeLeftMs`, `formatLeft`. |
| `apps/web/src/store/reducer.ts` | `expireStale` (the one function that expires offers), the `expire` action and the `answer` action (which calls `expireStale` first). |
| `apps/web/src/store/index.tsx` | `actions.answer` (returns `{ expired }`) and the effect that sweeps every 30 seconds. |
| `apps/web/src/screens/CustomerRequest.tsx` | Shows the TTL hint (`request.ttlHint`) under the urgency choice. |
| `backend/app/services/job_service.py` | Backend mirror: `offer_ttl`, `offer_expires_at`, `offer_expired`, `expire_if_stale`, `sweep_expired_offers`. |
| `backend/app/config.py` | `offer_ttl_hours_today = 1`, `offer_ttl_hours_this_week = 24`, `offer_ttl_hours_not_urgent = 120`. |
| `backend/tests/test_offer_expiry.py` | Backend tests of the same rules. |

## How it works

1. The customer picks an urgency on `CustomerRequest.tsx` (`today`, `week` or `later`, default `today`). A line `request.ttlHint` explains the windows: "The artisan must accept within 1 hour (Today), 1 day (This week) or 5 days (Not urgent), or the offer is cancelled."
2. When the customer confirms an artisan (section 05), the reducer `choose` action creates a `Job` with `status: 'REQUESTED'` and `createdAt = at`. The deadline is derived, not stored: `offerDeadline(job, request) = createdAt + OFFER_TTL_MS[request.urgency]` (`later` if the request is missing).
3. `ArtisanInbox` lists the logged-in artisan's jobs, newest first. For each job it computes `left = timeLeftMs(j, req, Date.now())`. For a `REQUESTED` job it shows a `role="timer"` line: `inbox.deadline` (local date and time) and `inbox.left` with `formatLeft(left)`. A `setInterval` of 30 s forces a re-render so the countdown moves.
4. The artisan presses YES or NO. Both call `actions.answer(j.id, accept)`; if the result has `expired: true` the card shows `inbox.expiredNow` ("Too late: this offer has expired and was cancelled.").
5. In `store/index.tsx`, `answer(jobId, accept)` first checks `isOfferExpired(job, request, Date.now())`. If true it dispatches `{ type: 'expire', at, stamp }` and returns `{ expired: true }` without dispatching `answer`. This is the "late YES lapses" rule.
6. Otherwise it dispatches `{ type: 'answer', jobId, accept, at, ids: ids(3) }` and returns `{ expired: false }`. For a YES in API mode it also mirrors `bridge.acceptJob`.
7. The reducer `answer` case begins with `s = expireStale(s, a.at, a.ids[0])`, so even a direct dispatch of a late answer lapses instead of being answered. Then it returns early unless the job is still `REQUESTED`. NO sets `DECLINED` and adds `chat.sysDeclined` plus `sms.jobDeclined`. YES sets `ACCEPTED`, `acceptedAt`, adds `chat.sysAccepted`, `sms.accepted` and an audit `job_accepted` (the job code is not created here; see section 08).
8. Background sweep: a `useEffect` in `StoreProvider` runs `sweep()` once on load and then every `30_000` ms. `sweep` checks whether any job satisfies `isOfferExpired(...)` and, if so, dispatches `{ type: 'expire', at: now(), stamp: uid('exp') }`.
9. `expireStale(s, at, stamp)` in the reducer:
   - `overdue = s.jobs.filter(j => isOfferExpired(j, request, nowMs))`; if none it returns the same state object.
   - For each overdue job it adds: an SMS to the customer (`sms.offerExpired`, param `artisan`), an SMS to the artisan (`sms.offerLost`, param `customer`), a system chat message `chat.sysExpired`, and an audit entry of kind `expiry` with the urgency.
   - Sets those jobs' `status` to `'EXPIRED'`. Ids are built as `${stamp}-${job.id}-c|a|m|x` so they are unique per sweep.
10. After the job is `EXPIRED`: the inbox card shows the `inbox.expired` badge and no YES/NO or chat button; Tracking shows `tracking.msgExpired` and the "Choose another" button (`tracking.again`); chat is refused (`isChatOpen` needs `REQUESTED` or `ACCEPTED`) and payments are refused (`checkPayStart` needs `ACCEPTED`).

## File by file

### `apps/web/src/domain/offers.ts`
- `OFFER_TTL_MS: Record<Urgency, number> = { today: 1h, week: 24h, later: 5 days }`.
- `offerDeadline(job, request)`: `new Date(job.createdAt).getTime() + OFFER_TTL_MS[request?.urgency ?? 'later']`.
- `isOfferExpired(job, request, nowMs)`: `job.status === 'REQUESTED' && nowMs > offerDeadline(job, request)`. The comparison is strict, so at exactly the deadline the offer is still valid.
- `timeLeftMs(job, request, nowMs)`: `Math.max(0, deadline - nowMs)`, never negative.
- `formatLeft(ms)`: `"59 min"` below one hour (rounded up with `Math.ceil`), `"5 h 20 min"` below one day, `"2 d 3 h"` otherwise. Language-neutral on purpose.

### `apps/web/src/store/reducer.ts`
- `expireStale`: described above. It is the single place where a job becomes `EXPIRED`. It never touches payments or payouts (an expired job cannot have either, since payment needs an accepted job).
- `expire` action: `return expireStale(s, a.at, a.stamp)`.
- `answer` action: see step 7. A repeated answer on a job that is no longer `REQUESTED` returns the state unchanged.
- The action type: `{ type: 'expire'; at: string; stamp: string }`. The `at` timestamp is passed in so tests can control time.

### `apps/web/src/store/index.tsx`
- `answer(jobId, accept): { expired: boolean }`: see steps 5-6.
- Sweep effect: runs on mount (so an offer that lapsed while the page was closed is nullified on reload) and every 30 s; the interval is cleared on unmount.
- The effect and `answer` read the latest state through a `ref`, not a stale closure.

### `apps/web/src/screens/ArtisanInbox.tsx`
- If nobody is logged in it renders `<ArtisanLogin next="artisanInbox" />`. Only jobs where `artisanId === me.id` are listed.
- Per job it shows: customer name (`inbox.from`), trade and urgency (`urgency.today|week|later`), the request description in quotes, the deadline line (REQUESTED only), `inbox.expired` badge (EXPIRED), the late alert (`late === j.id`, local state), a `PriceBreakdown` for every status except `DECLINED` and `EXPIRED`, the chat button (if `isChatOpen`), YES/NO (REQUESTED), accepted state with either "Finish job" (when `j.codeHash` exists) or `complete.waitPay`, and badges for declined and completed jobs.
- The tick interval (30 s) is separate from the store's sweep; it only re-renders the countdown.

### `apps/web/src/screens/CustomerRequest.tsx` (ttl hint only)
- A `<p className="muted small">⏱️ {t('request.ttlHint')}</p>` below the urgency radios. No logic.

## Data and state

- Reads: `Job.status`, `Job.createdAt`, `ServiceRequest.urgency` (`'today' | 'week' | 'later'`), `State.jobs`, `State.requests`.
- Writes by `expireStale`: `jobs[].status = 'EXPIRED'`, new `sms`, `chats`, `audit` entries.
- `JobStatus = 'REQUESTED' | 'ACCEPTED' | 'DECLINED' | 'EXPIRED' | 'COMPLETED'`.
- The deadline is never persisted; it is recomputed from `createdAt` and the urgency, so a reload does not lose or reset it. Everything else persists in `localStorage` with the state.

## Rules and edge cases

| Rule | Where |
|---|---|
| Windows: Today 1 h, This week 1 day, Not urgent 5 days | `OFFER_TTL_MS` |
| Only an unanswered `REQUESTED` offer can expire; `ACCEPTED`, `DECLINED`, `COMPLETED` and `EXPIRED` never do | `isOfferExpired` |
| A YES after the deadline does not accept; the offer lapses and the artisan sees `inbox.expiredNow` | `actions.answer` (UI result) and `answer` reducer (`expireStale` first) |
| An on-time YES still works, and an accepted job is never expired later, even after 30 days | `isOfferExpired` requires `REQUESTED` |
| Expired offers are swept on load and every 30 s without any user action | store effect |
| Everyone is told: customer SMS `sms.offerExpired`, artisan SMS `sms.offerLost`, chat message `chat.sysExpired`, audit kind `expiry` | `expireStale` |
| Sweeping again changes nothing (same state object returned) | `expireStale` early return |
| Chat and payment are closed on an expired offer | `isChatOpen`; `checkPayStart` (job must be `ACCEPTED`) |
| Missing request defaults to the 5-day window | `offerDeadline` |

i18n keys: `inbox.deadline`, `inbox.left`, `inbox.expired`, `inbox.expiredNow`, `tracking.msgExpired`, `chat.sysExpired`, `request.ttlHint`, `sms.offerExpired`, `sms.offerLost`.

## Tests

- `apps/web/src/__tests__/offers.test.ts`
  - "how long an artisan has to accept" > "is 1 hour (urgent), 1 day (this week) and 5 days (not urgent)"; the parametrised "still open just inside the window, nullified just after it" for `today` (59/61 min), `week` (23/25 h), `later` (4/6 days); "an answered offer never expires"; "formats the time left briefly".
  - "the reducer nullifies unanswered offers" > "expires an urgent offer after an hour: job EXPIRED, chat closed, both sides told, audit entry" (also checks a second sweep returns the same object); "a late YES does not accept: the offer lapses instead" (no `sms.accepted`, no payouts); "an on-time YES still works, and an accepted job is never expired later"; "a not-urgent offer survives 4 days and lapses after 5"; "chat and payments are closed on an expired offer".
- `apps/web/src/__tests__/ui-expiry.test.tsx` > "offers the artisan does not accept in time are nullified":
  - "an urgent offer lapses after one hour: the artisan sees it expired, the customer is told to choose another" (timer text with deadline and 59 min / 1 h 0 min, then after 61 minutes there is no YES button, "Offre expirée" is shown, both SMS appear, the customer sees "Choisir un autre", and chat and payments buttons are gone).
  - "a not-urgent offer is still open after two days" (YES still accepted).
  - The shared helper also asserts that the TTL hint ("dans l'heure (Aujourd'hui)") is shown on the request form.
- `backend/tests/test_offer_expiry.py`: `test_offer_is_valid_inside_the_window_and_cancelled_after_it` (parametrised TODAY/THIS_WEEK/NOT_URGENT), `test_just_reading_an_overdue_offer_nullifies_it`, `test_an_offer_the_artisan_already_accepted_never_expires`, `test_default_urgency_is_not_urgent_and_the_deadline_is_five_days`, `test_invalid_urgency_is_rejected_and_the_admin_sweep_expires_overdue_offers`.

## Backend connection

- The windows are the same as the backend settings `offer_ttl_hours_today = 1`, `offer_ttl_hours_this_week = 24`, `offer_ttl_hours_not_urgent = 120` (5 days). `job_service.offer_ttl(job)` picks one by `job.request.urgency`, with NOT_URGENT as the fallback. The web bridge maps urgency as `today -> TODAY`, `week -> THIS_WEEK`, `later -> NOT_URGENT` in `bridge.createRequest`.
- `offer_expires_at(job)` is `None` once the job is no longer `REQUESTED` or the artisan has agreed; `offer_expired` is true after the deadline.
- `expire_if_stale(db, job)` moves the job to `CANCELLED` with a `JOB_OFFER_EXPIRED` event (urgency and hours in the metadata). It runs lazily whenever a job is read, and inside `accept_job` (the accept then fails with a 409 "expired" error). `sweep_expired_offers(db)` expires all stale offers and is exposed as `POST /admin/expire-offers` (admin only, returns `{ "expired": n }`).
- Differences: the backend calls the final state `CANCELLED`, the web calls it `EXPIRED`. The backend only counts offers where `artisan_agreed` is false.
- In API mode the web app does not call the sweep endpoint; the local sweep and the backend rule act independently. `bridge.acceptJob` is only called for a YES that passed the local deadline check.

## Known limits and what changes in the production rebuild

- Expiry in the demo depends on the browser being open (30 s interval, plus a check on load). Nothing runs while the page is closed; the offer is only nullified the next time the app loads or the artisan taps YES/NO.
- The deadline uses the device clock (`Date.now()`), which a user can change. The backend uses server time.
- The "SMS" messages are shown in an in-app simulated SMS panel; nothing is sent.
- The local `EXPIRED` status is not synchronised to the backend job; a production version would let the server be the only authority (scheduled sweep on the server, push to the clients) and show the same state to both sides.
- The countdown re-renders every 30 s, so its display can be up to 30 s behind.
