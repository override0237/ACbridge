# Trades and customer requests

A customer (the app uses one fixed demo customer, Mary) types which kind of artisan is needed, picks how urgent it is (Today, This week, Not urgent), optionally describes the problem, and presses "Find artisans". The trade can be any text: the seven catalogue trades are recognised in French or English, and anything else is kept as free text. Submitting creates a request and opens the match list.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/CustomerRequest.tsx` | The request form: trade field, urgency radio buttons, offer-window hint, description, error box. |
| `apps/web/src/components/TradeField.tsx` | Free-text input with a `<datalist>` of the seven catalogue trades in the current language. Shared with artisan sign-up. |
| `apps/web/src/domain/trades.ts` | `TRADE_KEYS`, `BACKEND_SKILL`, `ALIASES`, `normalizeText`, `resolveTrade`, `isCatalogueTrade`, `sameTrade`. |
| `apps/web/src/i18n/trade.ts` | `tradeLabel(t, trade)`: display name of a stored trade. |
| `apps/web/src/store/index.tsx` | `submitRequest` action: resolves the trade, builds the `ServiceRequest`, dispatches, mirrors to the backend. |
| `apps/web/src/store/reducer.ts` | `request` case (stores the request and moves to the `matches` screen); `URGENCIES` constant; `DEMO_CUSTOMER`. |
| `apps/web/src/domain/types.ts` | `ServiceRequest` and `Urgency` types. |
| `apps/web/src/domain/offers.ts` | `OFFER_TTL_MS`: the 1 hour / 1 day / 5 days windows that the hint describes (read for context; the expiry feature is another section). |
| `apps/web/src/api/bridge.ts` | `createRequest` and `skillFor` with the `BACKEND_SKILL` mapping (API mode). |
| `packages/core/src/i18n/en.ts`, `fr.ts` | Keys `request.*`, `urgency.*`, `trade.*`. |
| `apps/web/src/__tests__/ui-flows.test.tsx`, `rules.test.ts` | Tests. |

## How it works

1. Home -> "I need a service" (`home.customer`) -> `actions.go('customerRequest')`.
2. `CustomerRequest` holds local state: `urgency` (default `'today'`), `description`, `trade`, `error`.
3. `TradeField` renders `<input list={listId} ... required autoComplete="off" placeholder={t('trade.hint')}>` and a `<datalist>` with one `<option>` per `TRADE_KEYS` entry, valued with `t('trade.<key>')`, i.e. "Plombier, Électricien, Menuisier, Maçon, Mécanicien, Couturier, Coiffeur" in French and "Plumber, Electrician, Carpenter, Mason, Mechanic, Tailor, Hairdresser" in English. The browser offers them as suggestions; the user can still type anything.
4. The urgency picker is a `role="radiogroup"` with three `role="radio"` buttons built from the `OPTIONS` array: `today` (fire icon), `week` (calendar icon), `later` (clock icon). Labels come from `urgency.today`, `urgency.week`, `urgency.later` ("Today / This week / Not urgent", "Aujourd'hui / Cette semaine / Pas urgent"). The selected one gets class `choice active`, `aria-checked`, and a check mark.
5. Under the picker the hint `request.ttlHint` is always visible, prefixed with a stopwatch icon. English text: "The artisan must accept within 1 hour (Today), 1 day (This week) or 5 days (Not urgent), or the offer is cancelled." This is a static text; it does not change with the selected option.
6. The neighbourhood field is read-only and shows `common.neighbourhood` (the constant `NEIGHBOURHOOD = 'Neighbourhood A'` is what is stored).
7. On submit the form calls `actions.submitRequest({ trade, urgency, description })`. If it returns `{ ok: false, error }` the screen calls `setError(error)`; typing in the trade field clears the error.
8. `submitRequest` in `store/index.tsx`:

```ts
const tradeKey = resolveTrade(trade);
if (!tradeKey) return { ok: false, error: 'request.errTrade' };
const request = {
  id: uid('req'), customerPhone: SEED_CUSTOMER.phone, customerName: SEED_CUSTOMER.name, trade: tradeKey,
  neighbourhood: NEIGHBOURHOOD, urgency, description: description.trim(), at: now(),
};
dispatch({ type: 'request', request });
```

   It then runs the API-mode mirror (below) and returns `{ ok: true }`.
9. Reducer `request`: `{ ...s, requests: [...s.requests, a.request], ui: { ...s.ui, requestId: a.request.id, screen: 'matches' } }`. The `Matches` screen (section 05) then ranks verified artisans of that trade with `sameTrade`.

### How `resolveTrade` normalises what the user types

```ts
export const normalizeText = (s: string): string =>
  s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

