import { describe, expect, it } from 'vitest';
import { checkAllPairs, contrastRatio } from './contrast';
import { renderCss, renderTheme } from './render';
import { colors } from './tokens';

describe('design tokens', () => {
  it('every foreground/background pair meets its WCAG ratio in light and dark', () => {
    const failing = checkAllPairs().filter((r) => !r.pass);
    expect(failing.map((r) => `${r.mode} ${r.fg}/${r.bg} ${r.ratio.toFixed(2)}`)).toEqual([]);
  });

  it('reproduces the numbers the spec states', () => {
    expect(contrastRatio('#2563EB', '#FFFFFF')).toBeGreaterThan(5.1); // about 5.2:1 on white: fine for text on light
    expect(contrastRatio('#FFFFFF', '#2563EB')).toBeGreaterThan(5.1); // white label on an accent button
    expect(contrastRatio('#2563EB', '#0F172A')).toBeLessThan(4.5); // the accent FAILS as text on dark ...
    expect(contrastRatio('#2563EB', '#0F172A')).toBeGreaterThan(3); // ... but is valid for focus rings (3:1)
    expect(contrastRatio(colors.dark.accentTextOnDark, '#0F172A')).toBeGreaterThan(4.5);
  });

  it('blue text on dark surfaces uses accent-text-on-dark, never the raw accent token', () => {
    expect(colors.dark.accentText).toBe(colors.dark.accentTextOnDark);
    expect(colors.dark.accentText).not.toBe(colors.dark.accent);
  });

  it('keeps the mandated palette values', () => {
    expect(colors.light).toMatchObject({ ink: '#0F172A', accent: '#2563EB', surface: '#FFFFFF', surfaceRaised: '#F8FAFC', border: '#CBD5E1', textMuted: '#475569' });
    expect(colors.dark).toMatchObject({ surface: '#0F172A', surfaceRaised: '#172033', border: '#334155', textMuted: '#94A3B8' });
  });

  it('generates CSS custom properties with light, system-dark and manual-dark blocks and reduced motion', () => {
    const css = renderCss();
    expect(css).toContain('--acb-color-accent: #2563EB;');
    expect(css).toContain('@media (prefers-color-scheme: dark)');
    expect(css).toContain(":root[data-theme='dark']");
    expect(css).toContain('prefers-reduced-motion: reduce');
    expect(renderTheme()).toContain('"accentText": "#93C5FD"');
  });
});
