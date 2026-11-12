import { describe, expect, it } from 'vitest';
import { OFFER_TTL_MS, formatLeft, isOfferExpired, offerDeadline } from '../domain/offers';
import type { Job, ServiceRequest, Urgency } from '../domain/types';
import { initialState, reducer, type State } from '../store/reducer';

const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR;
const t0 = Date.parse('2026-01-01T00:00:00Z');
const iso = (offsetMs: number) => new Date(t0 + offsetMs).toISOString();
const req = (urgency: Urgency): ServiceRequest => ({
  id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency, description: '', at: iso(0),
});
const job = (over: Partial<Job> = {}): Job => ({
  id: 'job', requestId: 'rq', artisanId: 'seed-1', customerPhone: '+237690000030', status: 'REQUESTED', codeHash: null, codeUsed: false,
  price: 5500, priceSource: 'estimate', createdAt: iso(0), ...over,
});

describe('how long an artisan has to accept', () => {
  it('is 1 hour (urgent), 1 day (this week) and 5 days (not urgent)', () => {
    expect(OFFER_TTL_MS).toEqual({ today: HOUR, week: DAY, later: 5 * DAY });
    expect(offerDeadline(job(), req('today'))).toBe(t0 + HOUR);
  });

  it.each([
    ['today', 59 * MIN, 61 * MIN],
    ['week', 23 * HOUR, 25 * HOUR],
    ['later', 4 * DAY, 6 * DAY],
  ] as const)('%s: still open just inside the window, nullified just after it', (urgency, inside, outside) => {
    expect(isOfferExpired(job(), req(urgency), t0 + inside)).toBe(false);
    expect(isOfferExpired(job(), req(urgency), t0 + outside)).toBe(true);
  });

  it('an answered offer never expires', () => {
    for (const status of ['ACCEPTED', 'DECLINED', 'COMPLETED', 'EXPIRED'] as const) {
      expect(isOfferExpired(job({ status }), req('today'), t0 + 30 * DAY)).toBe(false);
    }
  });

  it('formats the time left briefly', () => {
    expect(formatLeft(59 * MIN)).toBe('59 min');
    expect(formatLeft(5 * HOUR + 20 * MIN)).toBe('5 h 20 min');
    expect(formatLeft(2 * DAY + 3 * HOUR)).toBe('2 d 3 h');
  });
});

describe('the reducer nullifies unanswered offers', () => {
  const ids = (n: number) => Array.from({ length: n }, (_, i) => `i${i}${Math.random()}`);
  const start = (urgency: Urgency): State => {
    let s = initialState();
    s = reducer(s, { type: 'request', request: { ...req(urgency), at: iso(0) } });
    return reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'seed-1', price: 5500, at: iso(0), ids: ids(1) });
  };

  it('expires an urgent offer after an hour: job EXPIRED, chat closed, both sides told, audit entry', () => {
    let s = start('today');
    s = reducer(s, { type: 'expire', at: iso(30 * MIN), stamp: 'e1' });
    expect(s.jobs[0].status).toBe('REQUESTED');                         // not yet
    s = reducer(s, { type: 'expire', at: iso(61 * MIN), stamp: 'e2' });
    expect(s.jobs[0].status).toBe('EXPIRED');
    expect(s.sms.some((m) => m.key === 'sms.offerExpired' && m.to === '+237690000030')).toBe(true);
    expect(s.sms.some((m) => m.key === 'sms.offerLost' && m.to === '+237690000015')).toBe(true);
    expect(s.chats.at(-1)).toMatchObject({ key: 'chat.sysExpired' });
    expect(s.audit.at(-1)).toMatchObject({ kind: 'expiry', params: { urgency: 'today' } });
    const before = s;
    s = reducer(s, { type: 'expire', at: iso(2 * HOUR), stamp: 'e3' });  // sweeping again changes nothing
    expect(s).toBe(before);
  });

  it('a late YES does not accept: the offer lapses instead', () => {
    let s = start('today');
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at: iso(2 * HOUR), ids: ids(3) });
    expect(s.jobs[0].status).toBe('EXPIRED');
    expect(s.sms.some((m) => m.key === 'sms.accepted')).toBe(false);
    expect(s.payouts).toEqual([]);
  });

  it('an on-time YES still works, and an accepted job is never expired later', () => {
    let s = start('today');
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at: iso(59 * MIN), ids: ids(3) });
    expect(s.jobs[0].status).toBe('ACCEPTED');
    s = reducer(s, { type: 'expire', at: iso(30 * DAY), stamp: 'late' });
    expect(s.jobs[0].status).toBe('ACCEPTED');
  });

  it('a not-urgent offer survives 4 days and lapses after 5', () => {
    let s = start('later');
    s = reducer(s, { type: 'expire', at: iso(4 * DAY), stamp: 'a' });
    expect(s.jobs[0].status).toBe('REQUESTED');
    s = reducer(s, { type: 'expire', at: iso(5 * DAY + MIN), stamp: 'b' });
    expect(s.jobs[0].status).toBe('EXPIRED');
  });

  it('chat and payments are closed on an expired offer', () => {
    let s = start('today');
    s = reducer(s, { type: 'expire', at: iso(2 * HOUR), stamp: 'x' });
    const chats = s.chats.length;
    s = reducer(s, { type: 'chat', id: 'm', sysId: 'sy', jobId: 'job', from: 'customer', text: 'hello 9000 FCFA', at: iso(2 * HOUR), ids: ids(2) });
    expect(s.chats).toHaveLength(chats);
    s = reducer(s, { type: 'payStart', id: 'p', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'R', at: iso(2 * HOUR), ids: ids(1) });
    expect(s.payments).toHaveLength(0);
  });
});
