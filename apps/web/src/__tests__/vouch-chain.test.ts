import { describe, expect, it } from 'vitest';
import { countValidVouches, isVerified } from '../domain/rules';
import type { Artisan } from '../domain/types';
import { initialState, reducer, type State } from '../store/reducer';

const at = '2026-01-01T00:00:00Z';
const ids = (n: number) => Array.from({ length: n }, (_, i) => `i${i}${Math.random()}`);
const newArtisan = (id: string, phone: string): Artisan => ({
  id, name: id, phone, trade: 'plumbing', neighbourhood: 'Neighbourhood A', description: '', baseRating: 0, baseJobs: 0,
  avgResponseMin: 20, priceMin: 3000, priceMax: 8000, seedVerified: false, isSeed: false, username: id, salt: 's', passwordHash: 'h',
});
const vouch = (s: State, artisanId: string, voucherId: string): State =>
  reducer(s, { type: 'vouch', artisanId, voucherId, workedTogether: true, vouchId: `v-${voucherId}-${artisanId}`, at, ids: ids(5) });

describe('an artisan who became verified through vouches can vouch too', () => {
  it('Joel is verified by two seed artisans, then his vouch for Ana goes through and counts', () => {
    let s = initialState();
    s = reducer(s, { type: 'register', artisan: newArtisan('joel', '+237670000111'), at, ids: ids(4) });
    s = reducer(s, { type: 'register', artisan: newArtisan('ana', '+237670000222'), at, ids: ids(4) });
    s = vouch(s, 'joel', 'seed-1');
    s = vouch(s, 'joel', 'seed-2');
    const joel = s.artisans.find((a) => a.id === 'joel')!;
    expect(isVerified(joel, s.vouches, s.artisans)).toBe(true);            // verified by vouches, not a seed account

    s = vouch(s, 'ana', 'joel');                                           // Joel vouches for Ana
    expect(s.vouches.filter((v) => v.artisanId === 'ana' && v.voucherId === 'joel')).toHaveLength(1);
    const ana = s.artisans.find((a) => a.id === 'ana')!;
    expect(countValidVouches(ana, s.vouches, s.artisans)).toBe(1);
    expect(s.sms.some((m) => m.key === 'sms.vouchSealed' && m.to === joel.phone)).toBe(true);
    expect(isVerified(ana, s.vouches, s.artisans)).toBe(false);            // one vouch is not enough...
    s = vouch(s, 'ana', 'seed-1');
    expect(isVerified(s.artisans.find((a) => a.id === 'ana')!, s.vouches, s.artisans)).toBe(true); // ...the second one is
  });

  it('an artisan who is NOT verified yet still cannot vouch, and vouch loops prove nothing', () => {
    let s = initialState();
    s = reducer(s, { type: 'register', artisan: newArtisan('a', '+237670000333'), at, ids: ids(4) });
    s = reducer(s, { type: 'register', artisan: newArtisan('b', '+237670000444'), at, ids: ids(4) });
    s = vouch(s, 'b', 'a');                                                // a is unverified: refused
    expect(s.vouches).toHaveLength(0);
    s = vouch(s, 'a', 'seed-1');                                           // a has one vouch only
    s = vouch(s, 'b', 'a');                                                // still not verified: refused
    expect(s.vouches.filter((v) => v.artisanId === 'b')).toHaveLength(0);
  });
});
