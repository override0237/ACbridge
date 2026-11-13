import { describe, expect, it } from 'vitest';
import { checkChatMessage, endsWithBareNumber, isChatOpen, maskContacts, parseAmount } from '../domain/chat';
import type { Job } from '../domain/types';
import { generateJobCode } from '../domain/rules';
import { initialState, reducer, type State } from '../store/reducer';

describe('reading the price from the chat (same cases as the backend tests)', () => {
  it.each([
    ['9000 FCFA', 9000], ['9000FCFA', 9000], ['ok, deal at 9 000 FCFA', 9000], ['9.000 fcfa', 9000],
    ['9,000 F CFA', 9000], ['9 000 XAF', 9000], ['1 250 000 CFA', 1_250_000], ['final price 12000 FCFA.', 12000],
    ['12000 FCFA!!', 12000],
  ])('%s -> %i', (text, expected) => expect(parseAmount(text)).toBe(expected));

  it.each(['9000', 'FCFA 9000', '9000 FCFA is too much, sorry', '9.5 FCFA', 'hello', ''])(
    'no price in %j (currency missing or not last)', (text) => expect(parseAmount(text)).toBeNull());

  it('spots a bare number so the user is reminded to add the currency', () => {
    expect(endsWithBareNumber('ok 9000')).toBe(true);
    expect(endsWithBareNumber('ok 9000 FCFA')).toBe(false);
    expect(endsWithBareNumber('hello')).toBe(false);
  });

  it('hides phone numbers but never prices', () => {
    expect(maskContacts('call me 670123456 ok')).toBe('call me [number hidden] ok');
    expect(maskContacts('whatsapp +237 670 123 456 please')).toBe('whatsapp [number hidden] please');
    expect(maskContacts('my price is 1 250 000 FCFA')).toBe('my price is 1 250 000 FCFA');
  });
});

const job = (over: Partial<Job> = {}): Job => ({
  id: 'job', requestId: 'rq', artisanId: 'seed-1', customerPhone: '+237690000030', status: 'REQUESTED', codeHash: null,
  codeUsed: false, price: 5500, priceSource: 'estimate', createdAt: '', ...over,
});

describe('who can fix the price, and when', () => {
  it('only the ARTISAN, only before the artisan says YES, only inside the allowed range', () => {
    expect(checkChatMessage(job(), 'artisan', 'final price: 9000 FCFA')).toMatchObject({ ok: true, price: 'applied', amount: 9000 });
    expect(checkChatMessage(job(), 'customer', 'I offer 3000 FCFA')).toMatchObject({ ok: true, price: 'not_artisan', amount: 3000 });
    expect(checkChatMessage(job(), 'artisan', '100 FCFA')).toMatchObject({ price: 'out_of_range' });
    expect(checkChatMessage(job(), 'artisan', '9 000 000 FCFA')).toMatchObject({ price: 'out_of_range' });
    expect(checkChatMessage(job({ status: 'ACCEPTED' }), 'artisan', '3000 FCFA')).toMatchObject({ price: 'locked' });
    expect(checkChatMessage(job(), 'artisan', 'ok 9000')).toMatchObject({ price: 'bare_number' });
    expect(checkChatMessage(job(), 'customer', 'ok 9000')).toMatchObject({ price: 'none' });   // a customer's bare number is just talk
    expect(checkChatMessage(job(), 'artisan', 'hello')).toMatchObject({ price: 'none' });
  });
  it('refuses empty, over-long and closed-chat messages', () => {
    expect(checkChatMessage(job(), 'customer', '   ')).toEqual({ ok: false, reason: 'empty' });
    expect(checkChatMessage(job(), 'customer', 'x'.repeat(501))).toEqual({ ok: false, reason: 'too_long' });
    expect(checkChatMessage(job({ status: 'COMPLETED' }), 'customer', 'hi')).toEqual({ ok: false, reason: 'closed' });
    expect(checkChatMessage(job({ status: 'DECLINED' }), 'customer', 'hi')).toEqual({ ok: false, reason: 'closed' });
    expect(checkChatMessage(undefined, 'customer', 'hi')).toEqual({ ok: false, reason: 'closed' });
  });
});

