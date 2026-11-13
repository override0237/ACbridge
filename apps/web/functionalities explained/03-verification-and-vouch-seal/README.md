# Verification and the Vouch Seal

A new artisan is "not verified" and is hidden from customers until two already-verified artisans have each vouched for them (or the operator approves them). Verified artisans get a panel on their status screen where they can vouch for others; each vouch is final, gets a seal code such as `VS-1A2B3C4D`, and is chained by hash to the previous vouch. The operator panel shows pending artisans and a "Vouch ledger" that reports whether the chain is intact.

## Files

| File | Role |
|---|---|
| `apps/web/src/screens/ArtisanStatus.tsx` | The artisan's verification screen: vouch counter, "simulate vouch" buttons, the Vouch Seal card (candidate list, confirm box, sealed list). |
| `apps/web/src/domain/rules.ts` | `checkVouch`, `countValidVouches`, `isVerified`, `isTrusted` (private): who may vouch and who counts as verified. |
| `apps/web/src/config.ts` | `VOUCHES_REQUIRED = 2`. |
| `apps/web/src/domain/security.ts` | Seal ledger: `GENESIS_HASH`, `hasVouched`, `sealVouch`, `lastHash`, `verifyLedger`. |
| `apps/web/src/store/index.tsx` | `vouch` action: pre-check, security audit on duplicates, dispatch, API mirror. |
| `apps/web/src/store/reducer.ts` | `vouch`, `vouchBlocked`, `operator` cases (writes the sealed vouch, SMS and audit). |
| `apps/web/src/data/seed.ts` | `SEED_VOUCHERS = ['seed-1', 'seed-2']`, the two seeded artisans behind the "Simulate vouch" buttons, and the pending candidate `seed-5` (Samuel). |
| `apps/web/src/screens/Operator.tsx` | Only the "Pending verifications" card and the "Vouch ledger" card are part of this section. |
| `apps/web/src/domain/types.ts` | `Vouch` and `Artisan` types. |
| `apps/web/src/api/bridge.ts` | `vouch`, `verifyAfterVouches`, `operatorDecision` (API-mode mirror). |
| `apps/web/src/__tests__/vouch-chain.test.ts`, `rules.test.ts`, `security-money.test.ts`, `ui-flows.test.tsx` | Tests. |

## How it works

### Becoming verified (simulated vouches)

1. After sign-up the artisan lands on `ArtisanStatus` (see section 02). The component finds `artisan` by `state.ui.actingArtisanId`; if there is none it renders `<ArtisanLogin next="artisanStatus" />`.
2. It computes `count = countValidVouches(artisan, vouches, artisans)` and `verified = isVerified(...)`, and shows `status.count` with `n = Math.min(count, VOUCHES_REQUIRED)` and `total = VOUCHES_REQUIRED` (e.g. "0 sur 2 garanties").
3. While not verified, two buttons are listed from `SEED_VOUCHERS` (`status.simulate`, "Simulate vouch 1/2"). A click calls `actions.vouch(artisan.id, id)` where `id` is `seed-1` (Grace) or `seed-2` (Paul). `workedTogether` defaults to `true`. A returned error key is shown in the alert box (`setError`). A button becomes disabled with label `status.done` once that seed already vouched for this artisan.
4. `actions.vouch(artisanId, voucherId, workedTogether = true)` in `store/index.tsx`:
   1. finds both artisans, else returns `{ ok: false, error: 'status.noArtisan' }`;
   2. runs `checkVouch(artisan, voucher, workedTogether, s.vouches, s.artisans)`;
   3. on failure: if `check.reason === 'duplicate'` it first dispatches `vouchBlocked` (security audit), then returns `{ ok: false, error: VOUCH_ERRORS[check.reason] }`;
   4. on success dispatches `{ type: 'vouch', artisanId, voucherId, workedTogether, vouchId: uid('vouch'), at: now(), ids: ids(5) }` and returns `{ ok: true }`;
   5. in API mode, in the background (see Backend connection).
