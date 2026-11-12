import { describe, expect, it } from 'vitest';
import {
  balances, checkHold, checkPayStart, checkRelease, maskPhone, payoutPaidLines, paymentSucceededLines, postTx, reconcile,
  unbalancedTransactions,
} from '../domain/ledger';
import type { Job, LedgerLine, PaymentRec, Payout } from '../domain/types';
import { initialState, reducer, type State } from '../store/reducer';

const at = '2026-01-01T00:00:00Z';
const ids = (n: number) => Array.from({ length: n }, (_, i) => `i${i}${Math.random()}`);
const job = (over: Partial<Job> = {}): Job => ({
  id: 'job', requestId: 'rq', artisanId: 'seed-1', customerPhone: '+237690000030', status: 'ACCEPTED', codeHash: null, codeUsed: false,
  price: 6000, priceSource: 'chat', createdAt: at, ...over,
});

describe('ledger', () => {
  it('every transaction balances and an unbalanced one is refused', () => {
    expect(() => postTx([], 'x', [['collection', 'DEBIT', 100], ['platform_revenue', 'CREDIT', 90]], at)).toThrow(RangeError);
    expect(() => postTx([], 'x', [['collection', 'DEBIT', 0], ['platform_revenue', 'CREDIT', 0]], at)).toThrow(RangeError);
    const split = paymentSucceededLines(6000);
    expect(split).toMatchObject({ commission: 300, payout: 5700 });
    const ledger = postTx([], 'pay', split.lines, at);
    expect(unbalancedTransactions(ledger)).toEqual([]);
    expect(balances(ledger)).toMatchObject({ collection: 6000, platform_revenue: 300, artisan_pending: 5700, artisan_paid: 0 });
  });

  it('posting the same transaction twice (a replayed callback) does not double-credit', () => {
    const lines = paymentSucceededLines(6000).lines;
    const once = postTx([], 'payment-succeeded:p1', lines, at);
    const twice = postTx(once, 'payment-succeeded:p1', lines, at);
    expect(twice).toEqual(once);
    expect(balances(twice).platform_revenue).toBe(300);
  });

  it('paying the artisan moves the share from pending to paid, still balanced', () => {
    let ledger = postTx([], 'pay', paymentSucceededLines(6000).lines, at);
    ledger = postTx(ledger, 'payout', payoutPaidLines(5700), at);
    expect(balances(ledger)).toMatchObject({ artisan_pending: 0, artisan_paid: 5700, platform_revenue: 300 });
    expect(unbalancedTransactions(ledger)).toEqual([]);
    // a tampered ledger is detected
    const broken: LedgerLine[] = ledger.map((l, i) => (i === 0 ? { ...l, amount: l.amount + 1 } : l));
    expect(unbalancedTransactions(broken)).toEqual(['pay']);
  });
});

