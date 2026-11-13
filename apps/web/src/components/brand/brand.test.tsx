// @vitest-environment jsdom
// @ts-nocheck  (reads CSS files with Node's fs; the app itself has no Node typings)
import { cleanup, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SCREEN_MOTIF } from '@acbridge/brand';
import App from '../../App';
import { Logo, Motif } from './Logo';

beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, String(v)), removeItem: (k: string) => void store.delete(k), clear: () => store.clear() });
});
afterEach(cleanup);

describe('Logo', () => {
  it('is an image named ACbridge with the lettering and the gold glyph', () => {
    render(<Logo />);
    const svg = screen.getByRole('img', { name: 'ACbridge' });
    expect(svg.querySelectorAll('path.acb-logo-letters').length).toBe(2); // "AC" and "bridge"
    expect(svg.querySelectorAll('linearGradient stop').length).toBe(2);
    expect(svg.querySelectorAll('circle').length).toBe(2); // the foot and the tip of the post
  });

  it('lettering follows the theme by default and is near-white on the navy header', () => {
    const { container } = render(<><Logo /><Logo tone="on-ink" /></>);
    expect(container.querySelectorAll('.acb-logo-letters').length).toBe(2);
    expect(container.querySelectorAll('.acb-logo-letters-on-ink').length).toBe(2);
  });

  it('the mark variant is just the glyph (no lettering) and keeps its proportions', () => {
    render(<Logo variant="mark" height={44} />);
    const svg = screen.getByRole('img', { name: 'ACbridge' });
    expect(svg.querySelectorAll('path.acb-logo-letters').length).toBe(0);
    expect(svg.getAttribute('height')).toBe('44');
  });

  it('gradient ids are unique per instance (several logos on one page do not clash)', () => {
    const { container } = render(<><Logo /><Logo /><Motif kind="arch" /></>);
    const ids = [...container.querySelectorAll('linearGradient')].map((g) => g.id);
    expect(new Set(ids).size).toBe(3);
    for (const id of ids) expect(id).toMatch(/^acb-(gold|motif)-[a-zA-Z0-9]+$/);
  });

  it('Motif is decorative: hidden from screen readers and not focusable', () => {
    const { container } = render(<Motif kind="span" />);
    const svg = container.querySelector('svg');
    expect(svg.getAttribute('aria-hidden')).toBe('true');
    expect(svg.getAttribute('focusable')).toBe('false');
  });
});

describe('the app wears the logo', () => {
  it('the header shows the wordmark (on navy) and the footer the mark', () => {
    const { container } = render(<App />);
    const brandButton = screen.getByRole('button', { name: /accueil/i });
    expect(brandButton.querySelector('svg.acb-logo .acb-logo-letters-on-ink')).not.toBeNull();
    expect(container.querySelector('.foot svg.acb-logo-mark')).not.toBeNull();
  });

  it('every screen is signed with its own motif of the logo (home: the whole mark)', () => {
    const { container } = render(<App />);
    const home = container.querySelector('.screen[data-screen="home"]');
    expect(home).not.toBeNull();
    expect(home.querySelector('.acb-motif-' + SCREEN_MOTIF.home)).not.toBeNull();
    expect(home.querySelector('.gold-rule')).not.toBeNull();
  });
});

describe('brand.css uses only tokens', () => {
  const css = readFileSync(join(process.cwd(), 'src', 'components', 'brand', 'brand.css'), 'utf8');
  const tokens = readFileSync(join(process.cwd(), '..', '..', 'packages', 'tokens', 'generated', 'tokens.css'), 'utf8');
  it('no hex colours, and every variable it uses exists', () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    const used = new Set([...css.matchAll(/var\((--acb-[a-z0-9-]+)/g)].map((m) => m[1]));
    expect([...used].filter((v) => !tokens.includes(`${v}:`))).toEqual([]);
  });
});
