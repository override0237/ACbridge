# Home and navigation

When the app opens the user sees a header with the ACbridge brand and an FR/EN switch, a yellow banner saying the demo is simulated (and whether it is offline or connected to a backend), the current screen, a side panel listing every simulated SMS, and a footer. The Home screen offers two big buttons: "I am an artisan" and "I need a service" (plus "My job" once a job exists). Every other screen is reached by changing one field in the app state; there is no URL routing.

## Files

| File | Role |
|---|---|
| `apps/web/src/main.tsx` | Browser entry point: loads the design tokens and `styles.css`, mounts `<App />` inside `<StrictMode>`. |
| `apps/web/src/App.tsx` | Defines the `SCREENS` map, the `Shell` layout (header, banner, notice, main, SMS panel, footer), the backend toggle and wraps everything in `StoreProvider`. |
| `apps/web/src/screens/Home.tsx` | The landing screen with the artisan / customer / track-job buttons. |
| `apps/web/src/components/Screen.tsx` | Common frame of every screen: optional Back button, `<h1>`, spoken instruction and listen button. |
| `apps/web/src/components/LanguageToggle.tsx` | The FR / EN buttons in the header. |
| `apps/web/src/components/SpeakButton.tsx` | "Listen" button using the browser `speechSynthesis` API. |
| `apps/web/src/components/Button.tsx` | The one button component (icon + short label, four variants, `big` size). |
| `apps/web/src/components/Card.tsx` | `Card` container and `Badge` status chip. |
| `apps/web/src/components/SmsLog.tsx` | The SMS side panel shown by the shell (listed here because the shell renders it; the SMS content itself belongs to the features that send SMS). |
| `apps/web/src/store/reducer.ts` | `Screen` type, `UiState`, `initialState`, and the `nav`, `setLang`, `login`, `logout` cases. |
| `apps/web/src/store/index.tsx` | `StoreProvider`, `useStore`, and the `go` / `setLang` actions; also persistence and `notice`. |
| `apps/web/src/store/persistence.ts` | `STORAGE_KEY` (`acbridge.demo.v2`), `loadState`, `saveState`, `clearState`. |
| `apps/web/src/config.ts` | `readApiBase()`, `API_BASE`, `API_MODE`: decides between offline demo and API mode. |
| `apps/web/src/styles.css` | Layout, header, banner, language switch, buttons, cards and the responsive SMS panel. |
| `packages/core/src/i18n/fr.ts`, `en.ts` | Text of the keys used here (`app.demo`, `mode.*`, `footer.*`, `lang.*`, `speak.*`, `home.*`, `common.*`). |

## How it works

1. `index.html` contains `<div id="root">` and loads `/src/main.tsx` as a module.
2. `main.tsx` imports `@acbridge/tokens/css` (design tokens) and `./styles.css`, then calls `createRoot(...).render(<StrictMode><App /></StrictMode>)`.
3. `App` renders `<StoreProvider><Shell /></StoreProvider>`.
4. `StoreProvider` runs `useReducer(reducer, undefined, loadState)`. `loadState()` reads `localStorage['acbridge.demo.v2']`; if the data is missing, invalid (`v !== 1`) or throws, it returns `initialState()`. The initial UI is `{ screen: 'home', actingArtisanId: null, requestId: null, jobId: null, profileId: null, back: 'home' }`. Every state change is saved by `useEffect(() => saveState(state), [state])`. So a page refresh returns to the screen the user was on.
5. `Shell` calls `useStore()` and picks the component: `const Current = SCREENS[state.ui.screen] ?? Home;`. The `?? Home` fallback protects against a stale or unknown value in saved state.
6. `Shell` renders, in order: `<header class="top">` (brand button calling `actions.go('home')`, then `<LanguageToggle />`), the demo banner, an optional error `notice`, `<div class="layout">` containing `<main><Current /></main>` and `<SmsLog />`, and the footer.
7. A screen changes the screen by calling `actions.go(screen, patch?)`. In `store/index.tsx` this is `dispatch({ type: 'nav', screen, patch })`. The reducer case is:

```ts
case 'nav':
  return { ...s, ui: { ...s.ui, ...a.patch, screen: a.screen } };
```

   `patch` is a `Partial<UiState>` merged first, then `screen` is set last, so the patch cannot override the destination. Example from `ArtisanStatus`: `actions.go('profile', { profileId: artisan.id, back: 'artisanStatus' })`.
8. Because `Current` is chosen from state, React unmounts the old screen and mounts the new one. Local `useState` inside a screen (form fields, errors) is therefore lost on every navigation, while everything in the reducer state survives.

### Home screen decision

`Home` reads `hasArtisan = state.ui.actingArtisanId !== null`. The artisan button goes to `artisanStatus` when someone is already logged in, otherwise to `artisanEntry`. The customer button goes to `customerRequest`. The ghost "My job" button (`home.track`) is only rendered when `state.ui.jobId` is set and goes to `tracking`.

### Language toggle

1. `LanguageToggle` renders one button per language from `['fr','en']`, with `aria-pressed` and class `lang-btn active` for the current one.
2. Click calls `actions.setLang(l)` which dispatches `{ type: 'setLang', lang }`; the reducer does `{ ...s, lang }`.
3. `t` in the context is `useCallback((key, params) => translate(state.lang, key, params), [state.lang])`, so every component that calls `useStore()` re-renders in the new language. The language is part of `State` and is therefore persisted with it.
4. The SMS log stores i18n keys and params (not text), so already-sent SMS re-render in the new language too.

### Demo-mode / API-mode banner and "Connect backend"

1. `config.ts` runs `readApiBase()` once at module load:
   - reads `?api=` from `window.location.search`;
   - `?api=off` removes `localStorage['acbridge.api']` and returns `null`;
   - `?api=<url>` stores the URL (trailing slashes removed) in `localStorage['acbridge.api']`;
   - otherwise returns the stored URL if any;
   - otherwise returns `'/api'` when the build variable `VITE_API_MODE === 'api'`, else `null`;
   - the whole body is in `try/catch`, so blocked storage falls through to the env check.
2. `API_BASE` is that value and `API_MODE = API_BASE ? 'api' : 'local'`.
3. The banner is `{t('app.demo')} · {API_MODE === 'api' ? t('mode.api') : t('mode.local')}`. French texts: "Démo : personnes, SMS et vérification sont simulés." and "Démo hors ligne" / "Connecté au serveur".
4. The footer button shows `footer.disconnect` ("Go offline") in API mode and `footer.connect` ("Connect backend") otherwise. Its handler `toggleBackend`:

```ts
const next = API_MODE === 'api' ? 'off' : window.prompt(translate(loadLang(), 'footer.connectAsk'), 'http://localhost:8000');
if (!next) return;
const url = new URL(window.location.href);
url.searchParams.set('api', next);
window.location.href = url.toString();
```

   It asks for the address (default `http://localhost:8000`), puts it in the `api` query parameter and reloads the page; `config.ts` then picks it up on the next load. Cancelling the prompt (empty or null) does nothing.
5. A second footer button calls `actions.go('operator')` (label `footer.operator`). There is no link to the operator panel anywhere else.

## File by file

### `apps/web/src/main.tsx`
Eleven lines. Only mounts the app. `document.getElementById('root')!` is a non-null assertion; the element exists in `index.html`. `StrictMode` means effects run twice in development (the sweep and pending-payment effects in `StoreProvider` are written to tolerate this).

### `apps/web/src/App.tsx`
- `SCREENS: Record<Screen, ComponentType>`: maps all 15 `Screen` values to a component: `home`, `artisanEntry`, `artisanLogin`, `artisanSignup`, `artisanStatus`, `artisanInbox`, `artisanComplete`, `customerRequest`, `matches`, `tracking`, `chat`, `payments`, `rate`, `operator`, `profile` (the last maps to `ArtisanProfile`). Because the type is `Record<Screen, ...>`, TypeScript fails the build if a new `Screen` is added without a component.
- `toggleBackend()`: described above. `loadLang()` is a small local helper that reads `lang` directly from the persisted JSON in `localStorage` (default `'fr'`), because `toggleBackend` is outside the React tree and cannot use `useStore`.
- `Shell`: pulls `state, actions, t, notice, clearNotice` from `useStore()`. The `notice` paragraph (`role="alert"`, class `error`) appears when API-mode mirroring fails (set by `mirror()` in the store) and has a Close button (`common.close`).
- `App`: wraps `Shell` in `StoreProvider`. The footer note text is `footer.note` ("ACbridge demo · Team OVERRIDE").