describe('the reducer turns the ARTISAN amount into the price and the commission', () => {
  const at = '2026-01-01T00:00:00Z';
  const ids = (n: number) => Array.from({ length: n }, (_, i) => `i${i}${Math.random()}`);
  const start = (): State => {
    let s = initialState();
    s = reducer(s, { type: 'request', request: { id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: '', at } });
    return reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'seed-1', price: 5500, at, ids: ids(1) });
  };

  it('the customer bargains, the artisan states 9 000 FCFA (5% = 450), the customer is told, YES locks it', () => {
    let s = start();
    s = reducer(s, { type: 'chat', id: 'm1', sysId: 's1', jobId: 'job', from: 'customer', text: 'Could you do it for 3 000 FCFA?', at, ids: ids(2) });
    expect(s.jobs[0]).toMatchObject({ price: 5500, priceSource: 'estimate' });       // the customer's amount is only an offer
    expect(s.chats[0].price).toBeUndefined();
    s = reducer(s, { type: 'chat', id: 'm2', sysId: 's2', jobId: 'job', from: 'artisan', text: 'Call me on 670123456. My price is 12 000 FCFA', at, ids: ids(2) });
    expect(s.jobs[0]).toMatchObject({ price: 12000, priceSource: 'chat' });          // the artisan's amount IS the price
    expect(s.chats.find((m) => m.id === 'm2')?.text).toContain('[number hidden]');

    s = reducer(s, { type: 'chat', id: 'm3', sysId: 's3', jobId: 'job', from: 'customer', text: 'Final offer: 8 000 FCFA', at, ids: ids(2) });
    expect(s.jobs[0].price).toBe(12000);                                             // the customer still cannot change it
    s = reducer(s, { type: 'chat', id: 'm4', sysId: 's4', jobId: 'job', from: 'artisan', text: 'OK, my final price is 9 000 FCFA', at, ids: ids(2) });
    expect(s.jobs[0]).toMatchObject({ price: 9000, priceSource: 'chat' });
    expect(s.chats.at(-2)).toMatchObject({ from: 'artisan', price: 9000 });
    expect(s.chats.at(-1)).toMatchObject({ from: 'system', key: 'chat.sysPrice', params: { price: 9000, rate: 5, commission: 450, payout: 8550 } });
    expect(s.sms.at(-1)).toMatchObject({ to: '+237690000030', key: 'sms.priceProposed', params: { artisan: 'Grace', price: 9000 } });  // the CUSTOMER is told
    expect(s.audit.at(-1)).toMatchObject({ kind: 'price', params: { price: 9000, commission: 450 } });

    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at, ids: ids(3) });
    expect(s.chats.at(-1)).toMatchObject({ key: 'chat.sysAccepted', params: { price: 9000 } });
    s = reducer(s, { type: 'chat', id: 'm5', sysId: 's5', jobId: 'job', from: 'artisan', text: '20 000 FCFA', at, ids: ids(2) });
    expect(s.jobs[0].price).toBe(9000);                                              // locked after YES, even for the artisan
    // the customer pays the AGREED price: the commission is cut from it at that moment
    const code = generateJobCode();
    s = reducer(s, { type: 'payStart', id: 'p1', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'R', at, ids: ids(1) });
    s = reducer(s, { type: 'paySettle', id: 'p1', ok: true, code, at, ids: ids(4) });
    expect(s.jobs[0]).toMatchObject({ commission: 450, payout: 8550 });
    expect(s.payouts[0]).toMatchObject({ amount: 8550, commission: 450 });
  });

  it('closes the chat for good once the customer payment succeeds', () => {
    let s = start();
    s = reducer(s, { type: 'chat', id: 'm1', sysId: 's1', jobId: 'job', from: 'artisan', text: 'final price 9 000 FCFA', at, ids: ids(2) });
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at, ids: ids(3) });
    expect(isChatOpen(s.jobs[0])).toBe(true);                                   // accepted but not paid: still open
    s = reducer(s, { type: 'payStart', id: 'p1', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'R', at, ids: ids(1) });
    expect(isChatOpen(s.jobs[0])).toBe(true);                                   // payment pending: the money is not held yet
    s = reducer(s, { type: 'paySettle', id: 'p1', ok: true, code: '123456', at, ids: ids(4) });
    expect(isChatOpen(s.jobs[0])).toBe(false);                                  // payment succeeded: closed
    expect(s.chats.at(-1)).toMatchObject({ from: 'system', key: 'chat.sysClosed' });
    const before = s.chats.length;
    for (const from of ['customer', 'artisan'] as const) {
      s = reducer(s, { type: 'chat', id: 'x' + from, sysId: 'y' + from, jobId: 'job', from, text: 'one more thing', at, ids: ids(2) });
    }
    expect(s.chats).toHaveLength(before);                                       // nothing could be sent
    expect(checkChatMessage(s.jobs[0], 'customer', 'hello')).toEqual({ ok: false, reason: 'closed' });
  });

  it('a failed payment does not close the chat', () => {
    let s = start();
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at, ids: ids(3) });
    s = reducer(s, { type: 'payStart', id: 'p1', jobId: 'job', method: 'mtn', phone: '+237600000000', ref: 'R', at, ids: ids(1) });
    s = reducer(s, { type: 'paySettle', id: 'p1', ok: false, code: '123456', at, ids: ids(4) });
    expect(isChatOpen(s.jobs[0])).toBe(true);
  });

  it('ignores a message on a job that is closed', () => {
    let s = start();
    s = reducer(s, { type: 'answer', jobId: 'job', accept: false, at, ids: ids(3) });
    const before = s.chats.length;
    s = reducer(s, { type: 'chat', id: 'm', sysId: 's', jobId: 'job', from: 'artisan', text: 'hello 9000 FCFA', at, ids: ids(2) });
    expect(s.chats).toHaveLength(before);
  });
});