describe('starting a payment', () => {
  const none: PaymentRec[] = [];
  it('only an accepted job with a price can be paid, once, with a method and a valid phone', () => {
    expect(checkPayStart(job(), none, 'mtn', '+237670123456')).toEqual({ ok: true });
    expect(checkPayStart(undefined, none, 'mtn', '+237670123456')).toMatchObject({ reason: 'no_job' });
    expect(checkPayStart(job({ status: 'REQUESTED' }), none, 'mtn', '+237670123456')).toMatchObject({ reason: 'not_accepted' });
    expect(checkPayStart(job({ price: 0 }), none, 'mtn', '+237670123456')).toMatchObject({ reason: 'no_price' });
    expect(checkPayStart(job(), none, 'paypal', '+237670123456')).toMatchObject({ reason: 'bad_method' });
    expect(checkPayStart(job(), none, 'mtn', null)).toMatchObject({ reason: 'bad_phone' });
    const pending = [{ id: 'p', jobId: 'job', status: 'pending' } as PaymentRec];
    expect(checkPayStart(job(), pending, 'mtn', '+237670123456')).toMatchObject({ reason: 'already_live' });
    const failed = [{ id: 'p', jobId: 'job', status: 'failed' } as PaymentRec];
    expect(checkPayStart(job(), failed, 'mtn', '+237670123456')).toEqual({ ok: true }); // "Try again" after a failure
  });

  it('the amount always comes from the job, and a second live payment is ignored', () => {
    let s: State = initialState();
    s = reducer(s, { type: 'request', request: { id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: '', at } });
    s = reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'seed-1', price: 6000, at, ids: ids(1) });
    s = reducer(s, { type: 'payStart', id: 'early', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'R', at, ids: ids(1) });
    expect(s.payments).toHaveLength(0); // the artisan has not agreed yet
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at, ids: ids(3) });
    s = reducer(s, { type: 'payStart', id: 'p1', jobId: 'job', method: 'orange', phone: '+237670123456', ref: 'R1', at, ids: ids(1) });
    s = reducer(s, { type: 'payStart', id: 'p2', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'R2', at, ids: ids(1) });
    expect(s.payments).toHaveLength(1);
    expect(s.payments[0].amount).toBe(6000);
    s = reducer(s, { type: 'paySettle', id: 'p1', ok: true, code: '123456', at, ids: ids(4) });
    s = reducer(s, { type: 'paySettle', id: 'p1', ok: true, code: '654321', at, ids: ids(4) }); // replayed callback
    expect(balances(s.ledger).platform_revenue).toBe(300);
    expect(s.payouts).toHaveLength(1);
  });

  it('a declined payment books nothing and can be retried', () => {
    let s: State = initialState();
    s = reducer(s, { type: 'request', request: { id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: '', at } });
    s = reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'seed-1', price: 6000, at, ids: ids(1) });
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at, ids: ids(3) });
    s = reducer(s, { type: 'payStart', id: 'p1', jobId: 'job', method: 'mtn', phone: '+237600000000', ref: 'R1', at, ids: ids(1) });
    s = reducer(s, { type: 'paySettle', id: 'p1', ok: false, code: '123456', at, ids: ids(4) });
    expect(s.payments[0].status).toBe('failed');
    expect(s.ledger).toEqual([]);
    expect(s.jobs[0].codeHash).toBeNull();
    s = reducer(s, { type: 'payStart', id: 'p2', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'R2', at, ids: ids(1) });
    expect(s.payments).toHaveLength(2);
  });
});

describe('payout hold and release by the operator', () => {
  const payout = (status: Payout['status']): Payout => ({ id: 'po', jobId: 'job', artisanId: 'seed-1', paymentId: 'p', amount: 5700, commission: 300, status, createdAt: at });
  it('needs a reason, and release needs a completed job', () => {
    expect(checkHold(payout('PENDING'), 'no')).toMatchObject({ reason: 'bad_reason' });
    expect(checkHold(payout('PENDING'), 'customer reported a problem')).toEqual({ ok: true });
    expect(checkHold(payout('PAID'), 'customer reported a problem')).toMatchObject({ reason: 'not_holdable' });
    expect(checkRelease(payout('HELD'), job({ status: 'ACCEPTED' }), 'problem solved')).toMatchObject({ reason: 'not_completed' });
    expect(checkRelease(payout('HELD'), job({ status: 'COMPLETED' }), 'x')).toMatchObject({ reason: 'bad_reason' });
    expect(checkRelease(payout('HELD'), job({ status: 'COMPLETED' }), 'problem solved')).toEqual({ ok: true });
    expect(checkRelease(payout('PAID'), job({ status: 'COMPLETED' }), 'problem solved')).toMatchObject({ reason: 'not_releasable' });
  });
});

describe('reconciliation', () => {
  it('shows zero difference normally, a Mismatch when the provider total disagrees, and flags unpaid completed jobs', () => {
    const ledger = postTx(postTx([], 'pay', paymentSucceededLines(6000).lines, at), 'out', payoutPaidLines(5700), at);
    const payments = [{ id: 'p', jobId: 'job', amount: 6000, status: 'succeeded' } as PaymentRec];
    const payouts = [payout('PAID')];
    const clean = reconcile(ledger, payments, payouts, [job({ status: 'COMPLETED' })]);
    expect(clean.mismatch).toBe(false);
    expect(clean.differences).toEqual({ collected: 0, disbursed: 0 });
    const bad = reconcile(ledger, payments, payouts, [job({ status: 'COMPLETED' })], 6500);
    expect(bad.mismatch).toBe(true);
    expect(bad.differences.collected).toBe(500);
    const unpaid = reconcile([], [], [], [job({ status: 'COMPLETED' })]);
    expect(unpaid.unpaidCompleted).toEqual([{ artisanId: 'seed-1', jobs: 1 }]);
    function payout(status: Payout['status']): Payout { return { id: 'po', jobId: 'job', artisanId: 'seed-1', paymentId: 'p', amount: 5700, commission: 300, status, createdAt: at }; }
  });
});

describe('privacy', () => {
  it('masks phone numbers like the backend', () => {
    expect(maskPhone('+237670123456')).toBe('+237 6******56');
    expect(maskPhone('123')).toBe('***');
  });
});
