# Matching and ranking (the match results screen)

After a customer submits a request, the app shows up to five verified artisans of the requested trade, best first. Each card shows a name, trade, star rating with a one-decimal trust score, number of completed jobs, the artisan's usual price range, and what the artisan would keep after the platform commission. Tapping "Choose" opens an inline confirm step with the full price breakdown; confirming creates the job and moves to the tracking screen.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/Matches.tsx` | The screen. Ranks artisans with `rankArtisans`, renders the cards and the per-card confirm step, calls `actions.choose`. |
| `apps/web/src/domain/rules.ts` | Pure rules: `rankArtisans`, `trustScore`, `trustFor`, `completedJobs`, `priceRangeLabel`, `formatScore`, constants `NEUTRAL_RATING`, `VOUCH_BONUS`, `MAX_TRUST`. Also holds `isVerified` / `countValidVouches` that decide who is eligible. |
| `apps/web/src/domain/money.ts` | `computeCommission`, `agreedPrice`, `netRange`: commission maths and the simulated agreed price. |
| `apps/web/src/components/StarRating.tsx` | Read-only star display (and the input variant used on the rating screen). |
| `apps/web/src/components/PriceBreakdown.tsx` | The price / commission / artisan-receives box shown in the confirm step. |
| `apps/web/src/store/index.tsx` | `actions.choose(artisanId)`: builds ids and the price, dispatches `choose`, mirrors to the backend in API mode. |
| `apps/web/src/store/reducer.ts` | The `choose` reducer action: creates the `REQUESTED` job, sends the "new job" SMS, navigates to `tracking`. |
| `apps/web/src/config.ts` | `MAX_MATCHES` (5), `COMMISSION_RATE` (0.05) and the 3%-7% band constants. |
| `apps/web/src/data/seed.ts` | The nine seeded artisans (ratings, job counts, response times, price ranges) that the ranking runs on. |
| `apps/web/src/domain/trades.ts` | `sameTrade` (used by `rankArtisans` to compare trades). Not in the assigned list but called by the ranking. |

## How it works

1. The customer submits the request form (`CustomerRequest.tsx` -> `actions.submitRequest`). The reducer `request` action stores the request, sets `ui.requestId` and navigates to `matches`.
2. `Matches()` reads `state.requests.find(r => r.id === state.ui.requestId)` and takes its `trade` (empty string if missing).
3. A `useMemo` calls `rankArtisans(state.artisans, state.vouches, state.ratings, state.jobs, trade)`. It is recomputed only when one of those inputs changes. Everything is local state, so there is no network wait.
4. Inside `rankArtisans`:
   - `filter`: keep artisans where `sameTrade(a.trade, trade)` and `isVerified(a, vouches, artisans)` are both true. So a pending or rejected artisan never appears.
   - `map`: attach `trust = trustFor(...)` and `jobs = completedJobs(a, jobs)`.
   - `sort`: trust descending compared at one decimal (`Math.round(trust * 10)`); ties by `avgResponseMin` ascending; remaining ties by `name.localeCompare`.
   - `slice(0, limit)` with `limit = MAX_MATCHES` (5).
5. The screen shows `matches.none` if the list is empty. Otherwise, for each ranked row it renders a `Card`; the first card is highlighted and gets the "best match" badge (`matches.best`).
6. Each card computes `netRange(artisan)` (what the artisan keeps at both ends of the range after the commission) and shows `priceRangeLabel(artisan, currency, locale)`.
7. "Choose" sets local state `confirming = artisan.id`. The card switches to the confirm group: title `matches.confirmTitle`, then `<PriceBreakdown price={agreedPrice(artisan)} />`, then Confirm and Cancel buttons. Only one card can be in the confirm state at a time because `confirming` holds one id.
8. Cancel sets `confirming` back to `null`. Confirm calls `actions.choose(artisan.id)`.
9. In `store/index.tsx`, `choose` reads `ui.requestId`, creates `jobId = uid('job')`, finds the artisan, and dispatches
   `{ type: 'choose', jobId, requestId, artisanId, price: agreedPrice(chosen), at: now(), ids: ids(1) }`.
10. The reducer `choose` case creates the job:

```ts
const job: Job = {
  id: a.jobId, requestId: req.id, artisanId: artisan.id, customerPhone: req.customerPhone,
  status: 'REQUESTED', codeHash: null, codeUsed: false, price: a.price, priceSource: 'estimate', createdAt: a.at,
};
```

    It also appends an SMS (`sms.jobRequest`) addressed to the artisan, sets `ui.jobId` and navigates to `tracking`.
11. In API mode a `mirror` step then calls `bridge.chooseArtisan(req, artisan, agreedPrice(artisan))` and stores the returned backend job id as `job.remoteId` via `patchJob`.

## File by file