export function resolveTrade(input: string): string | null {
  const n = normalizeText(input);
  if (n.length < 2) return null;
  for (const key of TRADE_KEYS) {
    const names = [...ALIASES[key], normalizeText(en[`trade.${key}`]), normalizeText(fr[`trade.${key}`])];
    if (names.includes(n)) return key;
  }
  return n;
}
```

(The source writes the accent range as literal combining characters; it is the Unicode range U+0300 to U+036F.)

1. `normalizeText`: decompose accents (NFD), delete the combining marks, lower-case, trim, collapse runs of spaces. So `" Électricien "` becomes `"electricien"` and `"Maçon"` becomes `"macon"`.
2. Fewer than 2 characters after normalisation: returns `null` (the store then returns the error key).
3. For each of the seven keys the accepted names are the `ALIASES` list plus the normalised English and French dictionary labels `trade.<key>`:

| Key | Aliases in `ALIASES` (already accent-free) |
|---|---|
| `plumbing` | plumbing, plumber, plomberie, plombier |
| `electrical` | electrical, electrician, electricity, electrical repair, electricien, electricite |
| `carpentry` | carpentry, carpenter, menuiserie, menuisier |
| `masonry` | masonry, mason, maconnerie, macon |
| `mechanics` | mechanics, mechanic, mecanique, mecanicien |
| `tailoring` | tailoring, tailor, couture, couturier, couturiere |
| `hairdressing` | hairdressing, hairdresser, coiffure, coiffeur, coiffeuse |

4. A match returns the catalogue key (e.g. `'plumbing'`). Otherwise the normalised text itself is returned (e.g. `"Soudeur"` -> `"soudeur"`) and that string is stored as the request trade. So the stored value is either a key from `TRADE_KEYS` or lower-case, accent-free free text.
5. The match is an exact equality after normalisation, not a "contains" search: `"plombier urgent"` is free text, not plumbing.

### Display and matching of a stored trade

- `tradeLabel(t, trade)` (`i18n/trade.ts`): if `isCatalogueTrade(trade)` it returns `t('trade.<trade>')` (translated to the current language); otherwise it returns the stored text with its first letter upper-cased (`"soudeur"` -> `"Soudeur"`). Accents of free text are already gone because they were stripped when stored.
- `sameTrade(a, b)` compares `normalizeText(a) === normalizeText(b)`. `rankArtisans` in `rules.ts` uses it to match `artisan.trade` with the request trade, so a free-text trade typed identically by a customer and by an artisan (e.g. "Soudeur") matches.

## File by file

### `apps/web/src/screens/CustomerRequest.tsx`
- Constant `OPTIONS: { value: Urgency; icon: string }[]` for the three urgency choices.
- The `<form>` does not have `noValidate`, so the browser's own `required` check on the trade input blocks an empty submit before the store runs; the store check `request.errTrade` covers one-character input.
- The description textarea is optional (`request.description` "What is the problem? (optional)", placeholder `request.descriptionHint`).
- Error box: `<div role="alert" className="error" hidden={!error}>`.
- The customer identity is not typed: `submitRequest` always uses `SEED_CUSTOMER` (`name: 'Mary'`, `phone: '+237690000030'`).

### `apps/web/src/components/TradeField.tsx`
Props `label`, `value`, `onChange(v)`. Uses `useId()` so each instance has its own datalist id. Because options are `t('trade.<key>')`, suggestions follow the selected language; the user can pick one or type freely. Used by `CustomerRequest` (label `request.trade`) and `ArtisanSignup` (label `signup.trade`).

### `apps/web/src/domain/trades.ts`
Listed above. Other exports:
- `TRADE_KEYS = ['plumbing','electrical','carpentry','masonry','mechanics','tailoring','hairdressing'] as const` and `TradeKey`.
- `BACKEND_SKILL: Record<TradeKey, string>`: `Plumbing`, `Electrical Repair`, `Carpentry`, `Masonry`, `Mechanics`, `Tailoring`, `Hairdressing` (names of the backend skills in `backend/app/seed.py`).
- `isCatalogueTrade(trade)`: type guard, true if `trade` is one of `TRADE_KEYS`.
- It imports `en` and `fr` dictionaries from `@acbridge/core` to learn the labels, so changing a label automatically changes what is recognised.

### `apps/web/src/i18n/trade.ts`
Single function `tradeLabel`, described above.

### `apps/web/src/store/index.tsx` (`submitRequest`)
Signature: `submitRequest(v: { trade: string; urgency: Urgency; description: string }): { ok: true } | { ok: false; error: Key }`. The only refusal is the trade (`request.errTrade`). The urgency is not validated at run time (TypeScript type only).

### `apps/web/src/store/reducer.ts`
`request` case as above. `export const URGENCIES: Urgency[] = ['today', 'week', 'later']` and `DEMO_CUSTOMER = SEED_CUSTOMER` are exported at the end of the file.

### `apps/web/src/domain/types.ts`
```ts
export type Urgency = 'today' | 'week' | 'later';
export interface ServiceRequest {
  id: string; customerPhone: string; customerName: string; trade: string;
  neighbourhood: string; urgency: Urgency; description: string; at: string; remoteId?: string;
}
```
`trade` is a plain `string` on purpose (catalogue key or free text).

### `apps/web/src/domain/offers.ts` (context for the hint)
`OFFER_TTL_MS: Record<Urgency, number> = { today: 1 h, week: 24 h, later: 5 x 24 h }`. When the customer later chooses an artisan, the job's deadline is `job.createdAt + OFFER_TTL_MS[request.urgency]`; an unanswered offer expires after that. So urgency chosen on this screen is what sets the offer window, and `request.ttlHint` tells the customer in advance.

### `apps/web/src/api/bridge.ts` (`createRequest`, `skillFor`)
See "Backend connection".

## Data and state

- Writes: `state.requests` (append), `state.ui.requestId` (the new request id), `state.ui.screen = 'matches'`.
- `ServiceRequest.remoteId` is filled later in API mode through `patchRequest`.
- Persisted with the whole state in `localStorage['acbridge.demo.v2']`. Nothing is persisted from the form before submit (typed values are lost if the user navigates away).
- Artisans' `trade` field uses the same representation (written by sign-up through the same `resolveTrade`).

## Rules and edge cases

| Rule | Where | Message |
|---|---|---|
| Trade must be at least 2 characters after normalisation | `resolveTrade` (null), checked in store `submitRequest` | `request.errTrade` ("Write the artisan you need, for example electrician.") |
| Empty trade blocked by browser | `required` attribute in `TradeField` (not under `noValidate` here) | browser text |
| Trade stored as catalogue key when it matches a known name in FR or EN | `resolveTrade` | none |
| Anything else stored as normalised free text | `resolveTrade` | none |
| Urgency defaults to `today` | `CustomerRequest` state | none |
| No verified artisan for the trade | `Matches` screen | `matches.none` ("No verified artisan is available for this trade.") |

- Free-text trades are valid requests; they simply have no results unless a verified artisan registered with the same normalised text.
- Case, accents and extra spaces never matter (`" MAÇON "` equals `"macon"` equals the `masonry` key).
- A plural or typo ("plombiers") is not recognised and becomes free text.
- The offer windows are enforced elsewhere (`offers.ts`, reducer `expire`/`answer`); this screen only informs.

## Tests

- `apps/web/src/__tests__/rules.test.ts`, describe "trades", test "resolves what the user types in either language, or keeps free text": `resolveTrade('Plombier')` -> `'plumbing'`; `' électricien '` -> `'electrical'`; `'Carpenter'` -> `'carpentry'`; `'Soudeur'` -> `'soudeur'`; `'x'` -> `null`.
- `apps/web/src/__tests__/ui-flows.test.tsx`, test "lets a customer ask for any artisan: a free-text trade matches, and an unserved trade says so" (describe "full UI journey in the rendered app (French default)"): an artisan "Wendy" registers with trade "Soudeur" and gets two simulated vouches; the customer types `soudeur` in "Quel artisan vous faut-il ?", presses "Chercher" and sees exactly one result card (Wendy); going back and typing "Maçon" gives zero cards and the text "Aucun artisan vérifié".
- The first test of the same file ("registers, gets vouched, is matched, ...") types "Plombier" and clicks the "Aujourd'hui" radio, then expects three matching cards (Grace, Blaise and Joel), proving the alias mapping and urgency selection.
- `apps/web/src/__tests__/bridge.test.ts` exists in the same folder; it was not read for this section, so what it asserts about trades is not described here.

## Backend connection

API mode only (`store.submitRequest` -> `mirror` -> `bridge.createRequest(request, artisans)`):
1. `POST /auth/register` for the demo customer (role `CUSTOMER`, failure ignored) and `POST /auth/login`.
2. `skillFor(req.trade)`: if `!isCatalogueTrade(trade)` it throws `"<trade>" is not in the backend skill catalogue, so it stays local`, which becomes the visible notice; the local request still works. For catalogue trades it maps the key with `BACKEND_SKILL` and finds the skill id with `GET /skills` (name compared case-insensitively; result cached in `skillIds`). If the skill is missing it throws asking to run `python -m app.seed`.
3. `POST /service-requests` with `skill_id`, `description` (or `"<trade> help needed"` when empty), `location` (`"Neighbourhood A, Buea"`) and `urgency` mapped `today -> TODAY`, `week -> THIS_WEEK`, `later -> NOT_URGENT` (the backend schema `urgency: Literal["TODAY","THIS_WEEK","NOT_URGENT"]`).
4. `GET /matches/{request_id}`, then local artisans without a `remoteId` are linked to backend artisans by first name (`m.full_name.toLowerCase().startsWith(a.name.toLowerCase())`); links are stored with `patchArtisan`, the request id with `patchRequest`.

The backend offer windows are configured in `backend/.env.example` as `OFFER_TTL_HOURS_TODAY=1`, `OFFER_TTL_HOURS_THIS_WEEK=24`, `OFFER_TTL_HOURS_NOT_URGENT=120`, the same values as `OFFER_TTL_MS` in the front end (per the comment in `offers.ts`).

## Known limits and what changes in the production rebuild

- Only one customer exists (the seeded Mary); the form has no customer identity, phone verification or location. The neighbourhood is a constant.
- The trade catalogue is hard-coded (7 trades, hand-written aliases in French and English). A production system would load the catalogue from the backend and use proper search or synonyms; it would likely not accept unlimited free text for matching.
- Free-text trades never reach the backend (skills can only be added by admins there), so in API mode they stay local.
- Matching is exact equality after normalisation, with no fuzzy matching, plurals or typo tolerance, and free-text display loses accents.
- The offer-window hint is a fixed sentence, not computed from `OFFER_TTL_MS`; the two must be kept in sync by hand (and with the backend env values).
- Form input is not saved; urgency is not validated at run time.