### `apps/web/src/screens/Home.tsx`
Uses `Screen` with `home.title` and `home.instruction`. Three `Button`s as described. Hints under the buttons use `home.artisanHint` and `home.customerHint`. Note: `Home` has no `back` prop, so no Back button is shown.

### `apps/web/src/components/Screen.tsx`
Props: `title`, `instruction`, `back?: Screen`, `children`. Renders a Back button (`common.back`, ghost variant, icon arrow) only if `back` is given; it calls `actions.go(back)` (fixed target, not browser history). Then `<h1>{title}</h1>` and a `div.instruction` with the instruction paragraph and `<SpeakButton text={`${title}. ${instruction}`} />`. So every screen announces its title and instruction aloud, which is the app's accessibility approach for low-literacy users.

### `apps/web/src/components/LanguageToggle.tsx`
Group with `role="group"` and `aria-label={t('lang.label')}`. Labels come from `lang.fr` and `lang.en` ("FR", "EN"). Only French and English are offered; `packages/core/src/i18n/local.ts` is an empty placeholder for a future local language and is not shown.

### `apps/web/src/components/SpeakButton.tsx`
- `supported()` checks `'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window`. If false the component returns `null` (nothing rendered).
- `toggle()`: if already speaking, `synth.cancel()` and stop; otherwise cancel any previous speech, build a `SpeechSynthesisUtterance(text)`, set `u.lang = speechLocale[state.lang]`, set `onend`/`onerror` to reset the `speaking` state, and `synth.speak(u)`. Everything is wrapped in `try/catch` so speech can never break a screen.
- Label and icon switch between `speak.play` ("Listen") with a speaker icon and `speak.stop` ("Stop").

### `apps/web/src/components/Button.tsx`
Props: `icon` (required string), `label` (required), `variant` (`'primary' | 'secondary' | 'danger' | 'ghost'`, default `primary`), `big`, plus any native button attribute except `children`. Default `type="button"` so buttons inside forms do not submit unless `type="submit"` is passed. Output classes: `btn btn-<variant> [btn-big]`. The icon is `aria-hidden`; the comment in the source states the convention: every action has an icon and a short label (max three words).

### `apps/web/src/components/Card.tsx`
`Card({ children, highlight, as, className })` renders a `section` (or `article` / `div`) with class `card` and optionally `card-highlight`. `Badge({ icon, text, tone })` renders a chip with tone `good | warn | bad | info`; the comment says status is never shown by colour alone (icon + text + colour).

### `apps/web/src/store/reducer.ts` (navigation part only)
- `Screen`: string union of the 15 screens (see above).
- `UiState`: `screen`, `actingArtisanId`, `requestId`, `jobId`, `profileId`, `back`, optional `loginNext`, optional `chatAs`.
- `nav` action: `{ type: 'nav'; screen: Screen; patch?: Partial<UiState> }`.
- `login` sets `screen` to `a.next`; `logout` sets `actingArtisanId: null`, `loginNext: null`, `screen: 'home'`. `register` and `request` and `choose` also set `ui.screen` directly (to `artisanStatus`, `matches`, `tracking`), which is how the flow moves forward after a successful action.

### `apps/web/src/styles.css` (layout only)
- `.app`: flex column, `min-height: 100vh`, `max-width: 1100px`, centred.
- `.top`: sticky header (`position: sticky; top: 0; z-index: 5`), brand colour background.
- `.demo-banner`: warning colours, full width.
- `.layout`: CSS grid, one column by default (`grid-template-columns: 1fr`).
- `@media (min-width: 900px)`: `.layout` becomes `minmax(0, 1fr) 360px` (main + SMS side panel); `.sms` becomes `position: sticky; top: 76px`; the `.sms-toggle` button is hidden and `.sms-body` always shown. Below 900px the SMS panel is collapsible (`SmsLog` toggles class `sms-open`).
- `@media (max-width: 420px)`: `.row-2` and `.choices` collapse to one column.
- Accessibility rules: minimum 48px touch targets for buttons/inputs, `:focus-visible` outline, 16px base font.
- `.foot`: flex row with the note on the left and the two link buttons on the right.

