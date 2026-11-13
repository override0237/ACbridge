import { describe, expect, it } from 'vitest';
import { maskPhone, normalizePhone, stripPhones } from './index';

describe('phone normalisation', () => {
  it.each([
    ['670123456', '+237670123456'],
    ['670 123 456', '+237670123456'],
    ['237670123456', '+237670123456'],
    ['+237 670-123-456', '+237670123456'],
    ['+33 6 12 34 56 78', '+33612345678'],
  ])('%s -> %s', (raw, expected) => expect(normalizePhone(raw)).toBe(expected));

  it.each(['', '12', 'abc', '0670123456', '+0123456789'])('rejects %j', (raw) => expect(normalizePhone(raw)).toBeNull());
});

describe('phone masking', () => {
  it('shows only the first and last digits', () => {
    expect(maskPhone('+237670123456')).toBe('+237 6******56');
    expect(maskPhone('+237670123456')).not.toContain('70123');
    expect(maskPhone('123')).toBe('***');
  });
  it('removes phone numbers from free text', () => {
    expect(stripPhones('call +237 670 123 456 or 670123456 now')).toBe('call [phone] or [phone] now');
    expect(stripPhones('price 9000 FCFA')).toBe('price 9000 FCFA');
  });
});
