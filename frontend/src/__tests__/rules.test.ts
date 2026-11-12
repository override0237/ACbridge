import { describe, expect, it } from 'vitest';
import { SEED_ARTISANS } from '../data/seed';
import {
  checkCompletion, checkRating, checkVouch, countValidVouches, generateJobCode, hashCode, isVerified,
  normalizePhone, rankArtisans, trustScore,
} from '../domain/rules';
import { resolveTrade } from '../domain/trades';
import type { Artisan, Job, Rating, Vouch } from '../domain/types';

const seeds = (): Artisan[] => SEED_ARTISANS.map((a) => ({ ...a }));
const newbie = (): Artisan => ({
  id: 'n1', name: 'Newbie', phone: '+237670000999', trade: 'plumbing', neighbourhood: 'Neighbourhood A', description: '',
  baseRating: 0, baseJobs: 0, avgResponseMin: 20, priceMin: 3000, priceMax: 8000, seedVerified: false, isSeed: false,
  username: 'newbie', salt: 's', passwordHash: 'h',
});
const vouch = (artisanId: string, voucher: Artisan, id = voucher.id, workedTogether = true): Vouch =>
  ({ id: `v-${id}`, artisanId, voucherId: voucher.id, voucherPhone: voucher.phone, workedTogether, at: '', seal: '', prevHash: '', hash: '' });
const job = (over: Partial<Job> = {}): Job => ({
  id: 'j1', requestId: 'r1', artisanId: 'seed-1', customerPhone: '+237690000030', status: 'ACCEPTED',
  codeHash: hashCode('123456'), codeUsed: false, price: 5000, createdAt: '', ...over,
});

describe('verification', () => {
  it('one vouch does not verify; the second valid vouch does', () => {
    const all = [...seeds(), newbie()];
    const n = all[all.length - 1];
    const one = [vouch(n.id, all[0])];
    expect(isVerified(n, one, all)).toBe(false);
    const two = [...one, vouch(n.id, all[1])];
    expect(isVerified(n, two, all)).toBe(true);
  });
  it('rejects self, unverified, same-phone, duplicate and no-job vouches', () => {
    const all = [...seeds(), newbie()];
    const n = all[all.length - 1];
    expect(checkVouch(n, n, true, [])).toEqual({ ok: false, reason: 'self' });
    expect(checkVouch(n, all[4], true, [])).toEqual({ ok: false, reason: 'not_verified' }); // pending Samuel
    expect(checkVouch(n, { ...all[0], phone: n.phone }, true, [])).toEqual({ ok: false, reason: 'same_phone' });
    expect(checkVouch(n, all[0], true, [vouch(n.id, all[0])])).toEqual({ ok: false, reason: 'duplicate' });
    expect(checkVouch(n, all[0], false, [])).toEqual({ ok: false, reason: 'no_job_together' });
    expect(checkVouch(n, all[0], true, [])).toEqual({ ok: true });
  });
  it('counts distinct vouchers only, even if the same voucher is recorded twice', () => {
    const all = [...seeds(), newbie()];
    const n = all[all.length - 1];
    expect(countValidVouches(n, [vouch(n.id, all[0], 'a'), vouch(n.id, all[0], 'b')], all)).toBe(1);
  });
});

describe('job code', () => {
  it('generates 6 digits and hashes without storing plain text', () => {
    expect(generateJobCode(() => 0)).toBe('000000');
    expect(generateJobCode()).toMatch(/^\d{6}$/);
    expect(hashCode('123456')).not.toContain('123456');
  });
  it('completes only on a matching, unused code', () => {
    expect(checkCompletion(job(), '123456')).toEqual({ ok: true });
    expect(checkCompletion(job(), '654321')).toEqual({ ok: false, reason: 'wrong_code' });
    expect(checkCompletion(job(), '12')).toEqual({ ok: false, reason: 'bad_format' });
    expect(checkCompletion(job({ codeUsed: true }), '123456')).toEqual({ ok: false, reason: 'already_used' });
    expect(checkCompletion(job({ status: 'REQUESTED', codeHash: null }), '123456')).toEqual({ ok: false, reason: 'not_accepted' });
  });
});

