# Design system and monorepo foundation (phases 0 and 1)

This section is infrastructure: it provides the pnpm monorepo layout, a single source of design tokens (colours, spacing, type, motion) that generates both web CSS variables and a React Native theme, automated checks (contrast, no hard-coded colours, no secrets in built bundles), a set of accessible UI primitives, a style guide page that shows them in light and dark, and a mobile scaffold. The current demo screens still use their older components and `styles.css`; the primitives are the base the production rebuild is built on.

## Files

| File | Role |
|---|---|
| `package.json` (root) | Workspace scripts: `tokens:build`, `tokens:check`, `contrast`, `check:hex`, `check:bundles`, `check`, `test`, `build`, `web`, `mobile`. Declares `packageManager: pnpm@9.15.9`, `node >=20`, dev deps `tsx`, `typescript`. |
| `pnpm-workspace.yaml` | Workspace globs `apps/*`, `packages/*`, and excludes `apps/mobile`. |
| `packages/tokens/src/tokens.ts` | The single source of tokens (`colors`, `space`, `radius`, `shadow`, `type`, `target`, `motion`, `layout`) and the list of contrast `pairs`. |
| `packages/tokens/src/contrast.ts` | WCAG contrast maths: `hexToRgb`, `luminance`, `contrastRatio`, `checkAllPairs`. |
| `packages/tokens/src/render.ts` | Pure generators `renderCss()` and `renderTheme()`. |
| `packages/tokens/src/build.ts` | Writes (or with `--check` verifies) the generated files. |
| `packages/tokens/src/index.ts` | Package entry: re-exports tokens and the contrast helpers. |
| `packages/tokens/src/tokens.test.ts` | Tests for pairs, spec numbers, dark accent rule, palette, generated CSS. |
| `packages/tokens/generated/tokens.css` | Generated CSS custom properties (130 lines). Do not edit by hand. |
| `packages/tokens/generated/theme.ts` | Generated React Native theme object (83 lines). Do not edit by hand. |
| `packages/core/` | Platform-neutral shared code (see summary below). |
| `packages/config/` | Shared `tsconfig.base.json` and `prettier.json`. |
| `scripts/contrast-check.ts` | CLI: prints every pair, fails below the ratio, optional `--write` into `docs/ACCESSIBILITY.md`. |
| `scripts/check-no-hex.ts` | CLI: fails if a hex colour appears outside `packages/tokens`. |
| `scripts/hex-allowlist.json` | Legacy files still allowed to contain hex colours (only `apps/web/src/styles.css`). |
| `scripts/check-bundle-secrets.ts` | CLI: scans built client output for secrets. |
| `apps/web/src/components/ui/primitives.tsx` | `Button`, `Card`, `Badge`, `Field`, `Skeleton`, `EmptyState`, `ErrorState`. |
| `apps/web/src/components/ui/index.ts` | Re-exports the primitives and the `ButtonProps`, `Tone` types. |
| `apps/web/src/components/ui/ui.css` | Primitive styles using only `var(--acb-*)` tokens. |
| `apps/web/src/components/ui/ui.test.tsx` | Tests for the primitives and token-only rule. |
| `apps/web/src/styleguide/Styleguide.tsx`, `main.tsx` | The style guide page content and entry. |
| `apps/web/styleguide.html` | HTML entry for the style guide (served by the dev server at `/styleguide.html`). |
| `docs/ACCESSIBILITY.md` | Accessibility targets, the generated contrast table, built-in rules. |
| `apps/mobile/*` | Expo / React Native scaffold, not run on a device. |

## How it works

### Token pipeline

