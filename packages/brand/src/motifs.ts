/**
 * Page motifs: pieces of the logo's glyph, reused as the visual signature of each screen. The logo's glyph is made of
 *   - a leaning POST with a round foot and tip (the artisan's tool / the person),
 *   - an ARCH span (the bridge of trust),
 *   - a BASELINE with round caps (the ground both sides stand on).
 * Each motif is data (strokes + dots + viewBox) so web and React Native draw it identically.
 */
import { GLYPH, MARK_VIEWBOX } from './paths';

export type MotifKind = 'mark' | 'arch' | 'post' | 'baseline' | 'span';

export interface MotifStroke { d: string; strokeWidth: number }
export interface Motif { viewBox: string; strokes: MotifStroke[]; dots: { cx: number; cy: number; r: number }[] }

const footDot = GLYPH.dots[0]!;
const tipDot = GLYPH.dots[1]!;

export const MOTIFS: Record<MotifKind, Motif> = {
  /** The whole glyph: post + arch + baseline. */
  mark: { viewBox: MARK_VIEWBOX, strokes: [GLYPH.arch, GLYPH.baseline, GLYPH.post], dots: [footDot, tipDot] },
  /** Just the bridge span. */
  arch: { viewBox: '30 42 72 44', strokes: [GLYPH.arch], dots: [] },
  /** Just the leaning post with its round ends. */
  post: { viewBox: '-6 4 40 90', strokes: [GLYPH.post], dots: [footDot, tipDot] },
  /** The ground line with the round foot. */
  baseline: { viewBox: '-8 66 116 28', strokes: [GLYPH.baseline], dots: [footDot] },
  /** Arch over the baseline: a bridge span carrying something across. */
  span: { viewBox: '-8 42 116 50', strokes: [GLYPH.arch, GLYPH.baseline], dots: [footDot] },
};

/** Which motif signs which screen. Every screen of the web app must be listed (a test enforces it). */
export const SCREEN_MOTIF = {
  home: 'mark',
  artisanEntry: 'post',
  artisanLogin: 'post',
  artisanSignup: 'post',
  artisanStatus: 'arch',
  artisanInbox: 'post',
  artisanComplete: 'post',
  customerRequest: 'baseline',
  matches: 'arch',
  tracking: 'span',
  chat: 'baseline',
  payments: 'span',
  rate: 'arch',
  operator: 'baseline',
  profile: 'arch',
} as const satisfies Record<string, MotifKind>;

export type ScreenName = keyof typeof SCREEN_MOTIF;