5. Reducer case `vouch`:
   1. finds both artisans (else unchanged state);
   2. re-runs `checkVouch(...)` and returns the unchanged state if it fails (the UI and store are not trusted);
   3. builds the vouch with a seal chained to the previous one:

```ts
const vouch: Vouch = {
  id: a.vouchId, artisanId: artisan.id, voucherId: voucher.id, voucherPhone: voucher.phone,
  workedTogether: a.workedTogether, at: a.at,
  ...sealVouch(lastHash(s.vouches), artisan.id, voucher.id, a.at),
};
```

   4. computes `was = isVerified(artisan, s.vouches, ...)` and `now = isVerified(artisan, vouches, ...)`;
   5. adds SMS `sms.vouchRecorded` to the artisan (`voucher`, `seal`) and `sms.vouchSealed` to the voucher (`name`, `seal`), plus an audit entry `kind: 'verification'`, `{ event: 'vouch', name, voucher, seal }`;
   6. if `now && !was` also SMS `sms.verified` to the artisan and audit `{ event: 'verified', name }`.
6. Because `isVerified` is recomputed from state on every render, the badge changes from "waiting" (`signup.waiting`) to "verified" (`common.verified`) and the instruction changes to `status.verifiedMsg` with no stored "verified" flag.

### Verified artisan vouches for another (the Vouch Seal panel)

1. The "Vouch Seal" card (`vouch.title`) always shows the rule `vouch.rule`. If the artisan is not verified it shows `vouch.needVerified`.
2. If verified, `candidates = artisans.filter((a) => a.id !== artisan.id && !a.rejected && !isVerified(a, ...))` are listed with name, trade (`tradeLabel`) and a "Sealed" chip when `hasVouched(artisan.id, c.id, vouches)` is true. `vouch.none` shows when the list is empty.
3. Clicking "Vouch" (`vouch.button`):
   - not yet sealed: `setConfirming(c.id)` opens an inline confirm box with `vouch.confirmTitle`, the warning `vouch.warn` ("This is final..."), a checkbox `vouch.worked` ("I have worked with this artisan") and buttons `vouch.confirm` / cancel;
   - already sealed: calls `actions.vouch(c.id, artisan.id, true)` anyway, which the rules refuse as `duplicate` and the store logs as a security event; the UI shows `vouch.errDuplicate`.
4. "Seal vouch" runs `seal(candidateId)`: if the checkbox is not ticked it sets `vouch.errWorked` and does nothing else; otherwise `actions.vouch(candidateId, artisan.id, true)`. On `ok` it remembers `sealedFor`, closes the confirm box and resets the checkbox; the card then shows `vouch.done` ("Vouch sealed: VS-XXXXXXXX", `role="status"`).
5. "Vouches I sealed" (`vouch.mine`) lists all vouches where `voucherId === artisan.id` with their seal.
6. "Who vouched" (in the first card) lists vouches for the current artisan with a `seal-chip`.

### Operator side

1. `Operator` (PIN `1234` from `OPERATOR_PIN`) computes `pending = artisans.filter((a) => !a.rejected && !isVerified(a, ...))` and lists each with `operator.vouchCount` (valid vouch count capped at `VOUCHES_REQUIRED`) and two buttons: `operator.approve`, `operator.reject`. They call `actions.operator(a.id, approve)`.
2. `actions.operator` dispatches `{ type: 'operator', artisanId, approve, at, ids: ids(2) }`. The reducer sets `operatorApproved: true, rejected: false` for approve or `rejected: true` for reject; adds SMS `sms.verified` or `sms.rejected` and an audit entry `{ event: 'approved' | 'rejected', name }`.
3. The "Vouch ledger" card (`ledger.title`) runs `verifyLedger(state.vouches)`. If `ok` it shows the `ledger.intact` badge; otherwise `ledger.broken` with `n = ledger.index + 1` ("TAMPERING DETECTED at vouch n"). Below it, all vouches are listed as "voucher -> artisan" with the seal chip, or `ledger.empty`.
4. The audit table renders security events via the key `audit.${e.params.event}`, e.g. `audit.vouch_blocked`.

