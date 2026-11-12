import { describe, expect, it } from 'vitest';
import { checkChatMessage, endsWithBareNumber, maskContacts, parseAmount } from '../domain/chat';
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
  it('only the customer, only before the artisan says YES, only inside the allowed range', () => {
    expect(checkChatMessage(job(), 'customer', 'ok 9000 FCFA')).toMatchObject({ ok: true, price: 'applied', amount: 9000 });
    expect(checkChatMessage(job(), 'artisan', 'I want 9000 FCFA')).toMatchObject({ ok: true, price: 'not_customer' });
    expect(checkChatMessage(job(), 'customer', '100 FCFA')).toMatchObject({ price: 'out_of_range' });
    expect(checkChatMessage(job(), 'customer', '9 000 000 FCFA')).toMatchObject({ price: 'out_of_range' });
    expect(checkChatMessage(job({ status: 'ACCEPTED' }), 'customer', '3000 FCFA')).toMatchObject({ price: 'locked' });
    expect(checkChatMessage(job(), 'customer', 'ok 9000')).toMatchObject({ price: 'bare_number' });
    expect(checkChatMessage(job(), 'customer', 'hello')).toMatchObject({ price: 'none' });
  });
  it('refuses empty, over-long and closed-chat messages', () => {
    expect(checkChatMessage(job(), 'customer', '   ')).toEqual({ ok: false, reason: 'empty' });
    expect(checkChatMessage(job(), 'customer', 'x'.repeat(501))).toEqual({ ok: false, reason: 'too_long' });
    expect(checkChatMessage(job({ status: 'COMPLETED' }), 'customer', 'hi')).toEqual({ ok: false, reason: 'closed' });
    expect(checkChatMessage(job({ status: 'DECLINED' }), 'customer', 'hi')).toEqual({ ok: false, reason: 'closed' });
    expect(checkChatMessage(undefined, 'customer', 'hi')).toEqual({ ok: false, reason: 'closed' });
  });
});

describe('the reducer turns the customer amount into the price and the commission', () => {
  const at = '2026-01-01T00:00:00Z';
  const ids = (n: number) => Array.from({ length: n }, (_, i) => `i${i}${Math.random()}`);
  const start = (): State => {
    let s = initialState();
    s = reducer(s, { type: 'request', request: { id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: '', at } });
    return reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'seed-1', price: 5500, at, ids: ids(1) });
  };

  it('bargains, fixes 9 000 FCFA, shows 5% = 450, notifies the artisan, then locks on YES', () => {
    let s = start();
    s = reducer(s, { type: 'chat', id: 'm1', sysId: 's1', jobId: 'job', from: 'customer', text: 'Can you do it for less?', at, ids: ids(2) });
    s = reducer(s, { type: 'chat', id: 'm2', sysId: 's2', jobId: 'job', from: 'artisan', text: 'Not below 12 000 FCFA, call 670123456', at, ids: ids(2) });
    expect(s.jobs[0]).toMatchObject({ price: 5500, priceSource: 'estimate' }); // an artisan amount is only talk
    expect(s.chats[1].text).toContain('[number hidden]');

    s = reducer(s, { type: 'chat', id: 'm3', sysId: 's3', jobId: 'job', from: 'customer', text: 'Final offer: 9 000 FCFA', at, ids: ids(2) });
    expect(s.jobs[0]).toMatchObject({ price: 9000, priceSource: 'chat' });
    expect(s.chats.at(-2)).toMatchObject({ from: 'customer', price: 9000 });
    expect(s.chats.at(-1)).toMatchObject({ from: 'system', key: 'chat.sysPrice', params: { price: 9000, rate: 5, commission: 450, payout: 8550 } });
    expect(s.sms.at(-1)).toMatchObject({ to: '+237690000015', key: 'sms.priceProposed', params: { price: 9000, commission: 450 } });
    expect(s.audit.at(-1)).toMatchObject({ kind: 'price', params: { price: 9000, commission: 450 } });

    const code = generateJobCode();
    s = reducer(s, { type: 'answer', jobId: 'job', accept: true, code, at, ids: ids(3) });
    expect(s.chats.at(-1)).toMatchObject({ key: 'chat.sysAccepted', params: { price: 9000 } });
    // locked: a later amount changes nothing
    s = reducer(s, { type: 'chat', id: 'm4', sysId: 's4', jobId: 'job', from: 'customer', text: '3000 FCFA', at, ids: ids(2) });
    expect(s.jobs[0].price).toBe(9000);
    // the commission is taken from the AGREED price when the job completes
    s = reducer(s, { type: 'complete', jobId: 'job', entered: code, at, ids: ids(4) });
    expect(s.jobs[0]).toMatchObject({ commission: 450, payout: 8550 });
  });

  it('ignores a message on a job that is closed', () => {
    let s = start();
    s = reducer(s, { type: 'answer', jobId: 'job', accept: false, code: '000000', at, ids: ids(3) });
    const before = s.chats.length;
    s = reducer(s, { type: 'chat', id: 'm', sysId: 's', jobId: 'job', from: 'customer', text: 'hello', at, ids: ids(2) });
    expect(s.chats).toHaveLength(before);
  });
});
