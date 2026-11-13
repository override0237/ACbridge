/**
 * Pure SVG renderers for every logo variant. Geometry comes from paths.ts (extracted from the designer's file),
 * colours come from @acbridge/tokens. Nothing here contains a colour literal.
 *
 *   tone 'light'  : navy lettering, for light backgrounds
 *   tone 'on-ink' : near-white lettering, for the navy header, splash screens and dark surfaces
 * The gold glyph is the same in both tones.
 */
// Gradient id (a constant, so the string is not mistaken for a colour by the no-hex check).
const GOLD_ID = 'acb-gold';
import { colors } from '@acbridge/tokens';
import { MOTIFS, type MotifKind } from './motifs';
import { GLYPH, GLYPH_TRANSLATE, LETTERS_AC, LETTERS_BRIDGE, LOGO_HEIGHT, LOGO_VIEWBOX, LOGO_WIDTH, MARK_VIEWBOX } from './paths';

export type Tone = 'light' | 'on-ink';
const c = colors.light; // brand colours are identical in both modes (gold, ink, onInk)

const text = (tone: Tone): string => (tone === 'on-ink' ? c.onInk : c.ink);

const gradientDef = (id: string): string =>
  `<linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${GLYPH.gradient.x1}" y1="${GLYPH.gradient.y1}" x2="${GLYPH.gradient.x2}" y2="${GLYPH.gradient.y2}">` +
  `<stop offset="0" stop-color="${c.goldLight}"/><stop offset="1" stop-color="${c.goldDeep}"/></linearGradient>`;

const glyphShapes = (gradId: string): string =>
  `<g fill="none" stroke-linecap="round" stroke-linejoin="round">` +
  `<path d="${GLYPH.arch.d}" stroke="url(#${gradId})" stroke-width="${GLYPH.arch.strokeWidth}"/>` +
  `<path d="${GLYPH.baseline.d}" stroke="url(#${gradId})" stroke-width="${GLYPH.baseline.strokeWidth}"/>` +
  `<path d="${GLYPH.post.d}" stroke="url(#${gradId})" stroke-width="${GLYPH.post.strokeWidth}"/>` +
  GLYPH.dots.map((d) => `<circle cx="${d.cx}" cy="${d.cy}" r="${d.r}" fill="url(#${gradId})" stroke="none"/>`).join('') +
  `</g>`;

const open = (viewBox: string, width: number, height: number, label: string): string =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="${width}" height="${height}" role="img" aria-label="${label}"><title>${label}</title>`;

/** The full logo: AC + glyph + bridge. Transparent background (the designer's white rectangle is dropped so it works on any surface). */
export function renderWordmark(tone: Tone = 'light'): string {
  return open(LOGO_VIEWBOX, LOGO_WIDTH, LOGO_HEIGHT, 'ACbridge') +
    `<defs>${gradientDef('acb-gold')}</defs>` +
    `<path d="${LETTERS_AC}" fill="${text(tone)}"/>` +
    `<g transform="translate(${GLYPH_TRANSLATE.x},${GLYPH_TRANSLATE.y})">${glyphShapes('acb-gold')}</g>` +
    `<path d="${LETTERS_BRIDGE}" fill="${text(tone)}"/></svg>`;
}

/** The gold glyph alone (favicon, avatars, app icons). */
export function renderMark(): string {
  return open(MARK_VIEWBOX, 116, 88, 'ACbridge') + `<defs>${gradientDef('acb-gold')}</defs>${glyphShapes('acb-gold')}</svg>`;
}

/** Square app icon: navy tile with the gold mark centred. `rounded` for favicons/web, full-bleed for store icons and maskable use. */
export function renderAppIcon(opts: { rounded?: boolean; size?: number; scale?: number } = {}): string {
  const size = opts.size ?? 1024;
  const scale = opts.scale ?? 0.62; // share of the tile the mark's width may use (maskable icons keep it inside the safe zone)
  const markW = size * scale;
  const markH = markW * (88 / 116);
  const x = (size - markW) / 2;
  const y = (size - markH) / 2;
  const rx = opts.rounded ? size * 0.22 : 0;
  return open(`0 0 ${size} ${size}`, size, size, 'ACbridge') +
    `<rect width="${size}" height="${size}" rx="${rx}" fill="${c.ink}"/>` +
    `<svg x="${x}" y="${y}" width="${markW}" height="${markH}" viewBox="${MARK_VIEWBOX}"><defs>${gradientDef('acb-gold')}</defs>${glyphShapes('acb-gold')}</svg></svg>`;
}

/** Foreground for adaptive Android icons: the mark alone on transparent, inside the 66% safe zone. */
export function renderAdaptiveForeground(size = 1024): string {
  const markW = size * 0.5;
  const markH = markW * (88 / 116);
  return open(`0 0 ${size} ${size}`, size, size, 'ACbridge') +
    `<svg x="${(size - markW) / 2}" y="${(size - markH) / 2}" width="${markW}" height="${markH}" viewBox="${MARK_VIEWBOX}"><defs>${gradientDef('acb-gold')}</defs>${glyphShapes('acb-gold')}</svg></svg>`;
}

/** A navy canvas with the on-ink wordmark centred (splash screen, social preview). */
export function renderCanvas(width: number, height: number, wordmarkShare = 0.62): string {
  const w = width * wordmarkShare;
  const h = w * (LOGO_HEIGHT / LOGO_WIDTH);
  return open(`0 0 ${width} ${height}`, width, height, 'ACbridge') +
    `<rect width="${width}" height="${height}" fill="${c.ink}"/>` +
    `<svg x="${(width - w) / 2}" y="${(height - h) / 2}" width="${w}" height="${h}" viewBox="${LOGO_VIEWBOX}"><defs>${gradientDef('acb-gold')}</defs>` +
    `<path d="${LETTERS_AC}" fill="${c.onInk}"/><g transform="translate(${GLYPH_TRANSLATE.x},${GLYPH_TRANSLATE.y})">${glyphShapes('acb-gold')}</g>` +
    `<path d="${LETTERS_BRIDGE}" fill="${c.onInk}"/></svg></svg>`;
}

/** One page motif as a standalone SVG (docs and tests; the apps draw motifs from the same data). */
export function renderMotif(kind: MotifKind): string {
  const m = MOTIFS[kind];
  return open(m.viewBox, 96, 64, 'ACbridge') + `<defs>${gradientDef('acb-gold')}</defs><g fill="none" stroke-linecap="round" stroke-linejoin="round">` +
    m.strokes.map((s) => `<path d="${s.d}" stroke="url(#${GOLD_ID})" stroke-width="${s.strokeWidth}"/>`).join('') +
    m.dots.map((d) => `<circle cx="${d.cx}" cy="${d.cy}" r="${d.r}" fill="url(#${GOLD_ID})" stroke="none"/>`).join('') + `</g></svg>`;
}
