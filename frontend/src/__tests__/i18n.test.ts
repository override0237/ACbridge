import { describe, expect, it } from 'vitest';
import { en } from '../i18n/en';
import { fr } from '../i18n/fr';
import { dictionaries, translate } from '../i18n';

describe('translations', () => {
  it('fr and en have identical keys', () => {
    expect(Object.keys(fr).sort()).toEqual(Object.keys(en).sort());
  });
  it('has no empty strings', () => {
    for (const d of [fr, en]) for (const [k, v] of Object.entries(d)) expect([k, v.length > 0]).toEqual([k, true]);
  });
  it('local slot falls back to French and interpolates', () => {
    expect(dictionaries.local['home.title']).toBe(fr['home.title']);
    expect(translate('en', 'status.count', { n: 1, total: 2 })).toBe('1 of 2 vouches');
  });
});