## File by file

### `apps/web/src/screens/ArtisanStatus.tsx`
Local state: `error` (simulate buttons), `confirming` (candidate id with open confirm box), `worked` (checkbox), `sealedFor`, `vouchError`. Derived: `count`, `verified`, `mine` (vouches received), `given` (vouches given), `justSealed`, `candidates`. Also contains the "Job inbox" (`artisanInbox`) and "My profile" (`profile`, with `{ profileId, back: 'artisanStatus' }`) navigation buttons and the logout link. Edge case: a click on an already-sealed candidate does not open the confirm box; it triggers the refusal path on purpose so the blocked attempt is logged.

### `apps/web/src/domain/rules.ts` (vouch part)
- `isTrusted(a)` (not exported): `!a.rejected && (a.seedVerified || !!a.operatorApproved)`.
- `checkVouch(artisan, voucher, workedTogether, existing, all = [artisan, voucher])` returns `{ ok: true }` or `{ ok: false, reason }` in this order:
  1. `self`: same id;
  2. `not_verified`: `!isVerified(voucher, existing, all)`;
  3. `same_phone`: same phone;
  4. `duplicate`: an existing vouch for this artisan has the same `voucherId` or the same `voucherPhone`;
  5. `no_job_together`: `workedTogether` is false.
- `countValidVouches(artisan, vouches, all, seen)`: counts distinct vouchers whose vouch has `workedTogether`, who exist, are not the artisan, do not share the artisan's phone, and are themselves verified (`isVerified(voucher, vouches, all, seen)`); a voucher counted once per id and once per phone.
- `isVerified(a, vouches, all, seen)`: `false` if rejected; `true` if trusted (seed or operator-approved); `false` if `a.id` is already in `seen` (a loop of artisans vouching for each other proves nothing); otherwise `countValidVouches(a, ..., new Set(seen).add(a.id)) >= VOUCHES_REQUIRED`.

### `apps/web/src/domain/security.ts` (ledger part)
- `GENESIS_HASH = '0'.repeat(16)`: the `prevHash` of the first vouch.
- `hasVouched(voucherId, artisanId, vouches)`: any vouch with that pair.
- `sealVouch(prevHash, artisanId, voucherId, at)` returns `{ prevHash, hash, seal }` where `hash = hashSecret(`${voucherId}>${artisanId}@${at}`, prevHash)` (the previous hash is used as the salt, which creates the chain) and `seal = 'VS-' + hash.slice(0, 8).toUpperCase()`.
- `lastHash(vouches)`: hash of the last vouch or `GENESIS_HASH`.
- `verifyLedger(vouches)`: walks the list; for index `i` returns `broken_chain` if `v.prevHash !== prev`, `bad_hash` if recomputing `sealVouch` does not equal `v.hash`, `duplicate_pair` if the `voucherId>artisanId` pair was seen before; otherwise `{ ok: true }`. The returned `index` is zero-based (the UI shows `index + 1`).
- The file header lists the four defence layers: rules, store action, reducer, ledger audit, plus the backend `UNIQUE(artisan_id, endorser_id)` constraint in API mode. The hash is demo-grade (see section 02).

### `apps/web/src/store/index.tsx` (vouch)
`VOUCH_ERRORS` maps rule reasons to keys: `self` -> `status.errSelf`, `not_verified` -> `status.errNotVerified`, `same_phone` -> `status.errSamePhone`, `duplicate` -> `vouch.errDuplicate`, `no_job_together` -> `status.errNoJob`. (`status.errDuplicate` exists in the dictionaries but is not used by this map.) Result type `VouchResult = { ok: true } | { ok: false; error: Key }`.

