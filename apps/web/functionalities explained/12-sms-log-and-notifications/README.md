# SMS log and notifications

The app never sends a real text message. Instead, every message the system "would send" is appended to a list in the store and shown in a panel called "Simulated SMS" (French: "SMS simulés"). On a wide screen the panel sits to the right of the main content; on a phone it is a collapsible bar under the content. Each entry shows the recipient phone number, the time, and the message text in the language currently selected.

This section covers the panel, how a message is stored (`{ key, params }` rather than finished text), how stored parameters are turned back into display text, and a complete list of every SMS key that the reducer creates, with its recipient and trigger.

## Files

| File | Role |
|---|---|
| `apps/web/src/components/SmsLog.tsx` | The panel component: toggle button, title, note, and the `<ol>` list of messages (`aria-live="polite"`). |
| `apps/web/src/i18n/format.ts` | `renderParams` (stored params to display text) and `money` (FCFA amount formatting). |
| `apps/web/src/i18n/trade.ts` | `tradeLabel`, used by `renderParams` for the `trade` parameter. |
| `apps/web/src/i18n/index.ts` | Re-exports `Key`, `Params`, `translate` from `@acbridge/core`. |
| `apps/web/src/store/reducer.ts` | Defines the local `sms(...)` factory and creates every message inside the `reducer` cases and `expireStale`. |
| `apps/web/src/domain/types.ts` | The `SmsMessage` interface. |
| `packages/core/src/i18n/en.ts` (and `fr.ts`) | The `sms.*` strings (panel labels and message templates). |
| `apps/web/src/App.tsx` | Mounts `<SmsLog />` next to `<main>` inside `.layout`. |
| `apps/web/src/styles.css` | `.sms*` rules: dark panel, collapsed body on phones, sticky side panel at `min-width: 900px`. |

## How it works

1. A user action reaches the store (see section 14). The store's `actions` object generates ids and a timestamp and dispatches a reducer action such as `register`, `choose` or `answer`.
2. Inside the reducer case, the local helper `sms(id, to, key, params, at)` builds a `SmsMessage`: `{ id, to, key, params, at }`. The `key` is an i18n key string (for example `'sms.jobRequest'`); `params` holds the raw values to substitute (for example `{ customer: 'Mary', urgency: 'today', trade: 'plumbing' }`).
3. The case returns a new state with `sms: [...s.sms, ...newMessages]`. Messages are only ever appended; nothing removes one except `reset` (which restores `initialState()` with `sms: []`).
4. The store saves the whole state (including `sms`) to `localStorage` after every change, so the log survives a page refresh.
5. `SmsLog` reads `state.sms` through `useStore()`. For each message it calls `renderParams(m.params, t, state.lang)` and then `t(m.key as Key, params)`. Because the stored value is `{ key, params }` and not final text, switching language with `LanguageToggle` re-renders every old message in the new language.
6. `renderParams` converts four kinds of stored values into display text (details below): `urgency`, `trade`, `method`, and money amounts.
7. The list is `<ol aria-live="polite" aria-relevant="additions">`, so a screen reader announces new messages as they are added without re-reading the whole list.
8. On a phone (below 900 px) the body is hidden by default (`.sms-body { display: none }`) and the toggle button, 48 px high, flips local component state `open` which adds the `sms-open` class. On a desktop (900 px and up) the toggle is hidden (`.sms-toggle { display: none }`), the body is always visible and the panel is `position: sticky; top: 76px` in the second grid column (`.layout { grid-template-columns: minmax(0, 1fr) 360px }`).

Core of the render loop:

```tsx
{state.sms.map((m) => {
  const params = renderParams(m.params, t, state.lang);
  return (
    <li key={m.id} className="sms-item">
      <div className="sms-meta"><strong>{t('sms.to')}: {m.to}</strong> <time dateTime={m.at}>{time(m.at)}</time></div>
      <div className="sms-text">{t(m.key as Key, params)}</div>
    </li>
  );
})}
```

## File by file

### `apps/web/src/components/SmsLog.tsx`

