import { GLYPH, GLYPH_TRANSLATE, LETTERS_AC, LETTERS_BRIDGE, LOGO_HEIGHT, LOGO_VIEWBOX, LOGO_WIDTH, MARK_VIEWBOX, MOTIFS, type MotifKind } from '@acbridge/brand';
import { useId } from 'react';
import './brand.css';

/** A gold gradient definition. Stop colours are CSS variables (tokens), so nothing here is a colour literal. */
function GoldGradient({ id }: { id: string }) {
  return (
    <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={GLYPH.gradient.x1} y1={GLYPH.gradient.y1} x2={GLYPH.gradient.x2} y2={GLYPH.gradient.y2}>
      <stop offset="0" style={{ stopColor: 'var(--acb-color-gold-light)' }} />
      <stop offset="1" style={{ stopColor: 'var(--acb-color-gold-deep)' }} />
    </linearGradient>
  );
}

function GlyphShapes({ gradId }: { gradId: string }) {
  const stroke = `url(#${gradId})`;
  return (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d={GLYPH.arch.d} stroke={stroke} strokeWidth={GLYPH.arch.strokeWidth} />
      <path d={GLYPH.baseline.d} stroke={stroke} strokeWidth={GLYPH.baseline.strokeWidth} />
      <path d={GLYPH.post.d} stroke={stroke} strokeWidth={GLYPH.post.strokeWidth} />
      {GLYPH.dots.map((d, i) => <circle key={i} cx={d.cx} cy={d.cy} r={d.r} fill={stroke} stroke="none" />)}
    </g>
  );
}

/**
 * The ACbridge logo, drawn from the designer's own geometry (packages/brand).
 *  - `wordmark` = "AC" + gold glyph + "bridge";  `mark` = the gold glyph alone.
 *  - tone 'auto'  : lettering follows the theme (navy on light, near-white on dark);
 *    tone 'on-ink': near-white lettering, for the always-navy header.
 */
export function Logo({ variant = 'wordmark', tone = 'auto', height = 40, title = 'ACbridge' }: {
  variant?: 'wordmark' | 'mark'; tone?: 'auto' | 'on-ink'; height?: number; title?: string;
}) {
  const gradId = `acb-gold-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const letters = tone === 'on-ink' ? 'acb-logo-letters-on-ink' : 'acb-logo-letters';
  if (variant === 'mark') {
    return (
      <svg className="acb-logo acb-logo-mark" role="img" aria-label={title} viewBox={MARK_VIEWBOX} height={height} width={height * (116 / 88)}>
        <title>{title}</title>
        <defs><GoldGradient id={gradId} /></defs>
        <GlyphShapes gradId={gradId} />
      </svg>
    );
  }
  return (
    <svg className="acb-logo" role="img" aria-label={title} viewBox={LOGO_VIEWBOX} height={height} width={height * (LOGO_WIDTH / LOGO_HEIGHT)}>
      <title>{title}</title>
      <defs><GoldGradient id={gradId} /></defs>
      <path d={LETTERS_AC} className={letters} />
      <g transform={`translate(${GLYPH_TRANSLATE.x},${GLYPH_TRANSLATE.y})`}><GlyphShapes gradId={gradId} /></g>
      <path d={LETTERS_BRIDGE} className={letters} />
    </svg>
  );
}

/** A piece of the logo used as a screen's signature (decorative: hidden from screen readers). */
export function Motif({ kind, size = 56 }: { kind: MotifKind; size?: number }) {
  const m = MOTIFS[kind];
  const gradId = `acb-motif-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const stroke = `url(#${gradId})`;
  const [, , w, h] = m.viewBox.split(' ').map(Number);
  return (
    <svg className={`acb-motif acb-motif-${kind}`} aria-hidden="true" focusable="false" viewBox={m.viewBox} width={size} height={size * (h! / w!)}>
      <defs><GoldGradient id={gradId} /></defs>
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        {m.strokes.map((s, i) => <path key={i} d={s.d} stroke={stroke} strokeWidth={s.strokeWidth} />)}
        {m.dots.map((d, i) => <circle key={i} cx={d.cx} cy={d.cy} r={d.r} fill={stroke} stroke="none" />)}
      </g>
    </svg>
  );
}
