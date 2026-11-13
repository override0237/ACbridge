/** WCAG 2.x contrast maths (sRGB relative luminance). Used by the build check and by the tests. */
import { colors, pairs, type ColorSet, type Mode } from './tokens';

export function hexToRgb(hex: string): [number, number, number] {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`Not a 6-digit hex colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export interface PairResult { mode: Mode; fg: keyof ColorSet; bg: keyof ColorSet; fgHex: string; bgHex: string; ratio: number; min: number; pass: boolean; why: string }

/** Every pair, in every mode it applies to, with its measured ratio. */
export function checkAllPairs(): PairResult[] {
  const out: PairResult[] = [];
  for (const p of pairs) {
    for (const mode of p.modes) {
      const set = colors[mode];
      const ratio = contrastRatio(set[p.fg], set[p.bg]);
      out.push({ mode, fg: p.fg, bg: p.bg, fgHex: set[p.fg], bgHex: set[p.bg], ratio, min: p.min, pass: ratio >= p.min, why: p.why });
    }
  }
  return out;
}