- Purpose: show "every SMS the system would send, in order, with the recipient".
- Export: `SmsLog()` (no props). Reads `{ state, t }` from `useStore()`; keeps one local `useState(false)` called `open`.
- Markup: `<aside className="sms [sms-open]" aria-label={t('sms.title')}>`. Inside: a `<button className="sms-toggle" aria-expanded={open}>` with the label `t('sms.hide')` when open or `t('sms.show')` when closed, plus a `.sms-count` badge showing `state.sms.length`; then `.sms-body` with an `<h2>` (`sms.title`), a note paragraph (`sms.note`), and the `<ol>`.
- When the list is empty it renders one `<li className="muted">` with `t('sms.empty')`.
- The speech-bubble emoji is wrapped in `aria-hidden="true"` so it is not read aloud.
- `time(iso)` is a local helper: `new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })` (uses the browser locale, not `state.lang`). The `<time>` element also carries `dateTime={m.at}`.
- The aside exposes the ARIA role `complementary`; the UI tests find it with `screen.getByRole('complementary', { name: /SMS/i })`.
- `m.key` is typed `string` in `SmsMessage`, so the component casts with `m.key as Key`.

### `apps/web/src/i18n/format.ts`

- `money(n, lang)`: thin wrapper over `formatAmount` from `@acbridge/core` (whole FCFA, `toLocaleString('fr-FR')` giving "9 000" or `'en-US'` giving "9,000"; throws `RangeError` if `n` is not an integer).
- `MONEY_PARAMS = new Set(['price', 'commission', 'payout', 'amount'])`.
- `renderParams(params, t, lang)`: returns a copy of `params` where
  - `urgency` (string) becomes `t('urgency.<value>')` (`today`, `week`, `later`);
  - `trade` (string) becomes `tradeLabel(t, trade).toLowerCase()` (catalogue trades use `trade.<key>`; free-text trades are shown as typed, capitalised, then lowercased);
  - `method` (string) becomes `t('pay.<value>')` (`pay.mtn`, `pay.orange`);
  - every key in `MONEY_PARAMS` whose value is a number is formatted with `money`.
- Other params (`name`, `phone`, `artisan`, `customer`, `voucher`, `seal`, `code`, `score`, `rate`) pass through unchanged. `rate` is a number but is intentionally not in `MONEY_PARAMS` (it is a percentage).
- `translate` (in `@acbridge/core`) then replaces each `{name}` placeholder with `String(value)`.

### `apps/web/src/domain/types.ts` (`SmsMessage`)

```ts
export interface SmsMessage {
  id: string;
  to: string;                      // phone number of the recipient
  key: string;                     // i18n key, so the log re-renders in the selected language
  params: Record<string, string | number>;
  at: string;                      // ISO timestamp
}
```

### `apps/web/src/store/reducer.ts` (SMS creation)

- `const sms = (id, to, key, params, at): SmsMessage => ({ id, to, key, params, at })`. The reducer is pure, so ids and the timestamp `at` arrive inside the action (`a.ids[i]`, `a.at`); the reducer never calls `Date.now()` or random functions.
- `expireStale(s, at, stamp)` builds ids from a stamp string: `` `${stamp}-${j.id}-c` `` (customer) and `` `${stamp}-${j.id}-a` `` (artisan).
- There is no function that deletes or edits a message.

### `packages/core/src/i18n/en.ts` (the `sms.*` keys)

Panel labels: `sms.title`, `sms.show`, `sms.hide`, `sms.empty`, `sms.note`, `sms.to`. English values: "Simulated SMS", "SMS", "Hide SMS", "No messages yet. Every SMS the system would send appears here.", "No real SMS is sent.", "To". `fr.ts` has the same keys ("SMS simulés", "Masquer SMS", "À", ...).

Message templates are listed in the next section.

## Every SMS key: who gets it, and when

Phone numbers in the demo: seed artisans Grace `+237690000015` (`seed-1`) and Paul `+237690000011` (`seed-2`) are the two vouch requesters; the demo customer is Mary `+237690000030`.