## Data and state

| Field | Where | Meaning |
|---|---|---|
| `state.ui.screen` | `UiState` | Which screen is shown. The "router". |
| `state.ui.actingArtisanId` | `UiState` | Logged-in artisan id or `null`; read by `Home`. |
| `state.ui.jobId` | `UiState` | Current job; read by `Home` to show "My job". |
| `state.ui.requestId`, `profileId`, `back`, `loginNext`, `chatAs` | `UiState` | Context passed between screens through the `nav` patch. |
| `state.lang` | `State` | `'fr'` (default) or `'en'`. |
| `state.sms` | `State` | List used by the SMS panel and its counter. |
| `localStorage['acbridge.demo.v2']` | browser | Whole `State` as JSON, saved after every change. |
| `localStorage['acbridge.api']` | browser | Backend base URL set by `?api=`. |

`UiState.back` is a stored value read by `ArtisanProfile` (`state.ui.back`) to know where its Back button goes; for all other screens the Back button comes from the `back` prop of the `Screen` component.

## Rules and edge cases

- Unknown or stale `ui.screen` falls back to `Home` (App.tsx, `?? Home`).
- Corrupt or old-format saved state is ignored (persistence.ts: `v !== 1` or no `artisans` array gives a fresh `initialState()`); the key is versioned (`.v2`) so older data is never reused.
- `loadState` merges `{ ...initialState(), ...parsed }`, so new top-level fields added later get defaults.
- `localStorage` errors (private mode, full) are swallowed in `loadState`, `saveState`, `clearState` and `readApiBase`; the app keeps working in memory.
- Speech synthesis is optional: no support means no button; runtime errors are caught.
- There is no route guard: any screen can be set by any `go()` call. Screens protect themselves (e.g. artisan screens render `ArtisanLogin` inline when `actingArtisanId` is missing; the operator screen asks for a PIN).
- The browser Back button and URL do not change when navigating; reloading restores the screen only through the persisted state.

## Tests

- `apps/web/src/__tests__/ui-flows.test.tsx` renders `<App />` with a stubbed `localStorage` and French default. The first test starts with `expect(screen.getByRole('heading', { name: 'Bienvenue' }))`, i.e. the Home screen. Test "survives a refresh (localStorage) and Reset demo clears it" unmounts and re-renders `<App />` and checks that the screen state is restored, then resets and checks the Home heading is back. Navigation is used by every test through button clicks (`Je suis artisan`, `Accueil`, ...).
- `apps/web/src/i18n` has no tests in the web app; `packages/core/src/i18n/i18n.test.ts` checks the dictionaries (for example that `dictionaries.local['home.title']` falls back to the French text).
- No test targets `LanguageToggle`, `SpeakButton`, `toggleBackend` or `readApiBase` directly.

## Backend connection

None for navigation itself. `config.ts` only decides whether other code talks to the backend: `API_MODE === 'api'` makes the store's `mirror()` run the steps in `apps/web/src/api/bridge.ts` through `apps/web/src/api/client.ts`, which uses `API_BASE` (or `/api`, proxied by `vite.config.ts` to `VITE_BACKEND_URL` or `http://localhost:8000`). When a mirror step fails, `mirror()` sets the `notice` text `"<mode.api text>: <error message>"` that `Shell` displays.

## Known limits and what changes in the production rebuild

- The state-based router has no URLs, no deep links, no browser history and no code splitting; every screen is imported statically in `App.tsx`. A production rebuild would use real routes (so links and the Back button work) and per-route guards.
- Screen-local form state is lost on navigation by design of this approach.
- The whole app state, including every artisan's hash and all SMS, is kept in `localStorage`; a production app would keep server-side state and only cache what is needed.
- "Connect backend" is a prompt plus page reload driven by a query string; a production build would use a configured environment, not a user-entered URL.
- The SMS panel and the demo banner exist because people, SMS and verification are simulated; production would remove them and send real SMS.
- Only French and English exist; the `local` dictionary is an empty slot.
- Speech output depends on the browser's installed voices for `speechLocale[lang]`.