describe('rating', () => {
  const done = job({ status: 'COMPLETED', codeUsed: true });
  const rated: Rating = { id: 'r', jobId: 'j1', artisanId: 'seed-1', score: 5, comment: '', at: '' };
  it('accepts one rating per completed job with an integer 1-5', () => {
    expect(checkRating(done, 5, [])).toEqual({ ok: true });
    expect(checkRating(done, 4, [rated])).toEqual({ ok: false, reason: 'already_rated' });
    expect(checkRating(done, 0, [])).toEqual({ ok: false, reason: 'bad_score' });
    expect(checkRating(done, 6, [])).toEqual({ ok: false, reason: 'bad_score' });
    expect(checkRating(done, 3.5, [])).toEqual({ ok: false, reason: 'bad_score' });
  });
  it('rejects a rating for a job that is not completed', () => {
    expect(checkRating(job(), 5, [])).toEqual({ ok: false, reason: 'not_completed' });
    expect(checkRating(undefined, 5, [])).toEqual({ ok: false, reason: 'not_completed' });
  });
});

describe('trust score', () => {
  it('weights the average by job count and adds 0.2 per vouch, capped at 5.0', () => {
    const a = { ...newbie(), baseRating: 4, baseJobs: 4 };
    const r = (score: number): Rating => ({ id: `${score}`, jobId: 'j', artisanId: a.id, score, comment: '', at: '' });
    expect(trustScore(a, [], 0)).toBeCloseTo(4);
    expect(trustScore(a, [r(5)], 0)).toBeCloseTo((16 + 5) / 5);
    expect(trustScore(a, [], 2)).toBeCloseTo(4.4);
    expect(trustScore({ ...a, baseRating: 4.9 }, [r(5)], 3)).toBe(5);
  });
  it('uses a neutral prior with no history', () => {
    expect(trustScore(newbie(), [], 2)).toBeCloseTo(3.4);
  });
});

describe('ranking', () => {
  it('returns only verified artisans of the asked trade, trust desc, then response time asc, max five', () => {
    const all = seeds();
    expect(rankArtisans(all, [], [], [], 'plumbing').map((r) => r.artisan.name)).toEqual(['Grace', 'Blaise']);
    // Samuel (pending electrician) is excluded; electricians ranked by trust
    expect(rankArtisans(all, [], [], [], 'electrical').map((r) => r.artisan.name)).toEqual(['Paul', 'Esther', 'Peter']);
    expect(rankArtisans(all, [], [], [], 'welder')).toEqual([]);
    const tie = all.map((a) => ({ ...a, baseRating: 4.5, avgResponseMin: a.id === 'seed-3' ? 1 : 10 }));
    expect(rankArtisans(tie, [], [], [], 'electrical')[0].artisan.name).toBe('Esther');
    const many = [...all, ...Array.from({ length: 6 }, (_, i) => ({ ...all[0], id: `x${i}`, name: `X${i}` }))];
    expect(rankArtisans(many, [], [], [], 'plumbing')).toHaveLength(5);
  });
});

describe('trades', () => {
  it('resolves what the user types in either language, or keeps free text', () => {
    expect(resolveTrade('Plombier')).toBe('plumbing');
    expect(resolveTrade(' électricien ')).toBe('electrical');
    expect(resolveTrade('Carpenter')).toBe('carpentry');
    expect(resolveTrade('Soudeur')).toBe('soudeur');
    expect(resolveTrade('x')).toBeNull();
  });
});

describe('phone', () => {
  it('normalises like the backend', () => {
    expect(normalizePhone('670 123 456')).toBe('+237670123456');
    expect(normalizePhone('237670123456')).toBe('+237670123456');
    expect(normalizePhone('12')).toBeNull();
  });
});
