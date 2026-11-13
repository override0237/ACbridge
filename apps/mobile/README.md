<p align="center"><img src="../../packages/brand/assets/wordmark.svg" alt="ACbridge" height="56"></p>

# ACbridge mobile (React Native, Expo)

**Status: scaffold, NOT yet run on a device.** This machine cannot run an Android emulator or Expo, so nothing in this folder has been
type-checked against React Native or executed. It is written to be verified on a developer machine.

What exists (phase 1):

- `src/theme/useTheme.ts`: light/dark colours from `@acbridge/tokens/theme` (the same values as the web CSS variables).
- `src/components/primitives.tsx`: `Button` (icon + label, 48 px target), `Card`, `Badge` (icon + word), `Body`.
- `src/app/App.tsx`: a shell that shows the primitives in the current system mode.

## Run it (on a machine with Node 20+, pnpm and Android Studio or a phone with Expo Go)

1. Remove the line `- "!apps/mobile"` from `pnpm-workspace.yaml` (the mobile app is excluded so the web install stays light).
2. `pnpm install` at the repository root.
3. `pnpm --filter @acbridge/mobile start`, then press `a` for the Android emulator, or scan the QR code with Expo Go.
4. `pnpm --filter @acbridge/mobile typecheck` and `pnpm --filter @acbridge/mobile test`.

## Environment variables

None yet. Later phases add `EXPO_PUBLIC_API_URL` (the backend URL, placeholder only in `.env.example`). No secret may ever be placed in an
`EXPO_PUBLIC_*` variable: they are bundled into the app.

## Rules

- No hex colour in a component (`pnpm check:hex`); colours come from the theme.
- Tokens are stored in secure storage (`expo-secure-store`), never `AsyncStorage`, when auth lands (phase 2).
- This app never imports `apps/web`. Shared code lives in `packages/core` and `packages/tokens`.
