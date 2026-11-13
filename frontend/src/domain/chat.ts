/**
 * "Connect flexibly": the CUSTOMER bargains and the ARTISAN states the final price. When the ARTISAN ends a message
 * with an amount and a currency (e.g. "final price: 9000 FCFA"), that amount becomes the job price and the commission is
 * computed from it. An amount typed by the customer is just an offer in the conversation and never changes the price. Pure rules, kept identical to backend/app/services/chat_service.py (same regexes and limits).
 */
import type { Job } from './types';

export const MAX_BODY = 500;
export const MIN_PRICE = 500;
export const MAX_PRICE = 5_000_000;

// Amount at the very end of the text, currency last. Thousands may be separated by space, dot, comma or NBSP.
const AMOUNT_AT_END = /(?<![\d.,])(\d{1,3}(?:[ .,  ]\d{3})+|\d+)\s*(?:F\s?CFA|XAF|CFA)\s*[.!]*\s*$/i;
const ENDS_WITH_NUMBER = /\d\s*[.!]*\s*$/;
// Contiguous 9+ digit runs and international +CC numbers. Prices (max 7 digits) are never touched.
const PHONE = /\+\d{1,3}[ .-]?\d(?:[ .-]?\d){7,}|\d{9,}/g;
export const HIDDEN = '[number hidden]';

/** The amount at the end of `text` when it is followed by FCFA / F CFA / XAF / CFA, otherwise null. */
export function parseAmount(text: string): number | null {
  const m = AMOUNT_AT_END.exec(text.trim());
  return m ? Number(m[1].replace(/[ .,  ]/g, '')) : null;
}

/** "ok 9000" (a number but no currency): the UI reminds the user to add the currency. */
export const endsWithBareNumber = (text: string): boolean => parseAmount(text) === null && ENDS_WITH_NUMBER.test(text.trim());

/** Hides phone numbers so the deal stays on the platform. */
export const maskContacts = (text: string): string => text.replace(PHONE, HIDDEN);

export type ChatSender = 'customer' | 'artisan';
export type PriceStatus = 'none' | 'bare_number' | 'applied' | 'out_of_range' | 'locked' | 'not_artisan';
export type ChatCheck = { ok: true; amount: number | null; price: PriceStatus } | { ok: false; reason: 'empty' | 'too_long' | 'closed' };

/** A job is PAID once the customer's payment succeeded (that is when its job code is created): the app holds the money. */
export const isJobPaid = (job: Job): boolean => job.codeHash !== null;

/** The chat is open while the offer is live and until the customer's payment succeeds. After that no message can be sent. */
export const isChatOpen = (job: Job): boolean => (job.status === 'REQUESTED' || job.status === 'ACCEPTED') && !isJobPaid(job);

/** What would happen if `from` sent `text` on `job`. Used by the store before dispatching and by the reducer to re-validate. */
export function checkChatMessage(job: Job | undefined, from: ChatSender, text: string): ChatCheck {
  const t = text.trim();
  if (!t) return { ok: false, reason: 'empty' };
  if (t.length > MAX_BODY) return { ok: false, reason: 'too_long' };
  if (!job || !isChatOpen(job)) return { ok: false, reason: 'closed' };
  const amount = parseAmount(t);
  if (amount === null) return { ok: true, amount, price: endsWithBareNumber(t) && from === 'artisan' ? 'bare_number' : 'none' };
  if (from !== 'artisan') return { ok: true, amount, price: 'not_artisan' }; // the customer bargains, the artisan fixes the price
  if (amount < MIN_PRICE || amount > MAX_PRICE) return { ok: true, amount, price: 'out_of_range' };
  // The price is frozen once the artisan has said YES (the cooling-off/commitment rules start from there).
  if (job.status !== 'REQUESTED') return { ok: true, amount, price: 'locked' };
  return { ok: true, amount, price: 'applied' };
}