### `apps/web/src/store/reducer.ts` (vouch, vouchBlocked, operator)
- `vouchBlocked { artisanId, voucherId, at, id }`: only appends an audit entry `kind: 'security'`, `{ event: 'vouch_blocked', voucher: <name>, name: <artisan name> }`. No vouch is written.
- `vouch` and `operator`: described above. Event id slots in `vouch`: `ids[0]` SMS to artisan, `ids[1]` audit vouch, `ids[2]` SMS verified, `ids[3]` audit verified, `ids[4]` SMS to voucher.

### `apps/web/src/data/seed.ts`
`SEED_VOUCHERS = ['seed-1', 'seed-2'] as const`. Seeded artisans have `seedVerified: true`, except `seed-5` Samuel (`seedVerified: false`), the permanent "pending candidate" that appears in the operator list and in the vouch candidates list. Seeds start with no entries in `state.vouches`; seed artisans are verified by `isTrusted`, not by ledger entries.

### `apps/web/src/screens/Operator.tsx` (this section only)
Pending list, approve/reject, the ledger card. The rest of the screen (earnings, payments, trust scores, audit table, export, reset) belongs to other sections.

## Data and state

`Vouch` (types.ts): `id`, `artisanId` (who is vouched for), `voucherId`, `voucherPhone`, `workedTogether`, `at` (ISO time), `seal` (`VS-XXXXXXXX`), `prevHash`, `hash`. State: `state.vouches` (an append-only array, in order), `state.artisans[].operatorApproved` / `rejected`, `state.sms`, `state.audit`. Everything is persisted in `localStorage['acbridge.demo.v2']`. "Verified" is never stored; it is derived by `isVerified`.

## Rules and edge cases

- One vouch per (voucher, artisan) pair, forever, and also one per voucher phone: enforced in `checkVouch` (rules), again in the store action and the reducer, detected afterwards by `verifyLedger` (`duplicate_pair`). Repeat attempts are refused and recorded as a security audit event (store action dispatching `vouchBlocked`); message key `vouch.errDuplicate`.
- A voucher must be verified (`status.errNotVerified`), cannot be the artisan (`status.errSelf`), cannot share a phone (`status.errSamePhone`), and must attest a job done together (`status.errNoJob`; in the UI the checkbox error is `vouch.errWorked`).
- Two valid vouches from distinct verified people verify an artisan (`VOUCHES_REQUIRED = 2`). A rejected artisan is never verified.
- Vouches cannot be withdrawn: there is no remove action in the reducer.
- Chain integrity: any edited, removed, reordered or duplicated vouch breaks `verifyLedger` and the operator sees `ledger.broken`. Nothing in the demo UI lets a user edit a vouch, but the stored JSON can be edited by hand.
- Bug fixed in commit `f070723` "Fix: a verified artisan (verified through vouches) can now vouch for others": previously `checkVouch` and `countValidVouches` used only `isTrusted(voucher)` (seed-verified or operator-approved), so an artisan who became verified through two vouches could not vouch for anyone and their vouches did not count. Now both use `isVerified(voucher, existing, all)`. To keep this safe, `isVerified` and `countValidVouches` take a `seen` set so a cycle of artisans vouching for each other counts for nothing, and `checkVouch` gained an `all` argument; `store/index.tsx` and `store/reducer.ts` were changed to pass `s.artisans`. The test file `vouch-chain.test.ts` was added with that commit.
- `operator` approve/reject has no refusal rules: it applies to any listed artisan.

## Tests

- `apps/web/src/__tests__/vouch-chain.test.ts`, describe "an artisan who became verified through vouches can vouch too":
  - "Joel is verified by two seed artisans, then his vouch for Ana goes through and counts": reducer-level; Joel verified by `seed-1` and `seed-2`; Joel vouches for Ana (one vouch recorded, `sms.vouchSealed` sent to Joel, Ana not yet verified); a vouch from `seed-1` verifies Ana.
  - "an artisan who is NOT verified yet still cannot vouch, and vouch loops prove nothing": unverified `a` cannot vouch for `b`; after one vouch for `a` it still cannot.
