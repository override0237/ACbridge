# Connect flexibly (the bargaining chat)

Each job has a chat between the customer and the chosen artisan. The customer can bargain freely, but only the artisan can fix the final price, by ending a message with an amount and a currency (for example `9000 FCFA`). Phone numbers are hidden, and the chat closes for good once the customer's payment succeeds, or when the job is declined, expired or completed.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/Chat.tsx` | The chat screen for both sides (`ui.chatAs`): price banner, message list, send form, feedback line, and the artisan's YES / NO card. |
| `apps/web/src/domain/chat.ts` | Pure rules: `parseAmount`, `endsWithBareNumber`, `maskContacts`, `checkChatMessage`, `isChatOpen`, `isJobPaid`, constants `MIN_PRICE`, `MAX_PRICE`, `MAX_BODY`, types `ChatSender`, `PriceStatus`, `ChatCheck`. |
| `apps/web/src/store/reducer.ts` | The `chat` action (stores the message, applies the artisan's price, adds the system message, SMS and audit entry) and the other actions that add chat system messages (`answer`, `expire`, `paySettle`). |
| `apps/web/src/store/index.tsx` | `actions.sendChat`: validates with `checkChatMessage`, dispatches `chat`, mirrors to the backend, returns the `PriceStatus` to the UI. |
| `apps/web/src/api/bridge.ts` | `sendChat`: API-mode mirror that posts the same text to the backend as the right user. |
| `apps/web/src/screens/Tracking.tsx` | Customer entry button "Connect flexibly" (`chat.open`), shown only while `isChatOpen(job)`. |
| `apps/web/src/screens/ArtisanInbox.tsx` | Artisan entry button "Chat" (`chat.openArtisan`), shown only while `isChatOpen(j)`. |
| `backend/app/services/chat_service.py` | Backend rules (same regexes and limits): `parse_amount`, `mask_contacts`, `_price_status`, `send_message`, `list_messages`. |
| `backend/app/routers/chat.py` | `GET` and `POST /jobs/{job_id}/messages`. |
| `apps/web/src/domain/types.ts` | `ChatMessage` and `Job` types. |

## How it works

1. Customer path: on the Tracking screen, while the chat is open, the button `chat.open` runs `actions.go('chat', { chatAs: 'customer' })`. Artisan path: on the Inbox card, the button `chat.openArtisan` runs `actions.go('chat', { chatAs: 'artisan', jobId: j.id })`.
2. `Chat()` finds the job (`state.ui.jobId`), the artisan, and the messages (`state.chats.filter(m => m.jobId === job.id)`). `as` is `state.ui.chatAs ?? 'customer'`. The back target is `tracking` for the customer and `artisanInbox` for the artisan.
3. If `as === 'artisan'` and the logged-in artisan (`ui.actingArtisanId`) is not the job's artisan, the screen renders `<ArtisanLogin next="chat" />` instead.
4. The price banner shows a badge chosen by:

```ts
const priceLabel: Key = job.status !== 'REQUESTED' ? 'chat.priceAgreed'
  : job.priceSource === 'chat' ? 'chat.priceProposed' : 'chat.priceEstimate';
```

   plus `<PriceBreakdown price={job.price} rate={job.commissionRate} />`.
5. The send form is shown only if `isChatOpen(job)`. Otherwise a status notice is shown: `chat.closedPaid` when `isJobPaid(job)`, else `chat.errClosed`. The message history stays visible.
6. On submit, `send` calls `actions.sendChat(job.id, as, text)`.
7. In the store, `sendChat` runs `checkChatMessage(job, from, text)`. On refusal it returns `{ ok: false, error }` with `empty -> chat.errEmpty`, `too_long -> chat.errLong`, `closed -> chat.errClosed`. On success it dispatches `{ type: 'chat', id, sysId, jobId, from, text, at, ids: ids(2) }`, starts the API mirror, and returns `{ ok: true, price, amount }`.
8. The reducer `chat` case re-validates with `checkChatMessage` (the UI is not trusted), stores the message with `text: maskContacts(a.text.trim())`, and sets `price` on the message only when the price status is `applied`.
9. If the status is `applied`, the reducer also: computes `computeCommission(amount)`; sets `job.price = tx.price` and `job.priceSource = 'chat'`; appends a system message (`chat.sysPrice`, params `price`, `rate`, `commission`, `payout`); appends an SMS to the customer (`sms.priceProposed`); and appends an audit entry of kind `price`.
10. Back in `Chat.tsx`, the returned `PriceStatus` is mapped to a feedback line (see the table below). The text field is cleared on success of the call (even when the price was not applied); the feedback line is cleared whenever the user types.
11. The artisan's YES in this screen (card with `chat.yes`, shown when `as === 'artisan'` and `job.status === 'REQUESTED'`) calls `actions.answer(job.id, true)`, which freezes the price. The customer's payment (section 09) then creates the job code and closes the chat.

### The price rule in one place

`checkChatMessage(job, from, text)` in `apps/web/src/domain/chat.ts`:

```ts
const t = text.trim();
if (!t) return { ok: false, reason: 'empty' };
if (t.length > MAX_BODY) return { ok: false, reason: 'too_long' };
if (!job || !isChatOpen(job)) return { ok: false, reason: 'closed' };
const amount = parseAmount(t);
if (amount === null) return { ok: true, amount, price: endsWithBareNumber(t) && from === 'artisan' ? 'bare_number' : 'none' };
if (from !== 'artisan') return { ok: true, amount, price: 'not_artisan' };
if (amount < MIN_PRICE || amount > MAX_PRICE) return { ok: true, amount, price: 'out_of_range' };
if (job.status !== 'REQUESTED') return { ok: true, amount, price: 'locked' };
return { ok: true, amount, price: 'applied' };
```

The order matters: the sender check comes before the range check, and the range check comes before the lock check.

### PriceStatus values and the feedback messages

| `PriceStatus` | Meaning | Feedback in `Chat.tsx` (tone, key) |
|---|---|---|
| `applied` | Artisan, job `REQUESTED`, amount in range: the price is set | good, `chat.priceSet` (`{price}`) |
| `bare_number` | Artisan ended with a number but no currency | warn, `chat.noCurrency` |
| `out_of_range` | Artisan's amount is below 500 or above 5,000,000 | bad, `chat.outOfRange` (`{min}`, `{max}`) |
| `locked` | Artisan's valid amount, but the job is no longer `REQUESTED` (the artisan already said YES) | warn, `chat.locked` |
| `not_artisan` | The customer ended a message with an amount and currency; it is only an offer | warn, `chat.notArtisan` |
| `none` | No amount to act on (including a customer's bare number) | no feedback (`null`) |

Refusals from `sendChat` (`ok: false`) show a bad-tone feedback with the key `chat.errEmpty`, `chat.errLong` or `chat.errClosed`. In every non-refused case the message is still sent and visible; only the price is not changed.

## File by file

### `apps/web/src/domain/chat.ts`
- Constants: `MAX_BODY = 500`, `MIN_PRICE = 500`, `MAX_PRICE = 5_000_000`, `HIDDEN = '[number hidden]'`.
- Regexes (kept identical to the backend):
  - `AMOUNT_AT_END`: `/(?<![\d.,])(\d{1,3}(?:[ .,  ]\d{3})+|\d+)\s*(?:F\s?CFA|XAF|CFA)\s*[.!]*\s*$/i`. The amount must be at the very end of the text, with the currency last. A trailing `.` or `!` is allowed. Thousands may be separated by space, dot, comma or non-breaking spaces. The negative look-behind stops `9.5 FCFA` from being read as 5.
  - `ENDS_WITH_NUMBER`: a digit then optional punctuation at the end.
  - `PHONE`: `+CC` numbers (9 or more digits in total with optional separators) and contiguous runs of 9 or more digits. Prices have at most 7 digits so they are never touched.
- `parseAmount(text)`: the integer after stripping separators, or `null`. The currencies accepted are `FCFA`, `F CFA`, `XAF`, `CFA` (case-insensitive).
- `endsWithBareNumber(text)`: true when `parseAmount` is `null` and the text ends with a number, e.g. `ok 9000`.
- `maskContacts(text)`: replaces phone-like runs with `[number hidden]`.
- `isJobPaid(job)`: `job.codeHash !== null`. The job code is created exactly when the customer's payment succeeds, so the hash is the "paid" marker.
- `isChatOpen(job)`: `(status === 'REQUESTED' || status === 'ACCEPTED') && !isJobPaid(job)`. So the chat is closed for `DECLINED`, `EXPIRED`, `COMPLETED`, and for any job whose payment succeeded.
- `checkChatMessage`: see above. Returns `ChatCheck = { ok: true; amount; price } | { ok: false; reason: 'empty' | 'too_long' | 'closed' }`. Note the length is checked on the trimmed text and the amount is parsed from the original (unmasked) text.

### `apps/web/src/screens/Chat.tsx`
- Local state: `text`, `feedback` (`{ tone, key, params }`), `endRef` (scrolls to the newest message when `messages.length` changes).
- Message rendering: system messages are translated at render time with `t(m.key, renderParams(m.params, t, lang))`; people's messages use `m.text`. The label is `chat.who.system`, `chat.who.customer` or the artisan's name. A message with `price` set shows `✅ <amount> FCFA`. Own messages get the `mine` CSS class.
- Hints under the field: `chat.hintCustomer` or `chat.hintArtisan`, and `chat.masked`.
- `textarea` has `maxLength={MAX_BODY}`.
- The customer view also shows `inbox.from` with the customer's name at the bottom.
- Missing job or artisan: an empty screen with `tracking.none`.

### `apps/web/src/store/reducer.ts` (chat-related)
- `chat` action: described in "How it works". Returns `s` unchanged if the job is missing or `checkChatMessage` refuses (this is what makes a closed chat safe even if the UI misbehaves).
- System messages written by other actions (all have `from: 'system'`, `text: ''`, a `key` and `params`):

| Key | Written by | When |
|---|---|---|
| `chat.sysPrice` | `chat` | the artisan's amount was applied |
| `chat.sysAccepted` | `answer` (accept) | the artisan said YES; price frozen (`{price, artisan}`) |
| `chat.sysDeclined` | `answer` (decline) | the artisan said NO |
| `chat.sysExpired` | `expireStale` | the offer lapsed (section 07) |
| `chat.sysClosed` | `paySettle` (success) | payment succeeded; id is `<paymentId>-closed` |

### `apps/web/src/store/index.tsx` (`sendChat`)
- Signature: `sendChat(jobId, from, text): { ok: true; price: PriceStatus; amount: number | null } | { ok: false; error: Key }`.
- After dispatching, `mirror` posts to the backend (API mode only). The mirror is fire-and-forget; its failure only sets a notice.

### `apps/web/src/api/bridge.ts` (`sendChat`)
- `sendChat(job, from, text, artisan)`: returns if `job.remoteId` is missing; otherwise logs in as the customer (`job.customerPhone`) or as the artisan (`artisan.phone`) and calls `api.sendMessage(token, job.remoteId, text)`. The comment says the backend reads the amount from the text itself, so no amount is sent separately.

### `apps/web/src/screens/Tracking.tsx` and `ArtisanInbox.tsx` (entry buttons only)
- Tracking: `{isChatOpen(job) && <Button ... label={t('chat.open')} onClick={() => actions.go('chat', { chatAs: 'customer' })} />}`.
- Inbox: `{isChatOpen(j) && <Button variant="secondary" ... label={t('chat.openArtisan')} onClick={() => actions.go('chat', { chatAs: 'artisan', jobId: j.id })} />}`.
- Because both use `isChatOpen`, the button disappears as soon as the job is declined, expired, completed or paid. Note that the customer button passes no `jobId`; it relies on `ui.jobId` already being set.

## Data and state

- `ChatMessage` (`types.ts`): `id`, `jobId`, `from: 'customer' | 'artisan' | 'system'`, `text` (already masked), optional `key` and `params` (system messages), optional `price` (set only when this artisan message became the job price), `at`.
- `Job` fields used: `status`, `codeHash`, `price`, `priceSource` (`'estimate'` until a chat message sets it to `'chat'`), `commissionRate`, `createdAt`. A comment in `types.ts` says the price comes from "the customer writes an amount in the chat"; that comment is out of date: the code sets it from the artisan's message.
- `State.chats: ChatMessage[]` is a flat list across all jobs, persisted with the rest of the state in `localStorage`.
- `UiState.chatAs?: 'customer' | 'artisan'` and `UiState.jobId` choose whose chat is open.
- Side effects of an applied price: `State.sms` (`sms.priceProposed` to the customer), `State.audit` (kind `price`: artisan, price, rate, commission).

## Rules and edge cases

| Rule | Where |
|---|---|
| A message is 1 to 500 characters after trimming (`chat.errEmpty`, `chat.errLong`) | `checkChatMessage`; the textarea also has `maxLength` |
| Only the artisan can set the price; a customer's amount is a plain offer and never changes it (`chat.notArtisan`) | `checkChatMessage` (`not_artisan`); reducer only applies `applied` |
| The amount must end the message and be followed by FCFA / F CFA / XAF / CFA | `parseAmount` |
| A bare number from the artisan does nothing and prompts for the currency (`chat.noCurrency`); a customer's bare number is just talk | `endsWithBareNumber` and the `from === 'artisan'` condition |
| Amount range 500 to 5,000,000 (`chat.outOfRange`); an out-of-range message is still sent | `checkChatMessage` |
| The price can only be set while the job is `REQUESTED` (before YES); after YES it is locked, even for the artisan (`chat.locked`) | `checkChatMessage` |
| Phone numbers are replaced with `[number hidden]` in the stored text, so the deal stays on the platform | `maskContacts` in the reducer |
| The chat is open only while the job is `REQUESTED` or `ACCEPTED` and unpaid; it closes permanently when `paySettle` succeeds (the job gets its `codeHash`), and for `DECLINED`, `EXPIRED`, `COMPLETED` (`chat.errClosed`, `chat.closedPaid`) | `isChatOpen` / `isJobPaid`; reducer re-checks |
| A pending payment does not close the chat; a failed payment does not close it either | `isJobPaid` depends on `codeHash`, set only on a successful `paySettle` |
| A re-validation in the reducer means a message sent in the same tick as a closure is dropped silently | `chat` case returns `s` |
| The customer's consent to the price is paying, not typing; the customer is told the price by SMS (`sms.priceProposed`) | reducer; Payments section |
| An artisan can act in the chat only when logged in as that job's artisan | `Chat.tsx` login gate |

Other i18n keys used by the screen: `chat.title`, `chat.instruction`, `chat.with`, `chat.asCustomer`, `chat.asArtisan`, `chat.field`, `chat.placeholder`, `chat.send`, `chat.empty`, `chat.priceEstimate`, `chat.priceProposed`, `chat.priceAgreed`.

## Tests

- `apps/web/src/__tests__/chat.test.ts`
  - "reading the price from the chat (same cases as the backend tests)": `parseAmount` table (`9000 FCFA`, `9 000 XAF`, `1 250 000 CFA`, `12000 FCFA!!`, ...) and negative table (`9000`, `FCFA 9000`, `9000 FCFA is too much, sorry`, `9.5 FCFA`, `hello`, empty); "spots a bare number..."; "hides phone numbers but never prices".
  - "who can fix the price, and when" > "only the ARTISAN, only before the artisan says YES, only inside the allowed range" (checks `applied`, `not_artisan`, `out_of_range` at 100 and 9,000,000, `locked`, `bare_number`, customer bare number is `none`); "refuses empty, over-long and closed-chat messages".
  - "the reducer turns the ARTISAN amount into the price and the commission": "the customer bargains, the artisan states 9 000 FCFA (5% = 450), the customer is told, YES locks it" (price stays 5500 after customer offers, 12000 then 9000 after artisan messages; system message `chat.sysPrice` with commission 450 and payout 8550; SMS and audit; locked after YES; payout 8550 after payment); "closes the chat for good once the customer payment succeeds"; "a failed payment does not close the chat"; "ignores a message on a job that is closed".
- `apps/web/src/__tests__/ui-chat.test.tsx` > "the customer bargains (amounts do not count), the artisan writes 9 000 FCFA, says YES, the customer pays, the job completes with 5% = 450": full rendered flow including the `chat.notArtisan` and `chat.noCurrency` alerts, `chat.priceSet`, `chat.locked`, and that the chat button disappears for both sides after payment.
- `backend/tests/test_chat.py` (backend rules): `test_amount_is_read_when_the_currency_is_at_the_end`, `test_no_amount_when_currency_is_missing_or_not_last`, `test_bare_number_is_detected_so_the_ui_can_remind_about_the_currency`, `test_phone_numbers_are_hidden_but_prices_are_not`, `test_both_parties_can_talk_and_read_the_conversation_in_order`, `test_strangers_cannot_read_or_write`, `test_artisan_amount_with_currency_becomes_the_proposed_price_and_shows_the_commission`, `test_the_artisans_acceptance_is_still_what_agrees_the_price`, `test_an_amount_typed_by_the_customer_or_without_currency_changes_nothing`, `test_out_of_range_amounts_are_rejected_but_the_message_is_kept`, `test_price_is_locked_once_the_artisan_has_agreed`, `test_inspection_jobs_do_not_take_a_price_from_the_chat`, `test_phone_numbers_in_messages_are_hidden`, `test_message_length_is_validated`, `test_chat_closes_with_the_job`, `test_messages_cannot_be_edited_or_deleted_even_directly_in_the_database`.

## Backend connection

- Endpoints (`backend/app/routers/chat.py`, prefix `/jobs/{job_id}/messages`): `GET` lists messages (parties and admins); `POST` sends one (customer or artisan only, rate-limited to 60 per 60 s). The response carries `price_status`.
- `chat_service.send_message` mirrors the web rules: same regexes, `MAX_BODY = 500`, `MIN_PRICE = 500`, `MAX_PRICE = 5_000_000`, only the `ARTISAN` party gets `APPLIED`, amount parsed from the original text before masking, `LOCKED` once the job is not `REQUESTED` or the artisan agreed.
- Backend status names are upper-case: `NONE`, `APPLIED`, `OUT_OF_RANGE`, `LOCKED`, `NOT_APPLICABLE`, `NOT_ARTISAN`. The backend has `NOT_APPLICABLE` (inspection-required jobs take no price from chat) and does not return a `bare_number` status; the web adds `bare_number` locally for the UI reminder.
- Closure: the backend refuses with a conflict when the job is `COMPLETED` or `CANCELLED` (its name for declined or expired offers), or `job_service.job_is_paid` is true (a succeeded or released job payment). The web uses `codeHash !== null` as its equivalent of "paid".
- When applied, the backend sets `job.proposed_price` and `proposed_by = "ARTISAN"` and records a `PRICE_PROPOSED_IN_CHAT` event with the commission if agreed. The backend then needs the artisan's `POST /accept` (mirrored by `bridge.acceptJob`) to agree the price.
- The web bridge sends the raw text; the amount is parsed again on the server. `bridge.sendChat` does nothing without `job.remoteId`.

## Known limits and what changes in the production rebuild

- Local chat is simulated: both sides are played in one browser through `ui.chatAs`; there is no real-time delivery, push notification or read receipt. Messages are in `localStorage`.
- Messages in the web state are not append-only protected (the backend has a database-level guard against edits and deletes).
- Phone masking only catches contiguous 9+ digit runs and `+CC` numbers. Numbers written in words or split by other characters are not hidden.
- The mirror sends the text after the local dispatch and does not read the backend's `price_status` back, so the local and backend views of the price could diverge if the backend refuses (e.g. an `expired` job on the server).
- A production rebuild would make the server the only source of the price and of the open/closed state, return `price_status` to the client, and subscribe to new messages instead of reading local state.
