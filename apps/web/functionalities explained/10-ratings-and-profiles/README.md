# Ratings and artisan profile

After a job is completed, the customer can rate it once with 1 to 5 stars and an optional comment. The rating changes the artisan's trust score, which the customer sees on the artisan profile screen together with verification status, completed jobs, vouches, usual price range, what the artisan keeps after commission, and the list of ratings with comments.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/Rate.tsx` | Customer "Rate the job" screen: stars, comment, submit, thank-you and "already rated" states. |
| `apps/web/src/screens/ArtisanProfile.tsx` | Read-only profile: verified badge, trust score, completed jobs, vouches, price range, net range, ratings list. |
| `apps/web/src/components/StarRating.tsx` | Star widget: read-only (fractional value rounded) or five clickable radio buttons. |
| `apps/web/src/domain/rules.ts` | Pure rules: `checkRating`, `trustScore`, `trustFor`, `completedJobs`, `formatScore`, `NEUTRAL_RATING`, `VOUCH_BONUS`, `MAX_TRUST`. |
| `apps/web/src/store/reducer.ts` | The `rate` action: stores the rating, sends an SMS, writes audit entries `rating` and `trust`. |
| `apps/web/src/store/index.tsx` | `actions.rate`: validates with `checkRating`, dispatches, mirrors to the backend. |
| `apps/web/src/api/bridge.ts` | `review(job, score, comment)`: `POST /jobs/{id}/reviews` in API mode. |
| `apps/web/src/api/client.ts` | `api.review`. |
| `apps/web/src/domain/types.ts` | `Rating`, `AuditEntry`, `AuditKind`. |
| `apps/web/src/screens/Tracking.tsx` | Opens the Rate screen when the job is `COMPLETED` and not yet rated; links to the profile. |
| `apps/web/src/screens/Matches.tsx`, `ArtisanStatus.tsx` | Other entry points to the profile (`actions.go('profile', { profileId, back })`). |

## How it works

1. **Reaching the Rate screen.** Tracking shows the "Rate" button (`tracking.rate`) only when `job.status === 'COMPLETED'` and no rating exists for the job. It calls `actions.go('rate')`; `state.ui.jobId` already points at the job.
2. **Rendering.** `Rate()` finds the job by `state.ui.jobId`. `rated` is true when `state.ratings` has an entry for that job. Three displays:
   - `rated && !submitted`: the user opened the screen for a job that was rated earlier. An alert shows `rate.errDone`.
   - `rated && submitted`: just recorded. A badge shows `rate.thanks`.
   - otherwise: `StarRating` (input mode), a comment `textarea` (`maxLength` 1000, placeholder `rate.commentHint`), an error area and the submit button (`rate.submit`).
3. **Stars.** `StarRating` with `onChange` renders five `role="radio"` buttons inside a `role="radiogroup"`. The accessible name of each is `rate.stars` with `{n}` (for example "5 stars" / "5 étoiles"). Picking a star sets `score` and clears the error.
4. **Submit.** `submit()` calls `actions.rate(job.id, score, comment)`. The initial `score` is `0`, so pressing submit with no star returns `bad_score` and the screen shows `rate.errNone`. Reasons map through `ERRORS`: `bad_score` to `rate.errNone`, `already_rated` to `rate.errDone`, `not_completed` to `rate.errNotCompleted`. On success `submitted` becomes true.
5. **Store `rate`.** Runs `checkRating(job, score, state.ratings)` first. If not ok it returns the refusal and dispatches nothing. Otherwise it dispatches `{ type: 'rate', ratingId: uid('rating'), jobId, score, comment, at, ids: ids(3) }`, then in API mode mirrors with `bridge.review(job, score, comment)`.
6. **Reducer `rate`.** Re-validates with `checkRating` (the UI is not trusted), then:
   - appends `{ id, jobId, artisanId: job.artisanId, score, comment: comment.trim(), at }` to `state.ratings`;
   - appends SMS `sms.rated` to the artisan ("you received a rating of {score} out of 5");
   - computes the new trust score with `trustFor(artisan, s.vouches, ratings, s.artisans)` using the ratings list that already contains the new one, and formats it with `formatScore` (one decimal);
   - appends two audit entries: `audit(ids[1], 'rating', { artisan, score })` and `audit(ids[2], 'trust', { artisan, trust })`.
7. **Profile.** `ArtisanProfile()` finds the artisan by `state.ui.profileId`; the back target is `state.ui.back` (set by whoever navigated). It computes `isVerified`, `trustFor`, and the artisan's ratings newest first (`filter` then `slice().reverse()`). Everything is recomputed on every render from state, so a new rating shows immediately.