- `apps/web/src/__tests__/rules.test.ts`, describe "verification": "one vouch does not verify; the second valid vouch does"; "rejects self, unverified, same-phone, duplicate and no-job vouches" (including pending Samuel as `not_verified`); "counts distinct vouchers only, even if the same voucher is recorded twice".
- `apps/web/src/__tests__/security-money.test.ts`, describe "Vouch Seal ledger": "chains every vouch to the previous one and verifies clean" (first `prevHash` is `GENESIS_HASH`, seal matches `/^VS-[0-9A-F]{8}$/`, empty ledger is ok); "detects tampering: edited, deleted, reordered and duplicated vouches" (`bad_hash` at 0, `broken_chain` at 1, `duplicate_pair` at 3); "refuses a second vouch for the same pair (and the same phone) in the rules layer" (`hasVouched`, `checkVouch` returns `duplicate`, also for a clone with the same phone).
- `apps/web/src/__tests__/ui-flows.test.tsx`: the full journey test clicks "Simuler garantie 1" (expects "1 sur 2 garanties" and no verified message), "Simuler garantie 2" (expects "2 sur 2 garanties", SMS "vous êtes maintenant vérifié" and `Sceau VS-XXXXXXXX`). "an artisan can vouch for another only once: sealed, refused on a second try, logged and chained": logs in as `grace`, opens the confirm box ("C'est définitif"), tries without the checkbox ("Cochez la case"), seals (`Garantie scellée : VS-...`, chip "Scellé"), clicks again ("Garantie refusée"), checks exactly one stored vouch, then in the operator panel expects "Chaîne intacte" and "BLOQUÉ : Grace a essayé de garantir Ana une deuxième fois". The free-text-trade test also uses both simulate buttons.

## Backend connection

In API mode (`apps/web/src/api/bridge.ts`), after the local vouch succeeds:
- `bridge.vouch(artisan, voucher)`: logs in as the voucher (`login(voucher.phone)`, `POST /auth/login`) and calls `POST /artisans/{remoteId}/endorsements` with an `evidence_description` text ("<voucher> worked with <artisan> on <trade> jobs in <neighbourhood>."). The store first waits (`waitForRemote`, up to 40 x 150 ms) until the registration mirror has stored `remoteId` on the artisan.
- When the number of local vouches for the artisan (`vouches.filter(v => v.artisanId === artisanId).length`) reaches 2, `bridge.verifyAfterVouches(artisan)`: artisan `POST /verifications` (SKILL check), then a simulated verifier (`VERIFIER_PHONE = '+237670000002'`) calls `POST /verifications/{id}/decision` with `UNDER_REVIEW` then `APPROVED` ("SIMULATED: demo approval after 2 vouches").
- Operator approve/reject: `bridge.operatorDecision` submits a check and the simulated verifier decides `APPROVED` or `REJECTED`.
- The backend rule mirrored is "endorsement" with `UNIQUE(artisan_id, endorser_id)` as final guard (per the comment in `security.ts`). The seal ledger (hash chain, `VS-` codes, `vouchBlocked` audit) exists only in the front end; the backend has no equivalent.
- Backend failures are shown as a notice; the local demo keeps working.

## Known limits and what changes in the production rebuild

- The two "Simulate vouch" buttons let the artisan vouch for themselves through the seeded artisans; real verification would require real people answering the `sms.vouchRequest` SMS.
- The verifier and operator decisions are simulated; the demo operator PIN is hardcoded (`1234`).
- The chain is demo-grade: it makes casual tampering visible but a user who can edit `localStorage` can recompute every hash, because the hash function and salt rule are public and there is no secret key or server anchor. A production version would store the chain on the server (or sign entries) and verify there.
- `workedTogether` is a self-declared checkbox; there is no proof of a shared completed job.
- Verification counts only `workedTogether` vouches from verified people, but the API-mode mirror triggers `verifyAfterVouches` from the raw count (2 recorded vouches), not from `countValidVouches`.
- `seed-5` Samuel is a fixed demo candidate; his vouches would come only from artisans using the panel.
