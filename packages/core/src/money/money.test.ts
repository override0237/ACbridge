import { describe, expect, it } from 'vitest';
import { formatAmount, formatFcfa, formatRange } from './index';

describe('money', () => {
  it('formats whole FCFA per language', () => {
    expect(formatAmount(9000, 'en')).toBe('9,000');
    expect(formatAmount(9000, 'fr').replace(/\s/g, ' ')).toBe('9 000');
    expect(formatFcfa(500, 'en')).toBe('500 FCFA');
  });
  it('refuses non-integer amounts (no floats for money)', () => {
    expect(() => formatAmount(9000.5, 'en')).toThrow(RangeError);
  });
  it('shows a range, never a single number', () => {
    expect(formatRange(3000, 8000, 'en')).toBe('3,000 – 8,000 FCFA');
  });
});