### `apps/web/src/screens/Matches.tsx`
- Purpose: render the ranked list and the confirm step. It holds one piece of local state, `confirming: string | null`.
- Reads from the store: `state.requests`, `state.artisans`, `state.vouches`, `state.ratings`, `state.jobs`, `state.ui.requestId`, `state.lang`.
- `ratePercent = computeCommission(0).ratePercent` reads the configured rate (5) for the texts `matches.fee` and `money.netRange`.
- The card shows: `artisan.name`, `tradeLabel`, a verified badge (`common.verified`), `<StarRating value={trust} />`, `formatScore(trust)`, `common.jobs` with `n = jobs`, `matches.price` + range, and `money.netRange` with the net min and max.
- "Profile" button: `actions.go('profile', { profileId: artisan.id, back: 'matches' })`.
- The screen is wrapped in `<Screen ... back="customerRequest">`.
- Edge case: if the request is missing, `trade` is `''`, nothing matches and `matches.none` is shown.
- The shown commission figure is a notice: `matches.fee` says the commission is taken from the artisan when the job code is confirmed and the customer pays only the agreed price.

### `apps/web/src/domain/rules.ts` (parts used here)
- `NEUTRAL_RATING = 3.0`: average used when an artisan has no rating history at all.
- `VOUCH_BONUS = 0.2`: trust added per valid vouch.
- `MAX_TRUST = 5.0`: cap.
- `trustScore(a, ratings, vouchCount)`:

```ts
const mine = ratings.filter((r) => r.artisanId === a.id);
const jobs = a.baseJobs + mine.length;
const sum = a.baseRating * a.baseJobs + mine.reduce((s, r) => s + r.score, 0);
const avg = jobs === 0 ? NEUTRAL_RATING : sum / jobs;
return Math.min(MAX_TRUST, avg + VOUCH_BONUS * vouchCount);
```

  The seed history counts as `baseJobs` jobs at average `baseRating`; each new rating counts as one job. Example: `baseRating 4, baseJobs 4` plus one 5-star rating = `(16 + 5) / 5 = 4.2`.
- `trustFor(a, vouches, ratings, all)`: `trustScore(a, ratings, a.isSeed ? 0 : countValidVouches(a, vouches, all))`. Seeded artisans pass 0 vouches because their vouches are "already baked into" the seed average. Non-seed artisans get +0.2 per valid vouch (so a new artisan with no jobs and 2 vouches shows 3.0 + 0.4 = 3.4).
- `completedJobs(a, jobs)`: `a.baseJobs` plus the number of jobs for this artisan whose status is `COMPLETED`. Shown as "N jobs".
- `rankArtisans(artisans, vouches, ratings, jobs, trade, limit = MAX_MATCHES)`: returns `Ranked[]` = `{ artisan, trust, jobs }`. See "How it works" step 4.
- `priceRangeLabel(a, currency, locale)`: `"3 000 – 8 000 FCFA"` style string using `toLocaleString(locale)` (the screen passes `fr-FR` or `en-US`). Always a range, never a single number.
- `formatScore(n)`: `n.toFixed(1)`.
- `isVerified` (used by the filter): false if `rejected`; true if `seedVerified` or `operatorApproved`; otherwise true when `countValidVouches >= VOUCHES_REQUIRED` (2). A cycle guard (`seen` set) stops two artisans from verifying each other in a loop.

### `apps/web/src/domain/money.ts`
- `computeCommission(price, rate = COMMISSION_RATE)` returns `{ price, rate, ratePercent, commission, payout }`. `commission = Math.round(price * rate)`; `payout = price - commission`; `ratePercent = Math.round(rate * 1000) / 10`. Throws `RangeError` if the rate is outside 3%-7% (with a 1e-9 tolerance) or the price is negative or not finite.
- `agreedPrice(a)`: `Math.round((priceMin + priceMax) / 2 / 100) * 100`. This is the simulated opening price: the middle of the artisan's range rounded to 100 FCFA. Example: Grace 3000-8000 gives 5500.
- `netRange(a, rate)`: `{ min: payout at priceMin, max: payout at priceMax }`. Example: Grace gives `{ min: 2850, max: 7600 }`.

### `apps/web/src/components/StarRating.tsx`
- Without `onChange`: a read-only `span` with `role="img"` and `aria-label` `"4.8 / 5"`. It draws five stars, filled while `n <= Math.round(value)`. So 4.4 shows four filled stars and 4.5 shows five (rounded), while the number next to it shows one decimal.
- With `onChange`: a radio group of five buttons (used by the rate screen, `rate.stars`, `rate.instruction`).