1. Edit values in `packages/tokens/src/tokens.ts` (the only place a hex colour may be written).
2. Run `pnpm tokens:build`. `build.ts` calls `renderCss()` and `renderTheme()` and writes `packages/tokens/generated/tokens.css` and `theme.ts`.
3. `renderCss()` produces: a `:root` block with light colours, spacing, radii, shadow, font and size variables, line height, tap target, motion and max width; a `@media (prefers-color-scheme: dark)` block `:root:not([data-theme='light'])` with dark colours; a manual `:root[data-theme='dark']` block; scoped classes `.acb-theme-light` and `.acb-theme-dark` (each sets the colour variables plus `background: var(--acb-color-surface); color: var(--acb-color-text)`); and a `prefers-reduced-motion: reduce` block that sets the three motion variables to `0ms`.
4. Variable names are `--acb-<group>-<kebab-key>`, for example `colors.light.accentTextOnDark` becomes `--acb-color-accent-text-on-dark`, `space[4]` becomes `--acb-space-4: 16px`.
5. `renderTheme()` writes `export const theme = {...} as const` (colours for both modes, space, radius, type with `fontFamily: 'System'`, target, motion) plus `Theme` and `ThemeMode` types. Shadows are not in the theme (platform specific).
6. The web app imports the CSS with `import '@acbridge/tokens/css'` in `apps/web/src/main.tsx` (and in the style guide entry). The package `exports` map: `.` to `src/index.ts`, `./css` to `generated/tokens.css`, `./theme` to `generated/theme.ts`.
7. `pnpm tokens:check` (`build.ts --check`) regenerates in memory and fails if the files on disk differ (line endings are normalised), so generated files cannot go stale.

### Checks (`pnpm check`)

`pnpm check` = `pnpm tokens:check && pnpm contrast && pnpm check:hex`. `pnpm check:bundles` is separate because it needs a built app.

1. `contrast`: `scripts/contrast-check.ts` runs `checkAllPairs()` and prints one line per pair and mode (`PASS`/`FAIL`, ratio, minimum, both hex values). It exits 1 on any failure, and also fails if `colors.dark.accentText === colors.dark.accent`. `pnpm contrast -- --write` rewrites the table between `<!-- contrast:start -->` and `<!-- contrast:end -->` in `docs/ACCESSIBILITY.md`.
2. `check:hex`: `scripts/check-no-hex.ts` walks `apps` and `packages` for `.ts .tsx .css .js .jsx .mjs` (skipping `node_modules`, `dist`, `generated`, `.expo`, `database`, `coverage`), skips `packages/tokens/`, test files (`__tests__`, `.test.`, `.spec.`) and allow-listed files, and fails on any `#rgb`, `#rrggbb` or `#rrggbbaa` literal.
3. `check:bundles`: `scripts/check-bundle-secrets.ts` scans (by default) `apps/web/dist` and `apps/web/acbridge.html` (or the paths given as arguments) for patterns: webhook secret, JWT secret, database URL, MTN/Orange provider key names, private key block, bearer token literal, JWT literal, operator PIN hash, and generic `secret/api_key/password = "<16+ chars>"` assignments. It exits 1 on a finding or when no built file is found.

### Primitives and style guide

1. Screens (in the rebuild) import from `components/ui` and get components styled by `ui.css`; `ui.css` imports nothing but tokens through CSS variables.
2. To see them, run `pnpm web` (Vite dev server) and open `http://localhost:5173/styleguide.html`. `styleguide.html` loads `/src/styleguide/main.tsx`, which imports the token CSS and renders `<Styleguide />`.
3. `Styleguide` renders the same `Showcase` twice, once inside `<section className="acb-theme-light acb-page" data-testid="light">` and once inside `acb-theme-dark ... data-testid="dark"`, so both themes are visible side by side regardless of the system setting.

## File by file

### `package.json` and `pnpm-workspace.yaml`

