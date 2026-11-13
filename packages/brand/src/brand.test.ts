// @ts-nocheck  (Node-only test: it reads the designer's SVG and the generated assets from disk)
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { colors } from '@acbridge/tokens';
import { GLYPH, LETTERS_AC, LETTERS_BRIDGE, MOTIFS, SCREEN_MOTIF, renderAdaptiveForeground, renderAppIcon, renderCanvas, renderMark, renderMotif, renderWordmark } from './index';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const original = readFileSync(join(root, 'logo', 'acbridge_logo.svg'), 'utf8');

describe('the logo geometry is the designer\'s, unchanged', () => {
  it('lettering and glyph paths appear verbatim in logo/acbridge_logo.svg', () => {
    expect(original).toContain(LETTERS_AC);
    expect(original).toContain(LETTERS_BRIDGE);
    for (const part of [GLYPH.arch, GLYPH.baseline, GLYPH.post]) expect(original).toContain(`d="${part.d}"`);
    expect(original).toContain('stop-color="#F7D774"');
    expect(original).toContain('stop-color="#B8860B"');
  });

  it('the gradient colours come from the tokens (and equal the logo\'s)', () => {
    expect(colors.light.goldLight).toBe('#F7D774');
    expect(colors.light.goldDeep).toBe('#B8860B');
    expect(colors.light.ink).toBe('#0F172A');
  });
});

describe('every variant is a complete, accessible SVG', () => {
  const variants = {
    wordmark: renderWordmark('light'),
    'wordmark on ink': renderWordmark('on-ink'),
    mark: renderMark(),
    'app icon': renderAppIcon({ rounded: true }),
    'app icon square': renderAppIcon({ rounded: false }),
    'adaptive foreground': renderAdaptiveForeground(),
    splash: renderCanvas(1284, 2778, 0.7),
    'social card': renderCanvas(1200, 630, 0.6),
  };
  for (const [name, svg] of Object.entries(variants)) {
    it(`${name}: titled, labelled, balanced tags and uses the gold gradient`, () => {
      expect(svg.startsWith('<svg')).toBe(true);
      expect(svg).toContain('role="img"');
      expect(svg).toContain('<title>ACbridge</title>');
      expect(svg).toContain('stop-color');
      expect((svg.match(/<svg/g) ?? []).length).toBe((svg.match(/<\/svg>/g) ?? []).length);
    });
  }

  it('the wordmark has NO white background rectangle (it must work on any surface)', () => {
    expect(renderWordmark('light')).not.toMatch(/<rect/);
    expect(renderWordmark('on-ink')).not.toMatch(/<rect/);
  });

  it('lettering is navy on light and near-white on navy; the gold glyph is the same in both', () => {
    expect(renderWordmark('light')).toContain(`fill="${colors.light.ink}"`);
    expect(renderWordmark('on-ink')).toContain(`fill="${colors.light.onInk}"`);
    expect(renderWordmark('on-ink')).not.toContain(`fill="${colors.light.ink}"`);
    for (const tone of ['light', 'on-ink']) expect(renderWordmark(tone)).toContain(colors.light.goldDeep);
  });

  it('only token colours are used (no stray hex values)', () => {
    const allowed = new Set(Object.values(colors.light).concat(Object.values(colors.dark)).map((h) => h.toUpperCase()));
    for (const svg of Object.values(variants)) {
      for (const hex of svg.match(/#[0-9A-Fa-f]{6}\b/g) ?? []) expect(allowed.has(hex.toUpperCase())).toBe(true);
    }
  });

  it('the app icon keeps the mark inside the safe zone', () => {
    const svg = renderAppIcon({ rounded: false, size: 1024, scale: 0.62 });
    const w = Number(/<svg x="[\d.]+" y="[\d.]+" width="([\d.]+)"/.exec(svg)[1]);
    expect(w / 1024).toBeLessThanOrEqual(0.66);
  });
});

describe('the committed asset files match the renderers', () => {
  it.each([
    ['wordmark.svg', renderWordmark('light')],
    ['wordmark-on-ink.svg', renderWordmark('on-ink')],
    ['mark.svg', renderMark()],
    ['app-icon.svg', renderAppIcon({ rounded: true })],
    ['motif-span.svg', renderMotif('span')],
  ])('%s is up to date', (file, svg) => {
    expect(readFileSync(join(root, 'packages', 'brand', 'assets', file), 'utf8').trim()).toBe(svg.trim());
  });
});

describe('page motifs', () => {
  it('every motif is built only from the logo\'s own strokes', () => {
    const allowed = new Set([GLYPH.arch.d, GLYPH.baseline.d, GLYPH.post.d]);
    for (const m of Object.values(MOTIFS)) for (const s of m.strokes) expect(allowed.has(s.d)).toBe(true);
  });

  it('every screen of the web app has a motif, and the motifs are varied', () => {
    const screens = ['home', 'artisanEntry', 'artisanLogin', 'artisanSignup', 'artisanStatus', 'artisanInbox', 'artisanComplete', 'customerRequest', 'matches', 'tracking', 'chat', 'payments', 'rate', 'operator', 'profile'];
    expect(Object.keys(SCREEN_MOTIF).sort()).toEqual(screens.sort());
    expect(new Set(Object.values(SCREEN_MOTIF)).size).toBeGreaterThanOrEqual(4);
  });
});
