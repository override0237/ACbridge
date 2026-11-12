/**
 * Pure business rules. The UI and reducer call these and never re-implement them.
 * Vocabulary follows the backend: vouch = endorsement, trust score = reputation,
 * completion by job code = both-sides-confirmed completion.
 */
import { MAX_MATCHES, VOUCHES_REQUIRED } from '../config';
import { sameTrade } from './trades';
import type { Artisan, Job, Rating, Vouch } from './types';

export const NEUTRAL_RATING = 3.0; // used when an artisan has no rating history yet
export const VOUCH_BONUS = 0.2;
export const MAX_TRUST = 5.0;

// ---------------------------------------------------------------- vouches / verification
const isTrusted = (a: Artisan): boolean => !a.rejected && (a.seedVerified || !!a.operatorApproved);

export type VouchCheck =
  | { ok: true }
  | { ok: false; reason: 'self' | 'not_verified' | 'same_phone' | 'duplicate' | 'no_job_together' };

/**
 * Is this vouch acceptable for `artisan`? The voucher must already be verified, be a different person on a
 * different phone, not have vouched before, and attest a completed job together.
 */
export function checkVouch(artisan: Artisan, voucher: Artisan, workedTogether: boolean, existing: Vouch[]): VouchCheck {
  if (voucher.id === artisan.id) return { ok: false, reason: 'self' };
  if (!isTrusted(voucher)) return { ok: false, reason: 'not_verified' };
  if (voucher.phone === artisan.phone) return { ok: false, reason: 'same_phone' };
  if (existing.some((v) => v.artisanId === artisan.id && (v.voucherId === voucher.id || v.voucherPhone === voucher.phone)))
    return { ok: false, reason: 'duplicate' };
  if (!workedTogether) return { ok: false, reason: 'no_job_together' };
  return { ok: true };
}

/** Distinct, valid vouches for `artisan` (distinct people and phones, verified voucher, worked together). */
export function countValidVouches(artisan: Artisan, vouches: Vouch[], all: Artisan[]): number {
  const byId = new Map(all.map((a) => [a.id, a]));
  const ids = new Set<string>();
  const phones = new Set<string>();
  for (const v of vouches) {
    if (v.artisanId !== artisan.id || !v.workedTogether) continue;
    const voucher = byId.get(v.voucherId);
    if (!voucher || voucher.id === artisan.id || voucher.phone === artisan.phone || !isTrusted(voucher)) continue;
    if (ids.has(voucher.id) || phones.has(voucher.phone)) continue;
    ids.add(voucher.id);
    phones.add(voucher.phone);
  }
  return ids.size;
}

/** Verified = trusted by seed/operator, or at least VOUCHES_REQUIRED valid vouches. Rejected is never verified. */
export function isVerified(a: Artisan, vouches: Vouch[], all: Artisan[]): boolean {
  if (a.rejected) return false;
  if (isTrusted(a)) return true;
  return countValidVouches(a, vouches, all) >= VOUCHES_REQUIRED;
}

