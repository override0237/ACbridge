# Accessibility

Target: WCAG 2.2 AA on web; platform accessibility guidance on mobile. This file is updated as each phase lands.

## Colour contrast (checked, not assumed)

Every foreground/background pair of `packages/tokens/src/tokens.ts` is measured by `scripts/contrast-check.ts` (`pnpm contrast`),
which fails the build below the required ratio (4.5:1 for text, 3:1 for focus rings and input outlines).
Regenerate this table with `pnpm contrast -- --write`.

Rules from the spec that the script enforces:

- `#2563EB` is used for text and links on **light** surfaces only (5.17:1 on white).
- On dark surfaces, links and accent text use `accent-text-on-dark` (`#93C5FD`), because `#2563EB` on `#0F172A` is only about 3.4:1.
- `#2563EB` stays valid on dark for **buttons** (white label, 5.17:1) and **focus rings** (3.4:1, above the 3:1 non-text minimum).
- Derived roles that do not change the mandated palette: `text` (near-white on dark), `accentText`, `borderStrong` (input outlines;
  the mandated `border` is a divider colour and is below 3:1), and the status colours `success`, `warning`, `danger`.

<!-- contrast:start -->

| Mode | Foreground | Background | Ratio | Needs | Use | Result |
|---|---|---|---|---|---|---|
| light | `goldText` #8A6408 | `surface` #FFFFFF | 5.37:1 | 4.5:1 | gold text on the page | pass |
| dark | `goldText` #F7D774 | `surface` #0F172A | 12.69:1 | 4.5:1 | gold text on the page | pass |
| light | `goldText` #8A6408 | `surfaceRaised` #F8FAFC | 5.14:1 | 4.5:1 | gold text on cards | pass |
| dark | `goldText` #F7D774 | `surfaceRaised` #172033 | 11.56:1 | 4.5:1 | gold text on cards | pass |
| light | `goldDeep` #B8860B | `surface` #FFFFFF | 3.25:1 | 3:1 | gold shapes and rules against the page (non-text, 3:1) | pass |
| dark | `goldDeep` #B8860B | `surface` #0F172A | 5.49:1 | 3:1 | gold shapes and rules against the page (non-text, 3:1) | pass |
| light | `goldDeep` #B8860B | `surfaceRaised` #F8FAFC | 3.11:1 | 3:1 | gold shapes and rules against cards (non-text, 3:1) | pass |
| dark | `goldDeep` #B8860B | `surfaceRaised` #172033 | 5.00:1 | 3:1 | gold shapes and rules against cards (non-text, 3:1) | pass |
| light | `goldLight` #F7D774 | `ink` #0F172A | 12.69:1 | 3:1 | logo glyph and motifs on navy (non-text, 3:1) | pass |
| dark | `goldLight` #F7D774 | `ink` #0F172A | 12.69:1 | 3:1 | logo glyph and motifs on navy (non-text, 3:1) | pass |
| light | `goldDeep` #B8860B | `ink` #0F172A | 5.49:1 | 3:1 | logo glyph lower end on navy (non-text, 3:1) | pass |
| dark | `goldDeep` #B8860B | `ink` #0F172A | 5.49:1 | 3:1 | logo glyph lower end on navy (non-text, 3:1) | pass |
| light | `onInk` #F8FAFC | `ink` #0F172A | 17.06:1 | 4.5:1 | text and wordmark on the navy header | pass |
| dark | `onInk` #F8FAFC | `ink` #0F172A | 17.06:1 | 4.5:1 | text and wordmark on the navy header | pass |
| light | `onGold` #0F172A | `goldLight` #F7D774 | 12.69:1 | 4.5:1 | ink text on the light end of the gold gradient | pass |
| dark | `onGold` #0F172A | `goldLight` #F7D774 | 12.69:1 | 4.5:1 | ink text on the light end of the gold gradient | pass |
| light | `onGold` #0F172A | `goldDeep` #B8860B | 5.49:1 | 4.5:1 | ink text on the deep end of the gold gradient | pass |
| dark | `onGold` #0F172A | `goldDeep` #B8860B | 5.49:1 | 4.5:1 | ink text on the deep end of the gold gradient | pass |
| light | `text` #0F172A | `surface` #FFFFFF | 17.85:1 | 4.5:1 | body text on the page | pass |
| dark | `text` #F8FAFC | `surface` #0F172A | 17.06:1 | 4.5:1 | body text on the page | pass |
| light | `text` #0F172A | `surfaceRaised` #F8FAFC | 17.06:1 | 4.5:1 | body text on cards and sheets | pass |
| dark | `text` #F8FAFC | `surfaceRaised` #172033 | 15.55:1 | 4.5:1 | body text on cards and sheets | pass |
| light | `textMuted` #475569 | `surface` #FFFFFF | 7.58:1 | 4.5:1 | secondary text on the page | pass |
| dark | `textMuted` #94A3B8 | `surface` #0F172A | 6.96:1 | 4.5:1 | secondary text on the page | pass |
| light | `textMuted` #475569 | `surfaceRaised` #F8FAFC | 7.24:1 | 4.5:1 | secondary text on cards | pass |
| dark | `textMuted` #94A3B8 | `surfaceRaised` #172033 | 6.34:1 | 4.5:1 | secondary text on cards | pass |
| light | `accentText` #2563EB | `surface` #FFFFFF | 5.17:1 | 4.5:1 | links and accent text on the page | pass |
| dark | `accentText` #93C5FD | `surface` #0F172A | 9.90:1 | 4.5:1 | links and accent text on the page | pass |
| light | `accentText` #2563EB | `surfaceRaised` #F8FAFC | 4.94:1 | 4.5:1 | links and accent text on cards | pass |
| dark | `accentText` #93C5FD | `surfaceRaised` #172033 | 9.02:1 | 4.5:1 | links and accent text on cards | pass |
| light | `onAccent` #FFFFFF | `accent` #2563EB | 5.17:1 | 4.5:1 | label text on accent buttons | pass |
| dark | `onAccent` #FFFFFF | `accent` #2563EB | 5.17:1 | 4.5:1 | label text on accent buttons | pass |
| light | `accent` #2563EB | `surface` #FFFFFF | 5.17:1 | 3:1 | focus ring and selected outline against the page (non-text, 3:1) | pass |
| dark | `accent` #2563EB | `surface` #0F172A | 3.45:1 | 3:1 | focus ring and selected outline against the page (non-text, 3:1) | pass |
| light | `accent` #2563EB | `surfaceRaised` #F8FAFC | 4.94:1 | 3:1 | focus ring and selected outline against cards (non-text, 3:1) | pass |
| dark | `accent` #2563EB | `surfaceRaised` #172033 | 3.15:1 | 3:1 | focus ring and selected outline against cards (non-text, 3:1) | pass |
| light | `borderStrong` #64748B | `surface` #FFFFFF | 4.76:1 | 3:1 | input outlines against the page (non-text, 3:1) | pass |
| dark | `borderStrong` #64748B | `surface` #0F172A | 3.75:1 | 3:1 | input outlines against the page (non-text, 3:1) | pass |
| light | `borderStrong` #64748B | `surfaceRaised` #F8FAFC | 4.55:1 | 3:1 | input outlines against cards (non-text, 3:1) | pass |
| dark | `borderStrong` #64748B | `surfaceRaised` #172033 | 3.42:1 | 3:1 | input outlines against cards (non-text, 3:1) | pass |
| light | `success` #15803D | `surface` #FFFFFF | 5.02:1 | 4.5:1 | success text on the page | pass |
| dark | `success` #4ADE80 | `surface` #0F172A | 10.25:1 | 4.5:1 | success text on the page | pass |
| light | `success` #15803D | `surfaceRaised` #F8FAFC | 4.79:1 | 4.5:1 | success text on cards | pass |
| dark | `success` #4ADE80 | `surfaceRaised` #172033 | 9.34:1 | 4.5:1 | success text on cards | pass |
| light | `warning` #B45309 | `surface` #FFFFFF | 5.02:1 | 4.5:1 | warning text on the page | pass |
| dark | `warning` #FBBF24 | `surface` #0F172A | 10.69:1 | 4.5:1 | warning text on the page | pass |
| light | `warning` #B45309 | `surfaceRaised` #F8FAFC | 4.80:1 | 4.5:1 | warning text on cards | pass |
| dark | `warning` #FBBF24 | `surfaceRaised` #172033 | 9.75:1 | 4.5:1 | warning text on cards | pass |
| light | `danger` #B91C1C | `surface` #FFFFFF | 6.47:1 | 4.5:1 | error text on the page | pass |
| dark | `danger` #F87171 | `surface` #0F172A | 6.45:1 | 4.5:1 | error text on the page | pass |
| light | `danger` #B91C1C | `surfaceRaised` #F8FAFC | 6.18:1 | 4.5:1 | error text on cards | pass |
| dark | `danger` #F87171 | `surfaceRaised` #172033 | 5.88:1 | 4.5:1 | error text on cards | pass |
| dark | `accentTextOnDark` #93C5FD | `surface` #0F172A | 9.90:1 | 4.5:1 | accent-text-on-dark on the dark page | pass |
| dark | `accentTextOnDark` #93C5FD | `surfaceRaised` #172033 | 9.02:1 | 4.5:1 | accent-text-on-dark on dark cards | pass |

<!-- contrast:end -->

## Other rules built into the design system

- Tap targets are at least 48 px (`--acb-target-min`), text at least 16 px, line height 1.5.
- Focus is always visible: a 3 px `accent` ring on `:focus-visible`.
- Status is never conveyed by colour alone: every status uses an icon and a word.
- Motion is 150 to 250 ms and is removed under `prefers-reduced-motion`.
- Light and dark mode follow the system and can be overridden with `data-theme` (Settings, a later phase).

## Still to do (later phases)

Automated axe checks in CI (phase 8), keyboard walk-through of every screen, largest-system-text-size testing, and mobile screen-reader review.
