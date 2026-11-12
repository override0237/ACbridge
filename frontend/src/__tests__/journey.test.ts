import { describe, expect, it } from 'vitest';
import { generateJobCode, rankArtisans } from '../domain/rules';
import { initialState, reducer, type State } from '../store/reducer';
import type { Artisan } from '../domain/types';

const at = '2026-01-01T00:00:00Z';
const e = (n: number) => Array.from({ length: n }, (_, i) => `id${i}${Math.random()}`);

describe('mandatory journey (reducer + rules)', () => {
  it('runs register, 2 vouches, request, choose, accept, wrong code, right code, rate once', () => {
    let s: State = initialState();
    const art: Artisan = {
      id: 'new', name: 'Joel', phone: '+237670111222', trade: 'plumbing', neighbourhood: 'Neighbourhood A', description: '',
      baseRating: 0, baseJobs: 0, avgResponseMin: 20, priceMin: 3000, priceMax: 8000, seedVerified: false, isSeed: false, username: 'joel', salt: 's', passwordHash: 'h',
    };
    s = reducer(s, { type: 'register', artisan: art, at, ids: e(4) });
    expect(s.sms.filter((m) => m.key === 'sms.vouchRequest')).toHaveLength(2);

    s = reducer(s, { type: 'vouch', artisanId: 'new', voucherId: 'seed-1', workedTogether: true, vouchId: 'v1', at, ids: e(5) });
    expect(rankArtisans(s.artisans, s.vouches, s.ratings, s.jobs, 'plumbing').some((r) => r.artisan.id === 'new')).toBe(false);
    s = reducer(s, { type: 'vouch', artisanId: 'new', voucherId: 'seed-2', workedTogether: true, vouchId: 'v2', at, ids: e(5) });
    const ranked = rankArtisans(s.artisans, s.vouches, s.ratings, s.jobs, 'plumbing');
    expect(ranked.map((r) => r.artisan.name)).toEqual(['Grace', 'Blaise', 'Joel']);
    expect(ranked.some((r) => r.artisan.id === 'new')).toBe(true);
    expect(s.sms.some((m) => m.key === 'sms.verified')).toBe(true);

    s = reducer(s, {
      type: 'request',
      request: { id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: '', at },
    });
    s = reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'new', price: 5000, at, ids: e(1) });
    const code = generateJobCode();
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, code, at, ids: e(2) });
    const codeSms = s.sms.find((m) => m.key === 'sms.jobCode')!;
    expect(codeSms.to).toBe('+237690000030');
    expect(codeSms.params.code).toBe(code);
    expect(JSON.stringify(s.jobs)).not.toContain(code); // only the hash is stored on the job

    const wrong = code === '000000' ? '000001' : '000000';
    s = reducer(s, { type: 'complete', jobId: 'job', entered: wrong, at, ids: e(4) });
    expect(s.jobs[0].status).toBe('ACCEPTED');
    s = reducer(s, { type: 'complete', jobId: 'job', entered: code, at, ids: e(4) });
    expect(s.jobs[0].status).toBe('COMPLETED');
    // 5% commission taken from the artisan: 5000 -> 250 commission, 4750 payout
    expect(s.jobs[0]).toMatchObject({ commissionRate: 0.05, commission: 250, payout: 4750 });
    expect(s.sms.find((m) => m.key === 'sms.payout')).toMatchObject({ to: '+237670111222', params: { price: 5000, rate: 5, commission: 250, payout: 4750 } });
    expect(s.audit.find((x) => x.kind === 'transaction')?.params).toMatchObject({ commission: 250, payout: 4750 });
    s = reducer(s, { type: 'complete', jobId: 'job', entered: code, at, ids: e(4) }); // replay is ignored
    expect(s.audit.filter((x) => x.kind === 'job_completed')).toHaveLength(1);

    s = reducer(s, { type: 'rate', ratingId: 'r1', jobId: 'job', score: 5, comment: 'Good', at, ids: e(3) });
    s = reducer(s, { type: 'rate', ratingId: 'r2', jobId: 'job', score: 1, comment: 'again', at, ids: e(3) });
    expect(s.ratings).toHaveLength(1);
    expect(s.audit.some((x) => x.kind === 'trust')).toBe(true);
  });
});