- Root scripts (all through `pnpm`): `tokens:build`, `tokens:check`, `contrast`, `check:hex`, `check:bundles`, `check`, `test` (`pnpm -r --if-present test`, runs every package's `test`), `build` (`pnpm -r --if-present build`), `web` (`pnpm --filter @acbridge/web dev`), `mobile` (`pnpm --filter @acbridge/mobile start`).
- Workspace: `apps/*` and `packages/*`; `!apps/mobile` is excluded so `pnpm install` stays light on machines that cannot run Expo. To work on mobile, remove that line (see `apps/mobile/README.md`).
- The backend (`backend/`, Python) is not part of the pnpm workspace.

### `packages/tokens/src/tokens.ts`

- `colors: Record<'light'|'dark', ColorSet>` with 14 roles: `ink`, `text`, `accent`, `accentText`, `accentTextOnDark`, `onAccent`, `surface`, `surfaceRaised`, `border`, `borderStrong`, `textMuted`, `success`, `warning`, `danger`.
- Mandated palette values (kept unchanged): ink `#0F172A`, accent `#2563EB`, light surface `#FFFFFF`, surface raised `#F8FAFC`, border `#CBD5E1`, muted text `#475569`; dark surface `#0F172A`, raised `#172033`, border `#334155`, muted `#94A3B8`.
- Derived roles (added so the mandated values still meet contrast rules):
  - `text`: equals `ink` on light, `#F8FAFC` on dark (the ink colour is the dark page background, so it cannot be the text colour on dark).
  - `accentText`: `#2563EB` on light; `#93C5FD` on dark (accent fails 4.5:1 as text on `#0F172A`).
  - `accentTextOnDark`: `#93C5FD` in both sets.
  - `borderStrong`: `#64748B`, used for input outlines (the mandated `border` is a divider colour, below 3:1 against white).
  - `success`, `warning`, `danger`: darker in light mode, lighter in dark mode.
- `space` (0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 px under keys 0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16), `radius` (`card` 16, `button` 12, `pill` 999), one `shadow.raised`, `type` (system font stack only, sizes body 16 / instruction 18 / small 16 / heading 24 / display 30, line height 1.5, weights 400/500/700), `target.min = 48`, `motion` (150 / 200 / 250 ms), `layout.maxContentWidth = 960`.
- `pairs: Pair[]` is the list of checked combinations (`fg`, `bg`, `min`, `modes`, `why`).

### `packages/tokens/src/contrast.ts`

- `hexToRgb(hex)`: accepts only `#RRGGBB`, throws otherwise.
- `luminance(hex)`: sRGB relative luminance (WCAG formula).
- `contrastRatio(a, b)`: `(lighter + 0.05) / (darker + 0.05)`.
- `checkAllPairs()`: expands each `Pair` for each mode in `modes` and returns `PairResult[]` with ratio and `pass`.

### `packages/tokens/src/render.ts`, `build.ts`, `index.ts`

Described in the pipeline above. `render.ts` is pure and imported by both `build.ts` and the tests. `index.ts` exports `* from './tokens'` and `checkAllPairs`, `contrastRatio`, `luminance`, `hexToRgb`, `PairResult`.

### Generated files

- `tokens.css`: header comment "GENERATED ... Do not edit by hand", then the blocks listed above. Light is the default `:root`; `color-scheme: light dark` is declared.
- `theme.ts`: JSON of the theme object, `Theme` and `ThemeMode` types.

### Contrast pairs and the dark-accent rule

Pairs checked (both modes unless noted): `text` on `surface` and `surfaceRaised` (4.5); `textMuted` on both (4.5); `accentText` on both (4.5); `onAccent` on `accent` (4.5); `accent` on both surfaces (3, focus ring and selected outline, non-text); `borderStrong` on both (3); `success`, `warning`, `danger` on both (4.5); `accentTextOnDark` on both surfaces (4.5, dark only).

Numbers from `docs/ACCESSIBILITY.md` (generated by `pnpm contrast -- --write`):

| Pair | Ratio |
|---|---|
| `#2563EB` text on white (light) | 5.17:1 |
| White label on `#2563EB` button | 5.17:1 |
| `#2563EB` on `#0F172A` (dark page) | 3.45:1: fails as text (needs 4.5), valid as focus ring (needs 3) |
| `#93C5FD` (accent-text-on-dark) on `#0F172A` | 9.90:1 |
| `#93C5FD` on dark card `#172033` | 9.02:1 |

So the raw accent token is used for text and links on light surfaces only. On dark surfaces text and links use `accentText` which equals `accentTextOnDark` (`#93C5FD`). The accent stays valid on dark for button backgrounds (white label) and focus rings. A test and the CLI both enforce `colors.dark.accentText !== colors.dark.accent`.

### `apps/web/src/components/ui/primitives.tsx`

| Component | Props | Behaviour |
|---|---|---|
| `Button` | `icon: LucideIcon` (required), `label: string` (required), `variant?: 'primary'\|'secondary'\|'danger'\|'ghost'`, `big?`, `block?`, plus native button attributes | Renders `<button type="button">` with the icon (`size 22`, `aria-hidden`) and the label in a `<span>`. Icon plus label is enforced by the TypeScript props. Classes `acb-btn acb-btn-<variant>`, optional `acb-btn-big`, `acb-btn-block`. `type` defaults to `button`. |
| `Card` | `title?`, `children`, `as?: 'section'\|'article'\|'div'` | `acb-card` container with optional `<h2>`. |
| `Badge` | `tone: 'success'\|'warning'\|'danger'\|'info'`, `children` | A status is always an icon (`CheckCircle2`, `TriangleAlert`, `AlertCircle`, `Info`) plus a word; border and text use the tone colour. |
| `Field` | `label`, `hint?`, `error?`, `multiline?`, plus input/textarea attributes | Uses `useId()` to link a visible `<label htmlFor>` to the control; `aria-describedby` points to the hint and error ids; `aria-invalid` when there is an error; the error container `<div role="alert" aria-live="assertive">` is always rendered (empty when no error) so assistive technology announces changes; an error shows an icon and text; `data-invalid` drives the red border. |
| `Skeleton` | `lines = 3`, `height = 16` | `role="status" aria-busy="true" aria-label="Loading"`; grey bars with a pulse animation (the last bar is 60% wide). The `aria-label` text is English-only in this version. |
| `EmptyState` | `title`, `body`, `action?` | Centred icon (`Inbox`), `<h3>`, text, optional action: "what is empty and what to do next". |
| `ErrorState` | `title`, `body`, `action?` | Same layout with `role="alert"` and a danger-coloured icon; `action` is typically a retry button. |

`primitives.tsx` imports `./ui.css`. Icons come from `lucide-react`.

### `apps/web/src/components/ui/ui.css`

- Tokens only: sizes from `--acb-space-*`, `--acb-target-min` (48 px min height and width for buttons and inputs), radii (`--acb-radius-button`, `--acb-radius-card`, `--acb-radius-pill`), colours from `--acb-color-*`, motion from `--acb-motion-*`.
- Focus: `:focus-visible` gives `outline: 3px solid var(--acb-color-accent); outline-offset: 2px` on buttons and inputs.
- Variants: primary (accent background, `on-accent` label), secondary (transparent, `accent-text` label, accent border), danger, ghost; disabled `opacity: 0.55`.
- `.acb-skeleton` animation is switched off under `prefers-reduced-motion: reduce`; the motion variables are also zeroed by the generated CSS.
- Layout helpers `.acb-stack` and `.acb-page` (max width `--acb-max-content-width`).

### `apps/web/src/styleguide/Styleguide.tsx`, `main.tsx` and `apps/web/styleguide.html`

`Showcase` shows: Buttons (all variants, big/block, disabled), Statuses (four badges), Form fields (hint, error, multiline), Loading/empty/error (skeleton, empty state, error state with retry), and a Colour tokens list (swatch plus name using `var(--acb-color-<kebab>)`). `Styleguide` renders `Showcase` in both scoped themes. The page is a second HTML entry used by the Vite dev server only: the build script (`vite build`) has no extra Rollup input configured, so `styleguide.html` is not part of the production build or of `acbridge.html`. The component test renders `<Styleguide />` directly.

### Scoped themes `.acb-theme-light` and `.acb-theme-dark`

Generated classes that redefine every colour variable on an element and set its background and text colour. They let the style guide show both modes at once and let any region be forced to one mode regardless of `prefers-color-scheme` or `data-theme`.

### `packages/core` (summary)

Platform-neutral code with no React and no platform APIs. `src/index.ts` exports:

| Module | Contents |
|---|---|
| `types` | `Lang`, `Role`, `Urgency`, `JobStatus`, `PaymentStatus`, `PayoutStatus`, `ThemeChoice`, ... |
| `phone` | `DEFAULT_COUNTRY_PREFIX = '+237'`, `normalizePhone`, `maskPhone`, `stripPhones` |
| `money` | `assertWholeFcfa`, `formatAmount`, `formatFcfa`, `formatRange` (whole FCFA, never floats) |
| `i18n` | dictionaries, `translate`, `speechLocale` (section 13) |
| `schemas` | zod schemas for backend payloads (section 14) |
| `api/client` | `createApiClient`, `ApiError`, `SchemaError` (section 14) |

Its only runtime dependency is `zod`; its `test` script runs vitest (`i18n.test.ts`, `phone.test.ts`, `money.test.ts`, `client.test.ts`, `schemas.test.ts`).

### `packages/config`

No code: `tsconfig.base.json` (target ES2022, `strict`, `moduleResolution: bundler`, `noEmit`, `isolatedModules`, `skipLibCheck`) and `prettier.json` (`singleQuote`, `printWidth 120`, `trailingComma all`, `semi`).

### `scripts/hex-allowlist.json`

`{ "files": ["apps/web/src/styles.css"] }`: the demo's legacy stylesheet still contains literal colours (for example the SMS panel). The comment in the file says the list may only shrink, which means the legacy screens will be rebuilt on the primitives and the file removed from the list.

### `apps/mobile` (scaffold)

Files: `app.json`, `babel.config.js`, `package.json` (Expo `~52.0.0`, React Native `0.76.5`, `lucide-react-native`, `react-native-svg`, jest-expo), `tsconfig.json`, `README.md`, `src/app/App.tsx`, `src/components/primitives.tsx`, `src/theme/useTheme.ts`.

- `useTheme(override?)` reads `useColorScheme()` and returns `{ mode, colors, space, radius, type, target, motion }` from `@acbridge/tokens/theme`.
- `primitives.tsx` exports `Button` (icon + label, 48 px target), `Card`, `Badge` (icon + word), `Body`, and `styles`.
- `App.tsx` is a shell showing a card, a "Verified" badge and a "Continue" button in the current system mode.
- Status stated in its own README: scaffold, NOT yet run on a device; nothing has been type-checked against React Native or executed. It is excluded from the pnpm workspace; to run it, remove `- "!apps/mobile"` from `pnpm-workspace.yaml`, run `pnpm install`, then `pnpm --filter @acbridge/mobile start`. No environment variables yet (later `EXPO_PUBLIC_API_URL`; no secret may go into an `EXPO_PUBLIC_*` variable).

### `docs/ACCESSIBILITY.md`

States the target (WCAG 2.2 AA web, platform guidance on mobile), holds the contrast table between the markers, the rules (tap targets at least 48 px, text at least 16 px with line height 1.5, visible 3 px accent focus ring, status never by colour alone, motion 150 to 250 ms removed under reduced motion, light/dark follow the system with a `data-theme` override), and the "still to do" list (axe checks in CI, keyboard walk-through, largest-text testing, mobile screen-reader review).

## Data and state

No runtime state. Data are constants in `tokens.ts` and generated artefacts: `generated/tokens.css`, `generated/theme.ts`, the table inside `docs/ACCESSIBILITY.md`. The only runtime preference mentioned is the `data-theme` attribute on `<html>` (`light` or `dark`); no code in this version sets it (the Settings screen is a later phase).

## Rules and edge cases

- One source: a colour value is defined only in `packages/tokens/src/tokens.ts`. Components use `var(--acb-*)` (web) or `theme.colors[mode]` (mobile).
- No hex outside tokens: enforced by `pnpm check:hex` and by `ui.test.tsx` for the primitives; the legacy allow-list currently holds `apps/web/src/styles.css`.
- Text contrast 4.5:1, non-text (focus ring, input outline) 3:1, checked for both modes; accent text on dark must use `accentTextOnDark`.
- Generated files are never edited by hand and must match the source (`tokens:check`).
- Every action button has an icon and a label of at most 3 words (convention documented in the component comment; the type enforces both exist, not the word count).
- Statuses use icon plus word, never colour alone. Errors are announced via `role="alert"`.
- Only `.ts .tsx .css .js .jsx .mjs` are scanned by `check:hex`; `.html` files (such as `styleguide.html`) and `.json` are not.

## Tests

| File | Test | What it checks |
|---|---|---|
| `packages/tokens/src/tokens.test.ts` | "every foreground/background pair meets its WCAG ratio in light and dark" | `checkAllPairs()` has no failing pair. |
| same | "reproduces the numbers the spec states" | Accent on white above 5.1; white on accent above 5.1; accent on `#0F172A` below 4.5 but above 3; `accentTextOnDark` above 4.5. |
| same | "blue text on dark surfaces uses accent-text-on-dark, never the raw accent token" | `colors.dark.accentText === accentTextOnDark` and `!== accent`. |
| same | "keeps the mandated palette values" | Palette values listed above. |
| same | "generates CSS custom properties with light, system-dark and manual-dark blocks and reduced motion" | `renderCss()` contains the accent variable, the `prefers-color-scheme: dark` media query, `:root[data-theme='dark']`, `prefers-reduced-motion: reduce`; `renderTheme()` contains `"accentText": "#93C5FD"`. |
| `apps/web/src/components/ui/ui.test.tsx` | "Button always has an icon AND a label, and is a real button" | SVG icon present and `aria-hidden`, `type="button"`, class `acb-btn-primary`. |
| same | "Field has a visible label linked to the control, and announces its error" and "Field without an error has an empty (but present) live region" | Label association, error live region. |
| same | "Badge is icon + word, never colour alone", "Skeleton is announced as busy; Empty and Error states say what to do next", "Card renders a titled region" | Primitive structure. |
| same | "the style guide shows every primitive in BOTH light and dark" | `<Styleguide />` has `acb-theme-light` and `acb-theme-dark` regions each with 5 or more buttons, a badge, a skeleton and an error state. |
| same | "contain no hex colours", "every var(--acb-*) they use is defined by the generated tokens", "tap targets use the 48 px token and the focus ring uses the accent token" | `ui.css` and `primitives.tsx` have no hex; every CSS variable used exists in `tokens.css`; `min-height: var(--acb-target-min)` and the 3 px accent outline are present. |

`check-no-hex.ts`, `contrast-check.ts` and `check-bundle-secrets.ts` have no unit tests; they are run as commands.

## How to run everything

```bash
pnpm install              # once, at the repository root
pnpm tokens:build         # regenerate packages/tokens/generated/*
pnpm check                # tokens:check + contrast + check:hex
pnpm contrast -- --write  # also refresh the table in docs/ACCESSIBILITY.md
pnpm test                 # every package's vitest suite
pnpm build                # builds apps/web (type-check, vite build, acbridge.html)
pnpm check:bundles        # scan apps/web/dist and apps/web/acbridge.html (after build)
pnpm web                  # dev server; open /styleguide.html for the style guide
```

## Backend connection

None (local only). The tokens and primitives know nothing about the backend. `packages/core` contains the schemas and the typed API client that describe backend payloads (section 14), and `check:bundles` exists to keep backend secrets out of client output.

## Known limits and what changes in the production rebuild

- The existing demo screens still use `styles.css` (with hex colours, allow-listed) and `components/Button.tsx` and friends, not the new primitives; migrating them is the rebuild work, after which the allow-list should be empty.
- The style guide is a dev-only page, not a Storybook; it has no interaction states (hover, focus, error toggles) beyond what is rendered statically.
- Axe/automated accessibility testing in CI, a keyboard walk-through of all screens, largest-system-text testing and mobile screen-reader review are still to do (per `docs/ACCESSIBILITY.md`).
- `Skeleton` has a hard-coded English `aria-label="Loading"`; it should take a translated label.
- No Settings screen yet sets `data-theme`.
- `apps/mobile` has never been installed, type-checked or run on a device, and is outside the pnpm workspace; its `test` and `typecheck` scripts are unverified.
- `check-bundle-secrets.ts` is pattern based and can miss an unusual secret format; it does not replace secret management on the server.
