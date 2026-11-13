# 16. Logo and page identity ("chemistry" between the logo and each page)

## What the user sees
- The designer's logo (`logo/acbridge_logo.svg`) in the always-navy header, the footer, the favicon, the install icon, the share card and the database viewers.
- Every screen carries a small gold piece of the logo's glyph as its signature, plus a thin gold rule. The piece matches what the screen is about:

| Screens | Motif | Why |
|---|---|---|
| Home | `mark` (whole glyph) | the brand moment |
| Artisan entry, login, sign-up, inbox, complete | `post` (leaning post) | the artisan, the person who does the work |
| Artisan status, matches, rate, profile | `arch` (bridge span) | trust being built between two people |
| Customer request, chat, operator | `baseline` (ground line) | the common ground both sides stand on |
| Tracking, payments | `span` (arch over baseline) | something being carried across safely |

- Gold appears only as an accent: stepper, best-match badge, vouch seal, stars, chat bubbles. Text in gold uses a darker, contrast-safe gold.

## Files
| File | Role |
|---|---|
| `logo/acbridge_logo.svg` | the designer's original (kept untouched) |
| `packages/brand/src/paths.ts` | geometry extracted from the original (letters, arch, post, baseline, dots, gradient) |
| `packages/brand/src/motifs.ts` | the motifs and `SCREEN_MOTIF` (screen to motif) |
| `packages/brand/src/render.ts` | SVG string renderers (wordmark, mark, app icon, splash, social card) |
| `packages/brand/scripts/build-assets.ts`, `build-png.mjs` | write the SVGs and PNGs in `packages/brand/assets` (`pnpm brand:build`; `pnpm brand:check` fails if stale) |
| `apps/web/src/components/brand/Logo.tsx`, `brand.css` | the web `Logo` and `Motif` components; styling uses tokens only |
| `apps/web/src/components/Screen.tsx` | adds `data-screen`, the motif and the gold rule to every screen |
| `apps/web/scripts/sync-brand.ts` | copies icons and generates the web manifest before dev/build |
| `apps/mobile/src/components/Logo.tsx` | the React Native logo (react-native-svg; not yet run on a device) |
| `apps/web/database/make-browser.mjs` | puts the logo and tokens in the DB viewers |

## How it works
1. `build-assets.ts` turns the geometry into 12 SVGs; `build-png.mjs` rasterises PNGs with headless Edge (favicon, apple-touch, 192/512, maskable, 1024 icon, adaptive foreground, splash, social card).
2. Gold comes from tokens (`goldLight` #F7D774, `goldDeep` #B8860B, `goldText`, `onGold`), so the logo, the motifs and the accents cannot drift apart. Contrast is checked by `pnpm contrast` (54 pairs).
3. `Logo` draws the letters with `currentColor`-like token classes and the glyph with a gradient whose id is unique per instance (`useId`), so many logos can share one page.
4. `Screen` looks up `SCREEN_MOTIF[screen]`; a test fails if a screen has no motif.
5. The header is always navy with near-white lettering, so the logo reads the same in light and dark mode.

## Tests
`packages/brand/src/brand.test.ts` (geometry, renderers, every screen mapped) and `apps/web/src/components/brand/brand.test.tsx` (accessible name, unique gradient ids, decorative motifs hidden from screen readers, tokens only in `brand.css`).

## Known limits
Mobile icons and splash are wired in `apps/mobile/app.json` but were never built on a device. The FastAPI docs page still uses the default favicon.