### `apps/web/src/components/PriceBreakdown.tsx`
- Props: `price`, `rate = COMMISSION_RATE`, `done?`. Calls `computeCommission` and renders three rows: `money.price`, `money.commission` (with `{rate}`) as a negative amount, `money.payout` (with a check mark when `done`), plus the note `money.note` ("The commission is taken from the artisan, not from the customer").
- It uses `money()` from `i18n/format` to format numbers per language.

### `apps/web/src/store/index.tsx` (`choose`)
- Does nothing if there is no `ui.requestId` or the artisan is not found. Otherwise dispatches `choose` with `price: agreedPrice(chosen)`. The price is computed here (and again for the backend mirror), never typed by the user.

### `apps/web/src/store/reducer.ts` (`choose`)
- Returns the same state if the artisan or request is not found. Creates one job (`REQUESTED`, `codeHash: null`, `codeUsed: false`, `priceSource: 'estimate'`). It does not check whether a job already exists for this request, and it does not re-check that the artisan is verified or of the right trade (the screen only offers ranked artisans).

### `apps/web/src/config.ts`
- `COMMISSION_RATE = 0.05`, `MIN_COMMISSION_RATE = 0.03`, `MAX_COMMISSION_RATE = 0.07`. The comment records the reasoning: typical jobs are 3,000-8,000 FCFA, so 5% is 150-400 FCFA; mobile-money cash-out costs the artisan about 1-2% more; going lower leaves too little after processing costs.
- `MAX_MATCHES = 5`, `VOUCHES_REQUIRED = 2`.

### `apps/web/src/data/seed.ts`
- `SEED_ARTISANS` (nine people, all `isSeed: true`). Facts the ranking depends on:

| id | Name | Trade | baseRating | baseJobs | avgResponseMin | Range | Verified |
|---|---|---|---|---|---|---|---|
| seed-1 | Grace | plumbing | 4.8 | 24 | 8 | 3000-8000 | yes |
| seed-2 | Paul | electrical | 4.6 | 31 | 15 | 5000-12000 | yes |
| seed-3 | Esther | electrical | 4.3 | 12 | 12 | 4000-9000 | yes |
| seed-4 | Peter | electrical | 3.9 | 9 | 25 | 3500-8000 | yes |
| seed-5 | Samuel | electrical | 0 | 0 | 30 | 3000-7000 | no (pending) |
| seed-6 | Rose | tailoring | 4.7 | 40 | 20 | 2000-15000 | yes |
| seed-7 | Daniel | carpentry | 4.5 | 18 | 18 | 5000-20000 | yes |
| seed-8 | Fabrice | mechanics | 4.2 | 22 | 30 | 3000-25000 | yes |
| seed-9 | Blaise | plumbing | 4.1 | 10 | 14 | 2500-7000 | yes |

- Samuel is deliberately unverified: he never appears in matches until the operator approves him. `SEED_CUSTOMER` is Mary (`+237690000030`).
- New artisans registered in the app start with `baseRating 0`, `baseJobs 0`, `avgResponseMin 20`, `priceMin 3000`, `priceMax 8000` (set in `registerArtisan`).

## Data and state

Reads (all from `State`): `artisans`, `vouches`, `ratings`, `jobs`, `requests`, `ui.requestId`, `lang`.

Types used (`apps/web/src/domain/types.ts`):
- `Artisan`: `trade`, `baseRating`, `baseJobs`, `avgResponseMin`, `priceMin`, `priceMax`, `seedVerified`, `operatorApproved?`, `rejected?`, `isSeed`.
- `Ranked` (exported from `rules.ts`): `{ artisan: Artisan; trust: number; jobs: number }`. Not stored.

Writes (only on Confirm): one `Job` appended to `state.jobs` (`status: 'REQUESTED'`, `price` = `agreedPrice`, `priceSource: 'estimate'`), one `SmsMessage` (`sms.jobRequest`), and `ui.jobId` / `ui.screen`. The whole state is saved to `localStorage` by `saveState` on every change. The ranking result itself is derived on every render and never stored. `confirming` is component state only and is lost on navigation.

## Rules and edge cases

| Rule | Where enforced |
|---|---|
| Only verified artisans are listed (seed-verified, operator-approved, or 2 valid vouches; never rejected) | `rankArtisans` -> `isVerified` in `rules.ts` |
| Only artisans of the requested trade (compared with `sameTrade`, i.e. normalised text, so French and English names for a catalogue trade match) | `rankArtisans` |
| Order: trust desc at one decimal, then faster average response, then name | `rankArtisans` sort |
| At most 5 results | `MAX_MATCHES` in `config.ts`, applied by `slice` |
| Trust formula: job-weighted average + 0.2 per valid vouch (non-seed only), capped at 5.0, neutral 3.0 with no history | `trustScore` / `trustFor` |
| The price range is always shown as a range, never a single price | `priceRangeLabel` |
| Commission rate must be 3%-7%; the app uses 5% | `computeCommission` throws `RangeError` outside the band; `COMMISSION_RATE` in `config.ts` |
| Commission is whole francs, taken from the artisan side; `price = commission + payout` | `computeCommission` |
| The customer confirms before a job exists | `confirming` state in `Matches.tsx`; the `choose` action is only called from the Confirm button |
| The opening price is not typed by the user | `agreedPrice` computed in the store |

