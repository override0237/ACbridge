# Languages and speech

The app is bilingual: French is the default and English is one tap away (the "FR" / "EN" toggle in the header). Every visible string comes from a dictionary, and the choice is remembered after a refresh. Each screen has a short spoken-style instruction with a "Listen" button that reads the title and instruction aloud in the selected language, and the artisan sign-up form has an optional microphone button to dictate the description.

This section covers the shared dictionaries and `translate()` in `packages/core`, the web re-export shim, the language toggle, the read-aloud button, the shared screen frame that hosts it, speech recognition on the sign-up form, and how the language is persisted.

## Files

| File | Role |
|---|---|
| `packages/core/src/i18n/en.ts` | English dictionary (`en`, `as const`) and the `Dict` type derived from it (`Record<keyof typeof en, string>`). About 399 keys. |
| `packages/core/src/i18n/fr.ts` | French dictionary, typed as `Dict`, so a missing or extra key is a compile error. |
| `packages/core/src/i18n/local.ts` | Placeholder `Partial<Dict>` for one future local language; empty today. |
| `packages/core/src/i18n/index.ts` | `Key`, `Params`, `dictionaries`, `translate`, `speechLocale`. |
| `packages/core/src/i18n/i18n.test.ts` | Tests: identical keys, no empty strings, local fallback, interpolation. |
| `packages/core/src/index.ts` | Re-exports `./i18n` (so apps import from `@acbridge/core`). |
| `apps/web/src/i18n/index.ts` | One-line shim: `export { dictionaries, translate, speechLocale, type Key, type Params } from '@acbridge/core'`. |
| `apps/web/src/i18n/trade.ts` | `tradeLabel`: language-aware display name of a trade (catalogue key or free text). |
| `apps/web/src/i18n/format.ts` | `renderParams` / `money` (see section 12); formats values for display in the current language. |
| `apps/web/src/components/LanguageToggle.tsx` | The FR / EN button group in the header. |
| `apps/web/src/components/SpeakButton.tsx` | Read-aloud button using `speechSynthesis`; renders nothing if unsupported. |
| `apps/web/src/components/Screen.tsx` | Shared screen frame: back button, `<h1>`, instruction paragraph and the `SpeakButton`. |
| `apps/web/src/screens/ArtisanSignup.tsx` | Optional microphone button using the Web Speech API recognition. |
| `apps/web/src/store/persistence.ts` | `STORAGE_KEY`, `loadState`, `saveState`, `clearState`; `State.lang` is part of the persisted state. |
| `apps/web/src/store/reducer.ts` | `State.lang`, the `setLang` action, `initialState().lang = 'fr'`. |
| `apps/web/src/App.tsx` | Mounts `LanguageToggle`; its `loadLang()` reads the saved language for the "connect backend" prompt. |

## How it works

1. `Lang` is `'fr' | 'en'` (from `packages/core/src/types`). `State.lang` holds the current choice; `initialState()` sets it to `'fr'`.
2. In `StoreProvider` (see section 14) the translator for components is built as `t = (key, params) => translate(state.lang, key, params)`, memoised on `state.lang`. Every component gets `t` from `useStore()`.
3. `translate(lang, key, params)` looks up `dictionaries[lang][key]`, falls back to `fr[key]`, then to the key string itself, then replaces every `{name}` placeholder using `text.split('{name}').join(String(value))`.
4. The user taps FR or EN in `LanguageToggle`. The button calls `actions.setLang(l)`, which dispatches `{ type: 'setLang', lang }`; the reducer returns `{ ...s, lang: a.lang }`. Nothing else changes, so a language switch never loses data.
5. The store's `useEffect(() => saveState(state), [state])` writes the whole state, including `lang`, to `localStorage` under `acbridge.demo.v2`. On the next load `loadState()` restores it. `reset` keeps the current language: `{ type: 'reset', lang }` returns `{ ...initialState(), lang: a.lang }`.
6. Stored values that contain language-dependent data (SMS, chat system lines, audit entries) keep `{ key, params }` and are translated at render time, so old entries change language too.
7. Each screen wraps its content in `Screen` with a `title` and `instruction` already translated (for example `t('home.instruction')`). `Screen` renders `<SpeakButton text={`${title}. ${instruction}`} />` next to the instruction.
8. `SpeakButton` checks `supported()`. If `speechSynthesis` or `SpeechSynthesisUtterance` are missing it returns `null` (no button). Otherwise, on click it cancels any current speech, creates an utterance with `u.lang = speechLocale[state.lang]` (`fr-FR` or `en-US`), and calls `synth.speak(u)`. Clicking again while speaking cancels.
9. On the artisan sign-up screen, if the browser exposes `SpeechRecognition` or `webkitSpeechRecognition`, a "Speak (optional)" button appears. Pressing it starts recognition in `speechLocale[state.lang]`; the transcript is appended to the description text area.

## File by file

### `packages/core/src/i18n/en.ts` and `fr.ts`

