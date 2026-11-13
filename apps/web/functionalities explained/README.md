# ACbridge web app: functionalities explained

These documents explain how each part of the ACbridge web demo (`apps/web`, with shared code in `packages/core` and `packages/tokens`) was implemented and how it behaves, file by file. They are written for a developer who has never seen the codebase. Each folder holds one `README.md` with the same nine headings (summary, files, how it works, file by file, data and state, rules and edge cases, tests, backend connection, known limits and production rebuild).

## The 15 sections

| # | Section | What it covers | Primary files |
|---|---|---|---|
| 01 | [Home and navigation](./01-home-and-navigation/README.md) | Landing screen, screen routing, header and footer | `apps/web/src/App.tsx`, `screens/Home.tsx`, `store/reducer.ts` (`nav`) |
| 02 | [Artisan accounts](./02-artisan-accounts/README.md) | Sign-up, login, credentials | `screens/ArtisanSignup.tsx`, `ArtisanLogin.tsx`, `domain/security.ts` |
| 03 | [Verification and Vouch Seal](./03-verification-and-vouch-seal/README.md) | Two vouches, sealed hash chain, verification status | `screens/ArtisanStatus.tsx`, `domain/rules.ts`, `domain/security.ts` |
| 04 | [Trades and customer requests](./04-trades-and-customer-requests/README.md) | Trade catalogue and free-text trades, creating a request | `domain/trades.ts`, `screens/CustomerRequest.tsx`, `components/TradeField.tsx` |
| 05 | [Matching and ranking](./05-matching-and-ranking/README.md) | Which artisans are shown and in which order | `screens/Matches.tsx`, `domain/rules.ts` |
| 06 | [Connect flexibly (chat)](./06-connect-flexibly-chat/README.md) | Customer-artisan chat, contact masking, price in chat | `screens/Chat.tsx`, `domain/chat.ts` |
| 07 | [Job offers and expiry](./07-job-offers-and-expiry/README.md) | Offer inbox, YES/NO, deadlines and expiry | `screens/ArtisanInbox.tsx`, `domain/offers.ts`, `store/reducer.ts` (`expireStale`) |
| 08 | [Job tracking and completion](./08-job-tracking-and-completion/README.md) | Job status tracking, 6-digit job code, completion | `screens/Tracking.tsx`, `screens/ArtisanComplete.tsx`, `domain/rules.ts` |
| 09 | [Payments](./09-payments/README.md) | Sandbox payment, commission, ledger, payouts | `screens/Payments.tsx`, `domain/ledger.ts`, `domain/money.ts` |
| 10 | [Ratings and profiles](./10-ratings-and-profiles/README.md) | Rating after a job, trust score, artisan profile | `screens/Rate.tsx`, `screens/ArtisanProfile.tsx`, `components/StarRating.tsx` |
| 11 | [Operator panel and database export](./11-operator-panel-and-database-export/README.md) | PIN-protected operator view, audit log, export | `screens/Operator.tsx`, `components/OperatorPayments.tsx`, `domain/export.ts` |
| 12 | [SMS log and notifications](./12-sms-log-and-notifications/README.md) | Simulated SMS panel and every message the reducer creates | `components/SmsLog.tsx`, `i18n/format.ts`, `store/reducer.ts` |
| 13 | [Languages and speech](./13-languages-and-speech/README.md) | French/English dictionaries, `translate`, read-aloud, dictation | `packages/core/src/i18n/*`, `components/SpeakButton.tsx`, `LanguageToggle.tsx` |
| 14 | [State, persistence and API bridge](./14-state-persistence-and-api-bridge/README.md) | Single reducer store, `localStorage`, optional backend mirroring, build | `store/reducer.ts`, `store/index.tsx`, `api/bridge.ts`, `config.ts`, `scripts/inline.mjs` |
| 15 | [Design system and monorepo](./15-design-system-and-monorepo/README.md) | Tokens, contrast checks, UI primitives, style guide, mobile scaffold | `packages/tokens/src/*`, `components/ui/*`, `scripts/*.ts` |

Paths in the "Primary files" column are relative to `apps/web/src` unless they start with `packages/`, `scripts/` or `apps/`. The files listed for sections 01 to 11 are indicative; each section's own README has the authoritative list.

## How the app fits together

```
 screens (apps/web/src/screens/*)         React components, one per Screen name
        |  call actions.xxx(...)  and  read state / t(...)
        v
 store (apps/web/src/store/index.tsx)     StoreProvider: validates input, generates ids/timestamps/codes
        |  dispatch({ type, ..., at, ids })
        v
 reducer (apps/web/src/store/reducer.ts)  pure: State + Action -> State (re-validates every rule)
        |  uses
        v
 domain rules (apps/web/src/domain/*)     checkVouch, checkPayStart, checkChatMessage, checkCompletion,
        |                                  checkRating, computeCommission, ledger, offers, security (hashing, seals)
        v
 i18n (packages/core/src/i18n, apps/web/src/i18n)   text is stored as keys + params and translated at render time

 optional:  store/index.tsx --mirror--> api/bridge.ts --> api/client.ts --> FastAPI backend (backend/)
```

1. A screen shows data from `state` and text from `t(key, params)`. `state.ui.screen` decides which screen component `App.tsx` renders.
2. A user action calls a method on the `actions` object. It validates, creates the impure values (ids, ISO time, job code), and dispatches a reducer action.
3. The reducer is pure and applies the domain rules again; it appends SMS, chat system lines and audit entries as `{ key, params }` so they re-render in the selected language.
4. After each change the whole state is saved to `localStorage` (`acbridge.demo.v2`), so a refresh restores it. "Reset demo" clears it.
5. In API mode (`?api=<url>` or `VITE_API_MODE=api`) the store also replays key steps on the backend through `api/bridge.ts`; if a call fails the demo keeps working locally and shows a notice.
6. Visual styling comes from `styles.css` (legacy) and, for the new foundation, from design tokens in `packages/tokens` and the primitives in `components/ui`.
7. Everything involving people, SMS, verification and money is simulated; nothing real is sent or charged.

## How to read these documents

- Start with this page, then section 14 (state and store), because every other section is a slice of the reducer and the `actions` object.
- Each section README begins with what the user sees, then a files table, then a numbered "How it works" that names real functions and reducer actions in execution order. "File by file" has the details and edge cases.
- "Tests" cites real test names so you can run or read them (`pnpm test`, or `npm run test` inside `apps/web`).
- "Backend connection" says which backend routes or rules the section mirrors in API mode, or "none (local only)".
- "Known limits and what changes in the production rebuild" is deliberately honest: it lists what the demo simulates and what the production product must do differently.
- Code names in backticks (`checkVouch`, `paySettle`, `sms.jobCode`) can be searched directly in the repository.
