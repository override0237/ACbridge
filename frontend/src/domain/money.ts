/**
 * Commission maths (pure). The platform keeps a percentage of each completed job, taken from the artisan's side only.
 * The rate itself lives in config.ts and is forced to stay between 3% and 7% inclusive.
 */
import { COMMISSION_RATE, MAX_COMMISSION_RATE, MIN_COMMISSION_RATE } from '../config';

export interface Transaction {
  price: number;
  rate: number;
  /** Rate as a percentage with at most one decimal, e.g. 5 or 4.5. */
  ratePercent: number;
  commission: number;
  payout: number;
}

const EPS = 1e-9;

/** Whole FCFA only (no cents): the commission is rounded to the nearest franc and payout = price - commission. */
export function computeCommission(price: number, rate: number = COMMISSION_RATE): Transaction {
  if (!(rate >= MIN_COMMISSION_RATE - EPS && rate <= MAX_COMMISSION_RATE + EPS)) {
    throw new RangeError(`Commission rate must be between ${MIN_COMMISSION_RATE * 100}% and ${MAX_COMMISSION_RATE * 100}%`);
  }
  if (!Number.isFinite(price) || price < 0) throw new RangeError('Price must be a positive amount');
  const commission = Math.round(price * rate);
  return { price, rate, ratePercent: Math.round(rate * 1000) / 10, commission, payout: price - commission };
}

/** Simulated agreed price for a job: the middle of the artisan's usual range, rounded to 100 FCFA. */
export const agreedPrice = (a: { priceMin: number; priceMax: number }): number =>
  Math.round((a.priceMin + a.priceMax) / 2 / 100) * 100;

/** What the artisan would keep at both ends of their range after the commission. */
export function netRange(a: { priceMin: number; priceMax: number }, rate: number = COMMISSION_RATE): { min: number; max: number } {
  return { min: computeCommission(a.priceMin, rate).payout, max: computeCommission(a.priceMax, rate).payout };
}