- `en` is a plain object literal declared `as const`; `export type Dict = Record<keyof typeof en, string>` is derived from it. `fr` is declared `export const fr: Dict = { ... }`.
- Consequence: the English file is the source of truth for the set of keys. TypeScript rejects `fr` if a key is missing or misspelled. The test (below) also checks the key sets at runtime.
- Keys are namespaced by screen or feature with dots: `app.*`, `mode.*`, `common.*`, `lang.*`, `speak.*`, `footer.*`, `urgency.*`, `home.*`, `signup.*`, `status.*`, `login.*`, `request.*`, `trade.*`, `sms.*`, `chat.*`, `pay.*`, `acct.*`, `opay.*` and so on.
- Placeholders use single braces: `'common.jobs': '{n} jobs'`, `'status.count'` uses `{n}` and `{total}`.
- Speech-related strings: `speak.play` ("Listen" / "Écouter"), `speak.stop` ("Stop" / "Arrêter"), `signup.mic` ("Parler (facultatif)"), `signup.micOn` ("Écoute…").
- Rule: user-facing text is placed in these dictionaries, never hard-coded in components. Components call `t('some.key')`. (Some small demo-only developer strings may still exist in components; the rule applies to everything a user reads.)

### `packages/core/src/i18n/local.ts`

- `export const local: Partial<Dict> = {};`
- Reserved for ONE local language (for example Pidgin or Ewondo). `dictionaries.local` is `{ ...fr, ...local }`, so any missing key falls back to French. It is not shown in the toggle and `Lang` does not include it yet; `translate` accepts `Lang | 'local'` already.

### `packages/core/src/i18n/index.ts`

| Export | Type / behaviour |
|---|---|
| `Key` | `keyof Dict`: only existing dictionary keys type-check in `t('...')`. |
| `Params` | `Record<string, string \| number>`. |
| `en`, `fr`, `local`, `Dict` | Re-exported. |
| `dictionaries` | `Record<Lang \| 'local', Dict>` = `{ fr, en, local: { ...fr, ...local } }`. |
| `translate(lang, key, params?)` | Returns the text with `{placeholders}` filled. Fallback order: selected language, then French, then the key itself. A placeholder with no matching param stays as `{name}`. |
| `speechLocale` | `Record<Lang, string>` = `{ fr: 'fr-FR', en: 'en-US' }`; used by both speech synthesis and recognition. |

### `packages/core/src/i18n/i18n.test.ts`

See Tests below.

### `apps/web/src/i18n/index.ts`

A re-export shim so web code imports `from '../i18n'` while the implementation lives in the shared package. It exports only `dictionaries`, `translate`, `speechLocale`, `Key`, `Params`.

### `apps/web/src/i18n/trade.ts`

`tradeLabel(t, trade)`: if `isCatalogueTrade(trade)` (one of `plumbing`, `electrical`, `carpentry`, `masonry`, `mechanics`, `tailoring`, `hairdressing`) it returns `t('trade.<key>')` ("Plumber" / French equivalent); otherwise it returns the free text with the first letter capitalised. Trades typed by users in either language are normalised to a catalogue key by `resolveTrade` in `apps/web/src/domain/trades.ts` (aliases such as `plombier`, `electricien`), which is why a French or English entry both end up as the same stored key.

### `apps/web/src/components/LanguageToggle.tsx`

- Renders `<div className="lang" role="group" aria-label={t('lang.label')}>` with two buttons (`fr`, `en`).
- The active one gets `aria-pressed={true}` and the `active` class. Labels come from `lang.fr` and `lang.en` ("FR", "EN").
- Click calls `actions.setLang(l)`.

### `apps/web/src/components/SpeakButton.tsx`

- Props: `{ text: string }`. Local state: `speaking`.
- `supported()` is `typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window`. It is evaluated on each render; when false the component returns `null` after calling its hooks (hooks run before the early return).
- `toggle()` is wrapped in `try/catch`; on error it resets `speaking` so speech problems never break a screen. `u.onend` and `u.onerror` reset `speaking`.
- The button has a visible word (`speak.play` or `speak.stop`) plus an emoji marked `aria-hidden`; `aria-label` mirrors the word.
- It always calls `synth.cancel()` before speaking so two readings never overlap.

### `apps/web/src/components/Screen.tsx`

- Props: `title`, `instruction`, optional `back` (a screen name), `children`.
- Renders an optional ghost back button, `<h1>{title}</h1>`, and `<div className="instruction"><p>{instruction}</p><SpeakButton .../></div>`.
- The spoken text is the title and the instruction joined with ". ". The target audience may have low literacy, which is why each screen has one short instruction that can be heard.

### `apps/web/src/screens/ArtisanSignup.tsx` (microphone only)