| Key | Params stored | Recipient | Created by (reducer case) | When |
|---|---|---|---|---|
| `sms.vouchRequest` | `name`, `phone`, `trade` | Each of seed artisans `seed-1` and `seed-2` (two messages, ids `a.ids[0]`, `a.ids[1]`; skipped if that seed artisan is not in state) | `register` | A new artisan signs up: asks the two seed artisans to vouch. |
| `sms.welcome` | none | The new artisan (`art.phone`) | `register` | Same moment: "you are registered. Waiting for 2 vouches". |
| `sms.vouchRecorded` | `voucher`, `seal` | The artisan being vouched for | `vouch` | A vouch passes `checkVouch` and is sealed. |
| `sms.vouchSealed` | `name`, `seal` | The voucher (the person who vouched) | `vouch` | Same moment: tells the voucher the vouch is final and can never be repeated for that person. |
| `sms.verified` | none | The artisan | `vouch` (only when `isVerified` flips from false to true) and `operator` (approve) | Verification reached through 2 vouches, or an operator approved. |
| `sms.rejected` | none | The artisan | `operator` (reject) | The operator panel rejects the artisan. |
| `sms.jobRequest` | `customer`, `urgency`, `trade` | The chosen artisan | `choose` | The customer picks an artisan; the offer is created as `REQUESTED`. |
| `sms.jobDeclined` | `artisan` | The customer (`job.customerPhone`) | `answer` (accept false) | The artisan answers NO. |
| `sms.accepted` | `artisan`, `price` | The customer | `answer` (accept true) | The artisan answers YES; price is frozen; customer is told to pay. |
| `sms.priceProposed` | `artisan`, `customer`, `price` | The customer | `chat` (only when the artisan's message applies a price, `check.price === 'applied'`) | The artisan states a final price in the chat. |
| `sms.payFailed` | `price` | The customer | `paySettle` (ok false) | The sandbox provider declines the payment. |
| `sms.jobCode` | `artisan`, `code` | The customer | `paySettle` (ok true) | Payment succeeded; the 6-digit job code is sent only now. |
| `sms.paymentReceived` | `price`, `rate`, `commission`, `payout` | The artisan | `paySettle` (ok true) | Payment succeeded; the artisan learns the commission split. |
| `sms.payoutPaid` | `payout` | The artisan | `payoutRelease` (operator releases), and `complete` (only when the payout was `PENDING` so it is paid on completion) | The artisan's share is paid out. |
| `sms.jobCompleted` | `artisan`, `price` | The customer | `complete` | The right job code was entered. |
| `sms.rated` | `score` | The artisan | `rate` | The customer submits a rating. |
| `sms.offerExpired` | `artisan` | The customer | `expireStale` (via `expire` and at the start of `answer`) | An unanswered offer passed its deadline. |
| `sms.offerLost` | `customer` | The artisan | `expireStale` | Same moment; only if the artisan still exists in state. |

Notes on the table:

- `sms.verified` is also produced by `operator` with `approve: true`; the key is chosen with `a.approve ? 'sms.verified' : 'sms.rejected'`.
- `sms.payout` exists in the dictionaries (`"job paid {price} FCFA. Commission {rate}% = ..."`) but no reducer case creates it; the commission message actually sent is `sms.paymentReceived`. It is currently an unused key.
- The `payoutPaid` message in `complete` uses id `a.ids[2]`; the one in `payoutRelease` uses `a.ids[0]`.
- `payStart`, `payoutHold`, `chat` messages without a price, `vouchBlocked`, `login`, `logout`, `nav`, `request` and the `patch*` actions create no SMS.

## Data and state

| Item | Where | Notes |
|---|---|---|
| `State.sms: SmsMessage[]` | `apps/web/src/store/reducer.ts` | Append-only, in creation order. `initialState().sms` is `[]`. |
| `SmsMessage.params` values | `string \| number` | Raw: trade key (`plumbing`) not label, urgency key (`today`), numbers not formatted strings, `method` key (`mtn`). |
| Panel open/closed | `useState` inside `SmsLog` | Not persisted; resets to closed on reload. Only matters on phones. |
| Persistence | `localStorage` key `acbridge.demo.v2` | The full `State` is saved, so messages survive refresh. "Reset demo" clears them. |

## Rules and edge cases

- Storing `{ key, params }` is the rule that makes the log language-switchable; free-form final text must never be stored in `SmsMessage`.
- Money must be stored as a number under `price`, `commission`, `payout` or `amount` to be formatted. A new money param with another name would be shown unformatted unless added to `MONEY_PARAMS`.
- The `trade`, `urgency` and `method` params must be the raw keys; `renderParams` only converts when the value is a string.
- The `sms.jobCode` message is the only place the plain job code appears outside the customer's screen; the job itself stores only `hashCode(code)`. The code is therefore shown to the customer only, never the artisan.
- A message addressed to a missing artisan can have `to: ''`: `payoutRelease` and `rate` use `artisan?.phone ?? ''`.
- Unknown keys fall back through `translate` (French, then the key itself), so a typo shows the raw key rather than crashing.
- Accessibility: live region is `polite` and `aria-relevant="additions"`; the toggle has `aria-expanded`; the tap target of the toggle is 48 px; the list scrolls inside `max-height: 60vh`.
- The panel always shows `t('sms.note')` ("No real SMS is sent."), plus the global banner `app.demo` explains the simulation.

## Tests

| File | What it checks |
|---|---|
| `apps/web/src/__tests__/journey.test.ts` ("runs register, 2 vouches, request, choose, YES, PAY, wrong code, right code, payout, rate once") | Exactly two `sms.vouchRequest` after register; `sms.verified` after the second vouch; no `sms.jobCode` before payment; a `sms.jobCode` exists after payment. |
| `apps/web/src/__tests__/chat.test.ts` ("the customer bargains, the artisan states 9 000 FCFA (5% = 450), the customer is told, YES locks it") | The last SMS is `sms.priceProposed` to `+237690000030` with `params: { artisan: 'Grace', price: 9000 }`. |
| `apps/web/src/__tests__/offers.test.ts` ("expires an urgent offer after an hour...", "a late YES does not accept...") | `sms.offerExpired` goes to the customer and `sms.offerLost` to the artisan; no `sms.accepted` on a late YES. |
| `apps/web/src/__tests__/vouch-chain.test.ts` ("Joel is verified by two seed artisans...") | `sms.vouchSealed` is sent to the voucher. |
| `apps/web/src/__tests__/ui-flows.test.tsx` (full journey, "survives a refresh...") | Reads the panel via `getByRole('complementary', { name: /SMS/i })`; checks French texts ("est plombier", "vous êtes maintenant vérifié", "Sceau VS-..."), that the job code SMS goes to the customer's number, "Commission 5% = 275 FCFA"; after switching to EN it expects "To: +237" and "you are now verified", proving re-rendering in the selected language. |
| `apps/web/src/__tests__/ui-expiry.test.tsx` ("an urgent offer lapses after one hour...") | Both expiry SMS texts appear in the rendered panel. |

## Backend connection

None for the panel itself (local only). In API mode the reducer still creates the same simulated SMS locally; the backend calls made by `apps/web/src/api/bridge.ts` do not read or write this log. The backend has no SMS endpoint mirrored by the web demo.

## Known limits and what changes in the production rebuild

- Nothing is delivered. The log is a developer and demo aid showing what a real SMS provider would send, to whom, and in which language.
- The job code is shown in clear text in the log and in `localStorage` (inside the message params). A production system must never log the code; only the delivery provider would hold it briefly.
- Messages are rendered in the language selected by the viewer, whereas a real SMS must be sent in the recipient's preferred language, fixed at send time. The production product stores a language per user and renders at send time.
- The production product replaces this list with real delivery records from an SMS provider: provider message id, status (queued, delivered, failed), cost and retries, kept server-side and shown to operators, not to every user.
- A single global panel shows messages for all recipients at once, which is only acceptable because everything is simulated in one browser.
- The key `sms.payout` is unused and can be removed.
