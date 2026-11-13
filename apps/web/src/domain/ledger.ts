/**
 * Double-entry ledger, payments and reconciliation (pure). Mirrors backend/app/services/ledger_service.py:
 * every money event is a transaction whose DEBIT lines equal its CREDIT lines, in whole FCFA.
 *
 *   customer payment succeeds   DEBIT collection P | CREDIT platform_revenue C | CREDIT artisan_pending P - C
 *   payout paid to the artisan  DEBIT artisan_pending S | CREDIT artisan_paid S
 *
 * SANDBOX: no real money moves. The "provider" side of the reconciliation is derived from the payment/payout records.
 */
import type { Job, LedgerLine, PaymentRec, Payout } from './types';
import { computeCommission } from './money';

export type Account = 'collection' | 'platform_revenue' | 'artisan_pending' | 'artisan_paid' | 'refund_payable';
export const ACCOUNTS: Account[] = ['collection', 'platform_revenue', 'artisan_pending', 'artisan_paid', 'refund_payable'];
export type Line = [Account, 'DEBIT' | 'CREDIT', number];

/** Posts one balanced transaction. Idempotent: a txKey that already exists is skipped, so a replay never double-credits. */
export function postTx(ledger: LedgerLine[], txKey: string, lines: Line[], at: string): LedgerLine[] {
  const debit = lines.filter((l) => l[1] === 'DEBIT').reduce((s, l) => s + l[2], 0);
  const credit = lines.filter((l) => l[1] === 'CREDIT').reduce((s, l) => s + l[2], 0);
  if (lines.some((l) => !Number.isInteger(l[2]) || l[2] <= 0)) throw new RangeError('ledger amounts are positive whole FCFA');
  if (debit !== credit) throw new RangeError(`unbalanced transaction ${txKey}: debits ${debit} != credits ${credit}`);
  if (ledger.some((e) => e.txKey === txKey)) return ledger;
  return [...ledger, ...lines.map(([account, direction, amount], i) => ({ id: `${txKey}#${i}`, txKey, account, direction, amount, at }))];
}

export function balances(ledger: LedgerLine[]): Record<Account, number> {
  const out = Object.fromEntries(ACCOUNTS.map((a) => [a, 0])) as Record<Account, number>;
  for (const e of ledger) {
    const sign = e.account === 'collection' ? (e.direction === 'DEBIT' ? 1 : -1) : e.direction === 'CREDIT' ? 1 : -1;
    out[e.account] += sign * e.amount;
  }
  return out;
}

/** txKeys whose debits and credits differ. Must always be empty. */
export function unbalancedTransactions(ledger: LedgerLine[]): string[] {
  const sums = new Map<string, number>();
  for (const e of ledger) sums.set(e.txKey, (sums.get(e.txKey) ?? 0) + (e.direction === 'DEBIT' ? e.amount : -e.amount));
  return [...sums].filter(([, v]) => v !== 0).map(([k]) => k);
}

export function paymentSucceededLines(price: number): { lines: Line[]; commission: number; payout: number } {
  const tx = computeCommission(price);
  return {
    commission: tx.commission, payout: tx.payout,
    lines: [['collection', 'DEBIT', tx.price], ['platform_revenue', 'CREDIT', tx.commission], ['artisan_pending', 'CREDIT', tx.payout]],
  };
}

export const payoutPaidLines = (amount: number): Line[] => [['artisan_pending', 'DEBIT', amount], ['artisan_paid', 'CREDIT', amount]];

// ------------------------------------------------------------------ paying
export const PAY_METHODS = ['mtn', 'orange'] as const;
export type PayMethod = (typeof PAY_METHODS)[number];
export const SANDBOX_APPROVE_AFTER_MS = 5000; // the sandbox provider approves after 5 seconds
export const POLL_EVERY_MS = 3000;
export const POLL_MAX_MS = 3 * 60 * 1000;
/** Sandbox rule so the failure screen can be demonstrated: this number is always declined. */
export const SANDBOX_DECLINED_PHONE = '+237600000000';