- `getRecognition()` returns `window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null`. The `Recognition` type is declared loosely by hand (`lang`, `onresult`, `onend`, `start`, `stop`) because the API is vendor-prefixed and not in the default TypeScript DOM typings.
- The microphone button is rendered only when `Rec` is non-null: `{Rec && <Button ... label={listening ? t('signup.micOn') : t('signup.mic')} onClick={mic} />}`.
- `mic()`: if already `listening`, it stops the recognizer. Otherwise it creates `new Rec()`, sets `r.lang = speechLocale[state.lang]`, sets `r.onresult` to append `ev.results[0][0].transcript` to `description` (`` `${d} ${transcript}`.trim() ``), sets `r.onend` to clear `listening`, stores it in a ref, sets `listening` true and calls `r.start()`. A `catch` resets `listening`.
- Only the first alternative of the first result is used. The result is editable text in the same `<textarea>`, and no audio is stored.

### `apps/web/src/store/persistence.ts` (language only)

- `STORAGE_KEY = 'acbridge.demo.v2'`. `loadState()` parses JSON and returns `{ ...initialState(), ...parsed }` if `parsed.v === 1` and `artisans` is an array, otherwise `initialState()` (so `lang: 'fr'`).
- `App.tsx` has a separate small `loadLang()` that reads only `.lang` from the same key; it is used so the "Backend address" prompt (`footer.connectAsk`) is shown in the saved language before the page reloads.

## Data and state

| Item | Where | Persisted |
|---|---|---|
| `State.lang: 'fr' \| 'en'` | `apps/web/src/store/reducer.ts` | Yes, inside `acbridge.demo.v2` in `localStorage`. |
| `Dict`, `Key` | `packages/core/src/i18n` | Code only. |
| `speaking` (SpeakButton), `listening` (ArtisanSignup) | Component `useState` | No. |
| `SmsMessage.key/params`, `ChatMessage.key/params`, `AuditEntry.params` | State | Yes: store keys, not translated text. |

Reading: components read `state.lang` and `t`. Writing: only `setLang` and `reset` (preserves the language).

## Rules and edge cases

- Fallback: a key missing in the selected language shows French, and a key missing everywhere shows the key text. In practice the identical-keys test makes `fr`/`en` complete.
- `Key` is a compile-time check: `t('typo.key')` does not compile. Where a key is built dynamically the code casts (`t(`urgency.${v}` as Key)`), so those need care.
- Placeholders are replaced by plain string splitting, not a template engine: the same placeholder can appear several times, and params with no placeholder are ignored.
- No plural system: texts that depend on a count are written as `"{n} jobs"` or similar.
- Numbers and dates are not part of the dictionaries: money uses `formatAmount` (`9 000` in French, `9,000` in English); the SMS panel time uses the browser locale.
- Speech is progressive enhancement: no `speechSynthesis` means no button; no recognition API means no microphone button. Failures are swallowed so the form keeps working.
- Speech synthesis voices depend on the device; if no `fr-FR` voice is installed the browser may read with a default voice.
- `index.html` has a fixed `<html lang="fr">`; the code in `apps/web/src` does not update the document `lang` attribute when the language changes (see limits).

## Tests

| File | Test | What it checks |
|---|---|---|
| `packages/core/src/i18n/i18n.test.ts` | "fr and en have identical keys" | `Object.keys(fr).sort()` equals `Object.keys(en).sort()`. |
| same | "has no empty strings" | No value in `fr` or `en` is empty. |
| same | "local slot falls back to French and interpolates" | `dictionaries.local['home.title']` equals `fr['home.title']`; `translate('en', 'status.count', { n: 1, total: 2 })` is `'1 of 2 vouches'`. |
| `apps/web/src/__tests__/ui-flows.test.tsx` | "registers, gets vouched, ... " (full journey) | Clicks the `EN` button and checks the screen and SMS panel re-render in English ("Audit log", "To: +237", "you are now verified") while state is kept. |
| same | "survives a refresh (localStorage) and Reset demo clears it" | Persistence of the stored state (includes `lang`). |

There is no automated test for `SpeakButton` or the microphone button (browser speech APIs are not available in the jsdom/node test environments).

## Backend connection

None (local only). The backend does not translate UI text. `lang` is not sent to the API; backend error messages shown in the notice bar (`mode.api` prefix) are whatever the server returns.

## Known limits and what changes in the production rebuild

- Only two languages are live. The `local` slot is empty, `Lang` does not include it, and there is no UI to select it.
- The document `<html lang>` is fixed to `fr` in `apps/web/index.html`; a production build should set `document.documentElement.lang` when the language changes (screen readers pick the voice from it).
- The SMS panel is shown in the viewer's language rather than the recipient's (see section 12).
- Speech quality and availability depend on the browser and installed voices; there is no fallback to pre-recorded audio, which low-connectivity users may need.
- The microphone feature sends audio to whatever speech service the browser uses (often a cloud service); no consent or privacy text is shown in the demo.
- Dictionaries are two large TypeScript objects loaded with the app. A production rebuild may split them per screen or load per language, and move translation work to a translation platform while keeping the typed `Key` and the identical-keys test.
- The mobile scaffold (`apps/mobile`) does not use these dictionaries yet; both apps can share them because `packages/core` has no platform dependencies.