## File by file

### `apps/web/src/screens/Rate.tsx`
- Component `Rate()`, local state `score`, `comment`, `error`, `submitted`.
- No job in `state.ui.jobId` gives an empty screen with `rate.noJob`.
- After a rating exists, two buttons appear: profile (`tracking.profile`, navigates with `back: 'tracking'`) and home (`common.home`).
- The comment is trimmed only in the reducer. It is stored as plain text; the profile prints it in quotes.

### `apps/web/src/screens/ArtisanProfile.tsx`
- Shows, in this order: verified badge (`common.verified` or `common.notVerified`), trade (`tradeLabel`), neighbourhood, trust (stars plus `<strong data-testid="trust">` with `formatScore(trust)` and "/ 5"), completed jobs (`completedJobs(artisan, state.jobs)`), vouches, usual price range (`priceRangeLabel`), "artisan keeps after {rate}%" (`money.netRange` with `COMMISSION_RATE * 100`, values from `netRange(artisan)`), and the description in quotes if present.
- Vouch count: `'✔'` for seeded artisans (their vouches are baked into the seed average), otherwise `countValidVouches(...)`.
- Second card "Recent ratings" (`profile.ratings`): each rating shows stars, `score/5` and the comment; empty shows `profile.noRatings`. The list is not limited despite the "recent" label.
- Unknown id gives `profile.notFound`.
- Notice: the customer sees the net range the artisan keeps, which reveals the commission percentage. This is on the profile only; the Payments receipt shows no commission (see `09-payments`).

### `apps/web/src/components/StarRating.tsx`
- `StarRating({ value, onChange? })`.
- Without `onChange`: `<span role="img" aria-label="4.5 / 5">` with five stars; the filled count is `Math.round(value)`, so 4.5 shows 5 filled stars while the label keeps the exact number (`value.toFixed(1)`).
- With `onChange`: five buttons, `aria-checked={value === n}`, stars up to `value` look filled, group labelled `rate.instruction`.

### `apps/web/src/domain/rules.ts` (rating parts)

| Export | Behaviour |
|---|---|
| `NEUTRAL_RATING = 3.0`, `VOUCH_BONUS = 0.2`, `MAX_TRUST = 5.0` | Constants of the trust formula. |
| `checkRating(job, score, ratings)` | Returns `{ ok: true }` or `{ ok: false, reason }`. Order: `not_completed` (job missing or status not `COMPLETED`), `already_rated` (a rating exists for the job id), `bad_score` (not an integer between 1 and 5). |
| `trustScore(artisan, ratings, vouchCount)` | `jobs = baseJobs + ratings for this artisan`; `sum = baseRating * baseJobs + sum of scores`; `avg = jobs === 0 ? 3.0 : sum / jobs`; result `min(5, avg + 0.2 * vouchCount)`. |
| `trustFor(artisan, vouches, ratings, all)` | `trustScore` with `vouchCount = 0` for seeded artisans (`isSeed`) and `countValidVouches(...)` for others. |
| `completedJobs(artisan, jobs)` | `baseJobs` plus the number of `COMPLETED` jobs of this artisan. |
| `formatScore(n)` | `n.toFixed(1)`. |

Worked examples (from the tests): seed history 4.0 over 4 jobs, one new 5-star: `(16 + 5) / 5 = 4.2`. No history and 2 vouches: `3.0 + 0.4 = 3.4`. 4.9 history, a 5, 3 vouches: capped at `5`. In the UI journey test, a new artisan with one 5-star rating and 2 vouches shows `5.0` (`5 + 0.4`, capped).

### `apps/web/src/store/reducer.ts` (`rate`)
See How it works step 6. Ignored (state unchanged) if the job is missing or `checkRating` fails, so a second rating for the same job adds nothing and creates no audit entries.

### `apps/web/src/store/index.tsx` (`rate`)
Returns the `RatingCheck`. IDs: `ratingId = uid('rating')`, three event ids for SMS and the two audit entries.

### `apps/web/src/api/bridge.ts` (`review`)
`review(job, score, comment)`: returns if `job.remoteId` is absent; otherwise logs in as the customer and calls `api.review(token, job.remoteId, score, comment)`.

### `apps/web/src/api/client.ts` (`api.review`)
`POST /jobs/{jobId}/reviews` with body `{ rating, comment: comment || null }`.

## Data and state

