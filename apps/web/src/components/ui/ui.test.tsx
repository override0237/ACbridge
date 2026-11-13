// @vitest-environment jsdom
// @ts-nocheck  (reads CSS files with Node's fs; the app itself has no Node typings)
import { cleanup, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Check } from 'lucide-react';
import { afterEach, describe, expect, it } from 'vitest';
import { Styleguide } from '../../styleguide/Styleguide';
import { Badge, Button, Card, EmptyState, ErrorState, Field, Skeleton } from './index';

afterEach(cleanup);

describe('design-system primitives', () => {
  it('Button always has an icon AND a label, and is a real button', () => {
    render(<Button icon={Check} label="Confirm" />);
    const b = screen.getByRole('button', { name: 'Confirm' });
    expect(b.querySelector('svg')).not.toBeNull();
    expect(b.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    expect(b.getAttribute('type')).toBe('button');
    expect(b.className).toContain('acb-btn-primary');
  });

  it('Field has a visible label linked to the control, and announces its error', () => {
    render(<Field label="Phone number" error="Enter a valid phone number." hint="Example: 670123456" />);
    const input = screen.getByLabelText('Phone number');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toContain('hint');
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Enter a valid phone number.');
    expect(alert.getAttribute('aria-live')).toBe('assertive');
  });

  it('Field without an error has an empty (but present) live region', () => {
    render(<Field label="Name" />);
    expect(screen.getByRole('alert').textContent).toBe('');
    expect(screen.getByLabelText('Name').getAttribute('aria-invalid')).toBeNull();
  });

  it('Badge is icon + word, never colour alone', () => {
    render(<Badge tone="success">Verified</Badge>);
    const badge = screen.getByText('Verified').closest('.acb-badge')!;
    expect(badge.querySelector('svg')).not.toBeNull();
    expect(badge.textContent).toBe('Verified');
  });

  it('Skeleton is announced as busy; Empty and Error states say what to do next', () => {
    render(<><Skeleton lines={2} /><EmptyState title="No requests yet" body="Share your profile." /><ErrorState title="Could not load" body="Try again." /></>);
    expect(screen.getByRole('status').getAttribute('aria-busy')).toBe('true');
    expect(screen.getByRole('heading', { name: 'No requests yet' })).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('Could not load');
  });

  it('Card renders a titled region', () => {
    render(<Card title="Agreed price">9 000 FCFA</Card>);
    expect(screen.getByRole('heading', { name: 'Agreed price' })).toBeTruthy();
  });

  it('the style guide shows every primitive in BOTH light and dark', () => {
    render(<Styleguide />);
    for (const id of ['light', 'dark']) {
      const region = screen.getByTestId(id);
      expect(region.className).toContain(`acb-theme-${id}`);
      expect(region.querySelectorAll('.acb-btn').length).toBeGreaterThanOrEqual(5);
      expect(region.querySelector('.acb-badge')).not.toBeNull();
      expect(region.querySelector('.acb-skeleton')).not.toBeNull();
      expect(region.querySelector('.acb-state-error')).not.toBeNull();
    }
  });
});

describe('the primitives only use design tokens', () => {
  const dir = join(process.cwd(), 'src', 'components', 'ui');
  const css = readFileSync(join(dir, 'ui.css'), 'utf8');
  const tokens = readFileSync(join(process.cwd(), '..', '..', 'packages', 'tokens', 'generated', 'tokens.css'), 'utf8');

  it('contain no hex colours', () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(readFileSync(join(dir, 'primitives.tsx'), 'utf8')).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });

  it('every var(--acb-*) they use is defined by the generated tokens', () => {
    const used = new Set([...css.matchAll(/var\((--acb-[a-z0-9-]+)/g)].map((m) => m[1]));
    const missing = [...used].filter((v) => !tokens.includes(`${v}:`));
    expect(missing).toEqual([]);
  });

  it('tap targets use the 48 px token and the focus ring uses the accent token', () => {
    expect(css).toContain('min-height: var(--acb-target-min)');
    expect(css).toMatch(/outline: 3px solid var\(--acb-color-accent\)/);
  });
});