// ---------------------------------------------------------------- job code
/** Simple, non-cryptographic hash (salted FNV-1a): keeps the code out of storage in plain text. */
export function hashCode(code: string, salt = 'acbridge'): string {
  let h = 0x811c9dc5;
  for (const ch of `${salt}:${code}`) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

/** Six random digits, leading zeros kept. `rand` is injectable for tests. */
export function generateJobCode(rand: () => number = Math.random): string {
  let out = '';
  for (let i = 0; i < 6; i++) out += Math.floor(rand() * 10).toString();
  return out;
}

export type CompletionCheck =
  | { ok: true }
  | { ok: false; reason: 'bad_format' | 'wrong_code' | 'not_accepted' | 'already_used' };

/** A job completes only if it was accepted, the code is unused, and the entered code matches the stored hash. */
export function checkCompletion(job: Job, entered: string): CompletionCheck {
  if (job.status !== 'ACCEPTED' || !job.codeHash) return { ok: false, reason: 'not_accepted' };
  if (job.codeUsed) return { ok: false, reason: 'already_used' };
  if (!/^\d{6}$/.test(entered)) return { ok: false, reason: 'bad_format' };
  if (hashCode(entered) !== job.codeHash) return { ok: false, reason: 'wrong_code' };
  return { ok: true };
}

// ---------------------------------------------------------------- ratings
export type RatingCheck = { ok: true } | { ok: false; reason: 'not_completed' | 'already_rated' | 'bad_score' };

export function checkRating(job: Job | undefined, score: number, ratings: Rating[]): RatingCheck {
  if (!job || job.status !== 'COMPLETED') return { ok: false, reason: 'not_completed' };
  if (ratings.some((r) => r.jobId === job.id)) return { ok: false, reason: 'already_rated' };
  if (!Number.isInteger(score) || score < 1 || score > 5) return { ok: false, reason: 'bad_score' };
  return { ok: true };
}

// ---------------------------------------------------------------- trust score
/**
 * Average rating weighted by job count (seed history counts `baseJobs` jobs, each new rating counts one),
 * plus 0.2 per valid vouch, capped at 5.0. No history at all => neutral 3.0 prior.
 * Seeded artisans' vouches are already baked into their seed average, so callers pass vouchCount 0 for them.
 */
export function trustScore(a: Artisan, ratings: Rating[], vouchCount: number): number {
  const mine = ratings.filter((r) => r.artisanId === a.id);
  const jobs = a.baseJobs + mine.length;
  const sum = a.baseRating * a.baseJobs + mine.reduce((s, r) => s + r.score, 0);
  const avg = jobs === 0 ? NEUTRAL_RATING : sum / jobs;
  return Math.min(MAX_TRUST, avg + VOUCH_BONUS * vouchCount);
}

export const formatScore = (n: number): string => n.toFixed(1);

export function completedJobs(a: Artisan, jobs: Job[]): number {
  return a.baseJobs + jobs.filter((j) => j.artisanId === a.id && j.status === 'COMPLETED').length;
}

/** Trust score for display: counts valid vouches for non-seed artisans only. */
export function trustFor(a: Artisan, vouches: Vouch[], ratings: Rating[], all: Artisan[]): number {
  return trustScore(a, ratings, a.isSeed ? 0 : countValidVouches(a, vouches, all));
}

// ---------------------------------------------------------------- ranking
export interface Ranked { artisan: Artisan; trust: number; jobs: number }

/** Verified artisans of the requested trade only; trust desc (one decimal), then response time asc, then name; at most MAX_MATCHES. */
export function rankArtisans(
  artisans: Artisan[], vouches: Vouch[], ratings: Rating[], jobs: Job[], trade: string, limit = MAX_MATCHES,
): Ranked[] {
  return artisans
    .filter((a) => sameTrade(a.trade, trade) && isVerified(a, vouches, artisans))
    .map((a) => ({ artisan: a, trust: trustFor(a, vouches, ratings, artisans), jobs: completedJobs(a, jobs) }))
    .sort((x, y) => {
      const t = Math.round(y.trust * 10) - Math.round(x.trust * 10);
      if (t !== 0) return t;
      return x.artisan.avgResponseMin - y.artisan.avgResponseMin || x.artisan.name.localeCompare(y.artisan.name);
    })
    .slice(0, limit);
}

// ---------------------------------------------------------------- phone numbers
/** Same canonical form as the backend (backend/app/schemas.py normalize_phone): +237 6XXXXXXXX. Null if invalid. */
export function normalizePhone(raw: string): string | null {
  let cleaned = raw.replace(/[\s\-().]/g, '');
  if (/^6\d{8}$/.test(cleaned)) cleaned = `+237${cleaned}`;
  else if (/^237\d{9}$/.test(cleaned)) cleaned = `+${cleaned}`;
  return /^\+[1-9]\d{7,14}$/.test(cleaned) ? cleaned : null;
}

// ---------------------------------------------------------------- price display
/** Fair price: always a range, never a single number. */
export const priceRangeLabel = (a: Pick<Artisan, 'priceMin' | 'priceMax'>, currency: string, locale = 'fr-FR'): string =>
  `${a.priceMin.toLocaleString(locale)} – ${a.priceMax.toLocaleString(locale)} ${currency}`;