User-facing messages (i18n keys): `matches.title`, `matches.instruction`, `matches.request`, `matches.fee`, `matches.best`, `matches.price`, `matches.none` (empty list), `matches.choose`, `matches.profile`, `matches.confirmTitle`, `matches.confirmOk`, `money.title`, `money.price`, `money.commission`, `money.payout`, `money.note`, `money.netRange`, `common.verified`, `common.jobs`, `common.cancel`.

## Tests

- `apps/web/src/__tests__/rules.test.ts`
  - `ranking` > "returns only verified artisans of the asked trade, trust desc, then response time asc, max five": plumbing gives Grace then Blaise; electrical gives Paul, Esther, Peter (Samuel excluded); an unknown trade gives `[]`; with equal trust the faster Esther is first; with extra artisans the list is capped at 5.
  - `trust score` > "weights the average by job count and adds 0.2 per vouch, capped at 5.0" and "uses a neutral prior with no history" (3.0 + 2 vouches = 3.4).
  - `verification` tests cover the `isVerified` / vouch rules the filter relies on.
- `apps/web/src/__tests__/security-money.test.ts` > `commission`:
  - "the chosen platform rate is inside 3%-7% (inclusive)" (and equals 0.05).
  - "takes the commission from the artisan: price = commission + payout, whole francs" (5500 -> 275 / 5225).
  - "accepts 3% and 7% but refuses anything outside the band" (0.02 and 0.08 throw `RangeError`; negative price throws).
  - "derives the simulated agreed price and net range from the artisan range" (Grace: 5500; net 2850-7600).
- `apps/web/src/__tests__/ui-flows.test.tsx` > "registers, gets vouched, is matched, agrees, is PAID, ..." (match part): after a new plumber is verified, a Plombier request shows exactly 3 cards, the first has the "Meilleur choix" badge, no Paul/Rose/Daniel card appears, the text "Commission de la plateforme : 5%" is shown, and pressing Choose reveals "Commission de la plateforme (5%)" before Confirm. The other tests in that file cover free-text trades ("lets a customer ask for any artisan...": an unserved trade shows the empty message).
- `apps/web/src/__tests__/journey.test.ts` (ranking part): before the second vouch a new artisan is not in `rankArtisans`; after it the order is Grace, Blaise, Joel.

## Backend connection

- Ranking is NOT mirrored. The backend has its own deterministic two-stage matcher (`backend/app/services/matching_service.py`, endpoint `GET /matches/{request_id}`): hard eligibility filters, then the score `M(a) = 0.35*S + 0.25*L + 0.15*A + 0.15*R + 0.10*P` (skill, location, availability, work history, price). The web app does not use that formula; it uses the simpler trust-based ranking above.
- In API mode `bridge.createRequest` (`apps/web/src/api/bridge.ts`) creates the backend service request, calls `api.matches` and only uses the result to link local artisans to backend ids by matching `full_name` prefixes (`remoteId`).
- On Confirm, `bridge.chooseArtisan(req, artisan, price)` calls `api.createJob` (`POST /jobs`) with the agreed price; the backend `create_job` re-checks eligibility, requires `proposed_price` for fixed-price requests and records `proposed_by = CUSTOMER`. The backend commission uses its own `payment_service.compute_commission`. If either the request or the artisan has no `remoteId` (for example a free-text trade that is not in the backend skill catalogue), the mirror silently returns `null` and the job stays local.
- Mirror failures show a notice but do not stop the local demo.

## Known limits and what changes in the production rebuild

- The ranking uses only demo-seeded history (`baseRating`, `baseJobs`, `avgResponseMin`). There is no location, availability or price-fit scoring, no distance, and a single neighbourhood (`NEIGHBOURHOOD` in config).
- `avgResponseMin` is a fixed seed number (20 for new artisans); it is not measured from real response times.
- The "agreed price" at choose time is simulated as the middle of the artisan's declared range. The real price is later set by the artisan in the chat (see section 06).
- Trust ties are broken by name with `localeCompare`; the display rounds with `toFixed(1)` while the sort uses `Math.round(x*10)`.
- The reducer does not check for an existing job on the same request, and it trusts the UI to offer only ranked artisans. A production version should re-validate eligibility and uniqueness on the server (the backend already does).
- A production rebuild would rank on the server using the backend matcher (or a shared version of it), return the explanation of each score, and keep the rate as server-side configuration.