export type PayCheck = { ok: true } | { ok: false; reason: 'no_job' | 'not_accepted' | 'no_price' | 'already_live' | 'bad_method' | 'bad_phone' };

/** Can this customer start a payment for this job now? The amount is never an input: it always comes from the job. */
export function checkPayStart(job: Job | undefined, payments: PaymentRec[], method: string, phone: string | null): PayCheck {
  if (!job) return { ok: false, reason: 'no_job' };
  if (job.status !== 'ACCEPTED') return { ok: false, reason: 'not_accepted' };
  if (!(job.price > 0)) return { ok: false, reason: 'no_price' };
  if (payments.some((p) => p.jobId === job.id && (p.status === 'pending' || p.status === 'succeeded'))) return { ok: false, reason: 'already_live' };
  if (!(PAY_METHODS as readonly string[]).includes(method)) return { ok: false, reason: 'bad_method' };
  if (!phone) return { ok: false, reason: 'bad_phone' };
  return { ok: true };
}

export const isPaid = (job: Job | undefined, payments: PaymentRec[]): boolean =>
  !!job && payments.some((p) => p.jobId === job.id && p.status === 'succeeded');

export { maskPhone } from '@acbridge/core';

// ------------------------------------------------------------------ operator payout actions
export const MIN_REASON = 5;
export type PayoutCheck = { ok: true } | { ok: false; reason: 'no_payout' | 'bad_reason' | 'not_holdable' | 'not_releasable' | 'not_completed' };

export function checkHold(payout: Payout | undefined, reason: string): PayoutCheck {
  if (!payout) return { ok: false, reason: 'no_payout' };
  if (reason.trim().length < MIN_REASON) return { ok: false, reason: 'bad_reason' };
  return payout.status === 'PENDING' ? { ok: true } : { ok: false, reason: 'not_holdable' };
}

export function checkRelease(payout: Payout | undefined, job: Job | undefined, reason: string): PayoutCheck {
  if (!payout) return { ok: false, reason: 'no_payout' };
  if (reason.trim().length < MIN_REASON) return { ok: false, reason: 'bad_reason' };
  if (payout.status !== 'PENDING' && payout.status !== 'HELD') return { ok: false, reason: 'not_releasable' };
  if (!job || job.status !== 'COMPLETED') return { ok: false, reason: 'not_completed' }; // only after the job code was verified
  return { ok: true };
}

// ------------------------------------------------------------------ reconciliation
export interface Reconciliation {
  ledger: Record<Account, number>;
  provider: { collected: number; disbursed: number };
  differences: { collected: number; disbursed: number };
  unbalanced: string[];
  mismatch: boolean;
  unpaidCompleted: { artisanId: string; jobs: number }[];
}

export function reconcile(
  ledger: LedgerLine[], payments: PaymentRec[], payouts: Payout[], jobs: Job[], providerCollectedOverride: number | null = null,
): Reconciliation {
  const bal = balances(ledger);
  const collected = providerCollectedOverride ?? payments.filter((p) => p.status === 'succeeded').reduce((s, p) => s + p.amount, 0);
  const disbursed = payouts.filter((p) => p.status === 'PAID').reduce((s, p) => s + p.amount, 0);
  const differences = { collected: collected - bal.collection, disbursed: disbursed - bal.artisan_paid };
  const unbalanced = unbalancedTransactions(ledger);
  // completed jobs with no successful payment may have been paid outside the app
  const unpaid = new Map<string, number>();
  for (const j of jobs) if (j.status === 'COMPLETED' && !isPaid(j, payments)) unpaid.set(j.artisanId, (unpaid.get(j.artisanId) ?? 0) + 1);
  return {
    ledger: bal, provider: { collected, disbursed }, differences, unbalanced,
    mismatch: differences.collected !== 0 || differences.disbursed !== 0 || unbalanced.length > 0,
    unpaidCompleted: [...unpaid].map(([artisanId, jobsCount]) => ({ artisanId, jobs: jobsCount })),
  };
}
