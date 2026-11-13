# Performance

Budgets from the spec: web first-load JavaScript under 250 KB gzipped, first contentful paint under 2 s on simulated 3G, mobile cold start under 3 s,
skeletons for any response slower than 300 ms.

## Measured so far (phase 1)

| Measure | Result | Budget | Notes |
|---|---|---|---|
| Web first-load JavaScript, gzipped | **92 KB** (`gzip -9` of `index-*.js`; Vite reports 94.65 kB) | 250 KB | Includes React and the demo app. No web fonts, one icon set (`lucide-react`, tree-shaken). |
| Web CSS, gzipped | 3.1 KB | n/a | |
| Single-file demo (`acbridge.html`) | 332 KB raw | n/a | Inlined JS + CSS, used for opening the demo by double-click. |
| Mobile cold start | **not measured** | 3 s | Needs a device or emulator, not available in this environment. |
| Web FCP on simulated 3G | **not measured** | 2 s | Needs Lighthouse/Playwright throttling in CI (phase 8). |

Reproduce the size numbers: `pnpm --filter @acbridge/web build`, then `gzip -9 -c apps/web/dist/assets/index-*.js | wc -c`.

## To measure later

Lighthouse CI on a 3G profile (phase 8), the largest-contentful-paint of the match list with a throttled API, and a mid-range Android cold start.