| Type / field | Use |
|---|---|
| `Rating { id, jobId, artisanId, score, comment, at }` | Stored in `state.ratings`. |
| `Artisan.baseRating`, `baseJobs` | Seed history used by `trustScore`. New sign-ups start at `0` and `0`. |
| `Artisan.isSeed` | Decides whether vouches add to the score. |
| `State.vouches` | Feed `countValidVouches` for non-seed artisans. |
| `Job.status` | Must be `COMPLETED` to rate. |
| `State.sms`, `State.audit` | Receive `sms.rated`, and audit `rating` (`{ artisan, score }`) and `trust` (`{ artisan, trust }`). |

Persisted with the rest of the state in `localStorage` (the UI journey test reads `ratings` from storage). The trust score itself is never stored: it is derived each time. The audit `trust` entry is a snapshot string at the time of rating.

Audit rendering in the operator log: `audit.rating` is "Rating {score}/5 for {artisan}" and `audit.trust` is "Trust score updated: {artisan} now {trust}" (see `11-operator-panel-and-database-export`).

## Rules and edge cases

| Rule | Where | Message key |
|---|---|---|
| Only a `COMPLETED` job can be rated | `checkRating` (rules), re-run in the reducer | `rate.errNotCompleted` |
| One rating per job | `checkRating` `already_rated`; reducer ignores a second one | `rate.errDone` |
| Score is an integer 1-5 (no 0, 6, 3.5) | `checkRating` `bad_score` | `rate.errNone` |
| Comment is optional, trimmed, max 1000 chars in the UI | UI `maxLength`, reducer `trim()` | none |
| No rating without a payment | indirect: the job only becomes `COMPLETED` through the job code, which exists only after payment succeeded | none |
| Trust capped at 5.0; no history means 3.0 prior | `trustScore` | none |
| Trust list order on Matches: rounded to 1 decimal, then response time, then name | `rankArtisans` in `rules.ts` | none |

Edge cases:
- The "rated" check uses the job, not the customer, because the demo has a single hard-coded customer (`SEED_CUSTOMER`).
- Rating 5 stars on a 4.0 / 4-job history gives 4.2, so a single rating moves the score less for artisans with a long history; new artisans move quickly.
- `StarRating` read-only rounds to whole stars for the visual and shows the exact value in the label and the number.
- Ratings are not editable or deletable.

## Tests

| File | Tests |
|---|---|
| `apps/web/src/__tests__/rules.test.ts` | "accepts one rating per completed job with an integer 1-5"; "rejects a rating for a job that is not completed"; "weights the average by job count and adds 0.2 per vouch, capped at 5.0"; "uses a neutral prior with no history"; "returns only verified artisans of the asked trade, trust desc, then response time asc, max five" (ranking uses `trustFor`). |
| `apps/web/src/__tests__/journey.test.ts` | "runs register, 2 vouches, request, choose, YES, PAY, wrong code, right code, payout, rate once": a 5-star rating is stored, a second `rate` for the same job (score 1) is ignored (`ratings` length 1), and an audit entry of kind `trust` exists. |
| `apps/web/src/__tests__/ui-flows.test.tsx` | "registers, gets vouched, ... is rated, and shows in the operator log": clicks the "5 étoiles" radio, types a comment, sees `rate.thanks`, profile `data-testid="trust"` equals `5.0`, the comment is shown, operator log shows "Note 5/5 pour Joel", language switch keeps `ratings` length 1 in storage. |

## Backend connection

Only in API mode. `bridge.review` calls `POST /jobs/{job_id}/reviews` as the customer (role `CUSTOMER`). The backend (`backend/app/services/reputation_service.py`, `create_review`) mirrors the same rules: only the job's customer may review; the job must be `COMPLETED` ("Reviews are only accepted after both parties have confirmed completion"); `UNIQUE(job_id, reviewer_id)` makes a second review a conflict ("You have already reviewed this job"). The backend reputation is a separate calculation exposed at `GET /artisans/{id}/reputation`; the web app does not read it, it computes `trustFor` locally. If the mirror call fails, the local rating stays and a notice is shown.

## Known limits and what changes in the production rebuild

- The trust formula (weighted average plus 0.2 per vouch, cap 5) is the demo's own and is computed in the browser; production should read the server's reputation (`/artisans/{id}/reputation`) so the number is the same everywhere.
- Ratings are stored in `localStorage` and could be edited by the user; production stores them server side with the uniqueness constraint.
- Single hard-coded customer; production needs the real customer identity on each rating.
- Comments are not moderated or length-checked beyond 1000 characters in the form.
- The profile prints the artisan's net range, which discloses the commission rate to customers; a product decision to revisit.
- Seeded artisans have fixed `baseRating`/`baseJobs`; real history replaces them.
