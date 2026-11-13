/**
 * THE single source of design tokens. Nothing else in the repository may contain a hex colour
 * (scripts/check-no-hex.ts enforces it). `build.ts` turns this file into CSS custom properties (web) and a theme object
 * (React Native); `contrast.ts` checks every foreground/background pair below.
 *
 * The palette is mandated by the product spec (section 3.1). `text`, `accentText`, `borderStrong` and the status colours
 * are DERIVED roles that do not change the mandated values:
 *   - text         = `ink` on light, a near-white on dark (ink is the dark-mode PAGE background, so it cannot be dark text on dark).
 *   - accentText   = accent on light surfaces; `accentTextOnDark` on dark surfaces (accent fails 4.5:1 for text on #0F172A).
 *   - borderStrong = outline for inputs and controls: the mandated `border` is a divider colour and is below 3:1 on white.
 */
export type Mode = 'light' | 'dark';

export interface ColorSet {
  ink: string;
  text: string;
  accent: string;
  accentText: string;
  accentTextOnDark: string;
  onAccent: string;
  surface: string;
  surfaceRaised: string;
  border: string;
  borderStrong: string;
  textMuted: string;
  success: string;
  warning: string;
  danger: string;
}

export const colors: Record<Mode, ColorSet> = {
  light: {
    ink: '#0F172A',
    text: '#0F172A',
    accent: '#2563EB',
    accentText: '#2563EB',
    accentTextOnDark: '#93C5FD',
    onAccent: '#FFFFFF',
    surface: '#FFFFFF',
    surfaceRaised: '#F8FAFC',
    border: '#CBD5E1',
    borderStrong: '#64748B',
    textMuted: '#475569',
    success: '#15803D',
    warning: '#B45309',
    danger: '#B91C1C',
  },
  dark: {
    ink: '#0F172A',
    text: '#F8FAFC',
    accent: '#2563EB',
    accentText: '#93C5FD',
    accentTextOnDark: '#93C5FD',
    onAccent: '#FFFFFF',
    surface: '#0F172A',
    surfaceRaised: '#172033',
    border: '#334155',
    borderStrong: '#64748B',
    textMuted: '#94A3B8',
    success: '#4ADE80',
    warning: '#FBBF24',
    danger: '#F87171',
  },
};

/** 4 px base scale. Keys are multiples of 4 px (space[4] = 16 px). */
export const space = { 0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64 } as const;

/** ONE radius for cards, ONE for buttons (and inputs), one for pills. */
export const radius = { card: 16, button: 12, pill: 999 } as const;

/** ONE shadow level. */
export const shadow = { raised: '0 1px 2px rgba(15, 23, 42, 0.08), 0 2px 8px rgba(15, 23, 42, 0.06)' } as const;

/** System font stack only: no web fonts, so nothing extra to download. Sizes in px. */
export const type = {
  fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  size: { body: 16, instruction: 18, small: 16, heading: 24, display: 30 },
  lineHeight: 1.5,
  weight: { regular: 400, medium: 500, bold: 700 },
} as const;

/** Tap targets are at least 48 px. */
export const target = { min: 48 } as const;

/** Motion is short (150 to 250 ms) and is switched off by the reduced-motion setting. */
export const motion = { fast: 150, base: 200, slow: 250 } as const;

export const layout = { maxContentWidth: 960 } as const;

/** Every foreground/background pair that is checked, with the contrast ratio it must reach (WCAG 2.2 AA). */
export interface Pair { fg: keyof ColorSet; bg: keyof ColorSet; min: number; modes: Mode[]; why: string }
export const pairs: Pair[] = [
  { fg: 'text', bg: 'surface', min: 4.5, modes: ['light', 'dark'], why: 'body text on the page' },
  { fg: 'text', bg: 'surfaceRaised', min: 4.5, modes: ['light', 'dark'], why: 'body text on cards and sheets' },
  { fg: 'textMuted', bg: 'surface', min: 4.5, modes: ['light', 'dark'], why: 'secondary text on the page' },
  { fg: 'textMuted', bg: 'surfaceRaised', min: 4.5, modes: ['light', 'dark'], why: 'secondary text on cards' },
  { fg: 'accentText', bg: 'surface', min: 4.5, modes: ['light', 'dark'], why: 'links and accent text on the page' },
  { fg: 'accentText', bg: 'surfaceRaised', min: 4.5, modes: ['light', 'dark'], why: 'links and accent text on cards' },
  { fg: 'onAccent', bg: 'accent', min: 4.5, modes: ['light', 'dark'], why: 'label text on accent buttons' },
  { fg: 'accent', bg: 'surface', min: 3, modes: ['light', 'dark'], why: 'focus ring and selected outline against the page (non-text, 3:1)' },
  { fg: 'accent', bg: 'surfaceRaised', min: 3, modes: ['light', 'dark'], why: 'focus ring and selected outline against cards (non-text, 3:1)' },
  { fg: 'borderStrong', bg: 'surface', min: 3, modes: ['light', 'dark'], why: 'input outlines against the page (non-text, 3:1)' },
  { fg: 'borderStrong', bg: 'surfaceRaised', min: 3, modes: ['light', 'dark'], why: 'input outlines against cards (non-text, 3:1)' },
  { fg: 'success', bg: 'surface', min: 4.5, modes: ['light', 'dark'], why: 'success text on the page' },
  { fg: 'success', bg: 'surfaceRaised', min: 4.5, modes: ['light', 'dark'], why: 'success text on cards' },
  { fg: 'warning', bg: 'surface', min: 4.5, modes: ['light', 'dark'], why: 'warning text on the page' },
  { fg: 'warning', bg: 'surfaceRaised', min: 4.5, modes: ['light', 'dark'], why: 'warning text on cards' },
  { fg: 'danger', bg: 'surface', min: 4.5, modes: ['light', 'dark'], why: 'error text on the page' },
  { fg: 'danger', bg: 'surfaceRaised', min: 4.5, modes: ['light', 'dark'], why: 'error text on cards' },
  // The mandated rule: the accent token must NOT be the text/link colour on dark surfaces.
  { fg: 'accentTextOnDark', bg: 'surface', min: 4.5, modes: ['dark'], why: 'accent-text-on-dark on the dark page' },
  { fg: 'accentTextOnDark', bg: 'surfaceRaised', min: 4.5, modes: ['dark'], why: 'accent-text-on-dark on dark cards' },
];
