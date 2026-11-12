import { describe, expect, it } from 'vitest';
import { COMMISSION_RATE, MAX_COMMISSION_RATE, MIN_COMMISSION_RATE } from '../config';
import { SEED_ARTISANS } from '../data/seed';
import { agreedPrice, computeCommission, netRange } from '../domain/money';
import { checkVouch } from '../domain/rules';
import {
  GENESIS_HASH, checkNewCredentials, hasVouched, hashSecret, lastHash, makeCredentials, sealVouch, verifyLedger, verifyLogin,
} from '../domain/security';
import type { Artisan, Vouch } from '../domain/types';

describe('commission', () => {
  it('the chosen platform rate is inside 3%-7% (inclusive)', () => {
    expect(COMMISSION_RATE).toBeGreaterThanOrEqual(0.03);
    expect(COMMISSION_RATE).toBeLessThanOrEqual(0.07);
    expect(COMMISSION_RATE).toBe(0.05);
  });
  it('takes the commission from the artisan: price = commission + payout, whole francs', () => {
    const tx = computeCommission(5500);
    expect(tx).toMatchObject({ price: 5500, commission: 275, payout: 5225, ratePercent: 5 });
    expect(computeCommission(3333).commission + computeCommission(3333).payout).toBe(3333);
    expect(Number.isInteger(computeCommission(3333).commission)).toBe(true);
  });
  it('accepts 3% and 7% but refuses anything outside the band', () => {
    expect(() => computeCommission(1000, MIN_COMMISSION_RATE)).not.toThrow();
    expect(() => computeCommission(1000, MAX_COMMISSION_RATE)).not.toThrow();
    expect(() => computeCommission(1000, 0.02)).toThrow(RangeError);
    expect(() => computeCommission(1000, 0.08)).toThrow(RangeError);
    expect(() => computeCommission(-1)).toThrow(RangeError);
  });
  it('derives the simulated agreed price and net range from the artisan range', () => {
    const grace = SEED_ARTISANS[0]; // 3000-8000
    expect(agreedPrice(grace)).toBe(5500);
    expect(netRange(grace)).toEqual({ min: 2850, max: 7600 });
  });
});

describe('artisan credentials', () => {
  const all = SEED_ARTISANS;
  it('validates username, uniqueness, password length and confirmation', () => {
    expect(checkNewCredentials('ab', 'password123', 'password123', all)).toEqual({ ok: false, reason: 'username_format' });
    expect(checkNewCredentials('Grace', 'password123', 'password123', all)).toEqual({ ok: false, reason: 'username_taken' });
    expect(checkNewCredentials('newuser', 'short', 'short', all)).toEqual({ ok: false, reason: 'password_short' });
    expect(checkNewCredentials('newuser', 'password123', 'password124', all)).toEqual({ ok: false, reason: 'password_mismatch' });
    expect(checkNewCredentials('new.user-1', 'password123', 'password123', all)).toEqual({ ok: true });
  });
  it('logs in only with the right username AND password and never stores the password', () => {
    expect(verifyLogin(all, 'GRACE', 'Demo-Pass-123!')?.name).toBe('Grace');
    expect(verifyLogin(all, 'grace', 'wrong')).toBeNull();
    expect(verifyLogin(all, 'nobody', 'Demo-Pass-123!')).toBeNull();
    const c = makeCredentials('Zed', 'my-secret-pass', 'salt1');
    expect(JSON.stringify(c)).not.toContain('my-secret-pass');
    expect(c.passwordHash).not.toBe(hashSecret('my-secret-pass', 'salt2')); // salted
  });
  it('a rejected artisan cannot log in', () => {
    const rejected = all.map((a) => (a.username === 'grace' ? { ...a, rejected: true } : a));
    expect(verifyLogin(rejected, 'grace', 'Demo-Pass-123!')).toBeNull();
  });
});

describe('Vouch Seal ledger', () => {
  const [grace, paul, esther] = SEED_ARTISANS;
  const target: Artisan = { ...SEED_ARTISANS[4], id: 'target', phone: '+237670000123', username: 'target', seedVerified: false, isSeed: false };

  const chain = (): Vouch[] => {
    const out: Vouch[] = [];
    for (const [i, voucher] of [grace, paul, esther].entries()) {
      const at = `2026-01-0${i + 1}T00:00:00Z`;
      const seal = sealVouch(lastHash(out), target.id, voucher.id, at);
      out.push({ id: `v${i}`, artisanId: target.id, voucherId: voucher.id, voucherPhone: voucher.phone, workedTogether: true, at, ...seal });
    }
    return out;
  };

  it('chains every vouch to the previous one and verifies clean', () => {
    const v = chain();
    expect(v[0].prevHash).toBe(GENESIS_HASH);
    expect(v[1].prevHash).toBe(v[0].hash);
    expect(v[0].seal).toMatch(/^VS-[0-9A-F]{8}$/);
    expect(verifyLedger(v)).toEqual({ ok: true });
    expect(verifyLedger([])).toEqual({ ok: true });
  });
  it('detects tampering: edited, deleted, reordered and duplicated vouches', () => {
    const v = chain();
    expect(verifyLedger([{ ...v[0], voucherId: 'someone-else' }, v[1], v[2]])).toMatchObject({ ok: false, index: 0, reason: 'bad_hash' });
    expect(verifyLedger([v[0], v[2]])).toMatchObject({ ok: false, index: 1, reason: 'broken_chain' }); // deleted middle vouch
    expect(verifyLedger([v[1], v[0], v[2]])).toMatchObject({ ok: false, reason: 'broken_chain' });
    const dupSeal = sealVouch(lastHash(v), target.id, grace.id, '2026-02-01T00:00:00Z');
    const dup: Vouch = { ...v[0], id: 'dup', at: '2026-02-01T00:00:00Z', ...dupSeal };
    expect(verifyLedger([...v, dup])).toMatchObject({ ok: false, index: 3, reason: 'duplicate_pair' });
  });
  it('refuses a second vouch for the same pair (and the same phone) in the rules layer', () => {
    const v = chain();
    expect(hasVouched(grace.id, target.id, v)).toBe(true);
    expect(hasVouched(target.id, grace.id, v)).toBe(false);
    expect(checkVouch(target, grace, true, v)).toEqual({ ok: false, reason: 'duplicate' });
    expect(checkVouch(target, { ...grace, id: 'clone' }, true, v)).toEqual({ ok: false, reason: 'duplicate' }); // same phone, new id
  });
});
