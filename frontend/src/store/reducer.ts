import type {
  Artisan, AuditEntry, AuditKind, ChatMessage, Job, Lang, LedgerLine, PaymentRec, Payout, Rating, ServiceRequest, SmsMessage, Urgency, Vouch,
} from '../domain/types';
import { SEED_ARTISANS, SEED_CUSTOMER } from '../data/seed';
import { checkChatMessage, maskContacts, type ChatSender } from '../domain/chat';
import { checkHold, checkPayStart, checkRelease, paymentSucceededLines, payoutPaidLines, postTx, type PayMethod } from '../domain/ledger';
import { computeCommission } from '../domain/money';
import { isOfferExpired } from '../domain/offers';
import {
  checkCompletion, checkRating, checkVouch, formatScore, hashCode, isVerified, trustFor,
} from '../domain/rules';
import { lastHash, sealVouch } from '../domain/security';

export type Screen =
  | 'home' | 'artisanEntry' | 'artisanLogin' | 'artisanSignup' | 'artisanStatus' | 'artisanInbox' | 'artisanComplete'
  | 'customerRequest' | 'matches' | 'tracking' | 'chat' | 'payments' | 'rate' | 'operator' | 'profile';

export interface UiState {
  screen: Screen;
  actingArtisanId: string | null;
  requestId: string | null;
  jobId: string | null;
  profileId: string | null;
  back: Screen;
  /** Where to go after a successful artisan login. */
  loginNext?: Screen | null;
  /** Who is writing in the chat screen: the customer or the job's artisan. */
  chatAs?: ChatSender;
}

export interface State {
  v: 1;
  lang: Lang;
  artisans: Artisan[];
  vouches: Vouch[];
  requests: ServiceRequest[];
  jobs: Job[];
  chats: ChatMessage[];
  payments: PaymentRec[];
  payouts: Payout[];
  ledger: LedgerLine[];
  ratings: Rating[];
  sms: SmsMessage[];
  audit: AuditEntry[];
  ui: UiState;
}

export const initialState = (): State => ({
  v: 1,
  lang: 'fr',
  artisans: SEED_ARTISANS.map((a) => ({ ...a })),
  vouches: [],
  requests: [],
  jobs: [],
  chats: [],
  payments: [],
  payouts: [],
  ledger: [],
  ratings: [],
  sms: [],
  audit: [],
  ui: { screen: 'home', actingArtisanId: null, requestId: null, jobId: null, profileId: null, back: 'home' },
});

export type Action =
  | { type: 'setLang'; lang: Lang }
  | { type: 'nav'; screen: Screen; patch?: Partial<UiState> }
  | { type: 'register'; artisan: Artisan; at: string; ids: string[] }
  | { type: 'login'; artisanId: string; next: Screen }
  | { type: 'logout' }
  | { type: 'vouchBlocked'; artisanId: string; voucherId: string; at: string; id: string }
  | { type: 'vouch'; artisanId: string; voucherId: string; workedTogether: boolean; vouchId: string; at: string; ids: string[] }
  | { type: 'request'; request: ServiceRequest }
  | { type: 'choose'; jobId: string; requestId: string; artisanId: string; price: number; at: string; ids: string[] }
  | { type: 'expire'; at: string; stamp: string }
  | { type: 'answer'; jobId: string; accept: boolean; at: string; ids: string[] }
  | { type: 'payStart'; id: string; jobId: string; method: PayMethod; phone: string | null; ref: string; at: string; ids: string[] }
  | { type: 'paySettle'; id: string; ok: boolean; code: string; at: string; ids: string[] }
  | { type: 'payoutHold'; payoutId: string; reason: string; at: string; id: string }
  | { type: 'payoutRelease'; payoutId: string; reason: string; at: string; ids: string[] }
  | { type: 'chat'; id: string; sysId: string; jobId: string; from: ChatSender; text: string; at: string; ids: string[] }
  | { type: 'complete'; jobId: string; entered: string; at: string; ids: string[] }
  | { type: 'rate'; ratingId: string; jobId: string; score: number; comment: string; at: string; ids: string[] }
  | { type: 'operator'; artisanId: string; approve: boolean; at: string; ids: string[] }
  | { type: 'patchArtisan'; id: string; patch: Partial<Artisan> }
  | { type: 'patchRequest'; id: string; patch: Partial<ServiceRequest> }
  | { type: 'patchJob'; id: string; patch: Partial<Job> }
  | { type: 'reset'; lang: Lang };

const sms = (id: string, to: string, key: string, params: SmsMessage['params'], at: string): SmsMessage => ({ id, to, key, params, at });
const audit = (id: string, kind: AuditKind, params: AuditEntry['params'], at: string): AuditEntry => ({ id, kind, params, at });
const byId = <T extends { id: string }>(list: T[], id: string): T | undefined => list.find((x) => x.id === id);

/**
 * Nullifies every offer that is still unanswered after its deadline (1 hour urgent, 1 day this week, 5 days not urgent):
 * the job becomes EXPIRED, the chat closes, the customer is told to choose another artisan, the artisan is told it lapsed.
 */
export function expireStale(s: State, at: string, stamp: string): State {
  const nowMs = new Date(at).getTime();
  const overdue = s.jobs.filter((j) => isOfferExpired(j, byId(s.requests, j.requestId), nowMs));
  if (overdue.length === 0) return s;
  const ids = new Set(overdue.map((j) => j.id));
  const sms_: SmsMessage[] = [];
  const chats_: ChatMessage[] = [];
  const audit_: AuditEntry[] = [];
  for (const j of overdue) {
    const artisan = byId(s.artisans, j.artisanId);
    const req = byId(s.requests, j.requestId);
    const name = artisan?.name ?? '';
    sms_.push(sms(`${stamp}-${j.id}-c`, j.customerPhone, 'sms.offerExpired', { artisan: name }, at));
    if (artisan) sms_.push(sms(`${stamp}-${j.id}-a`, artisan.phone, 'sms.offerLost', { customer: req?.customerName ?? '' }, at));
    chats_.push({ id: `${stamp}-${j.id}-m`, jobId: j.id, from: 'system', text: '', key: 'chat.sysExpired', params: { artisan: name }, at });
    audit_.push(audit(`${stamp}-${j.id}-x`, 'expiry', { artisan: name, urgency: req?.urgency ?? 'later' }, at));
  }
  return {
    ...s,
    jobs: s.jobs.map((j) => (ids.has(j.id) ? { ...j, status: 'EXPIRED' as const } : j)),
    sms: [...s.sms, ...sms_], chats: [...s.chats, ...chats_], audit: [...s.audit, ...audit_],
  };
}

export function reducer(s: State, a: Action): State {
  switch (a.type) {
    case 'setLang':
      return { ...s, lang: a.lang };

    case 'nav':
      return { ...s, ui: { ...s.ui, ...a.patch, screen: a.screen } };

    case 'login':
      return { ...s, ui: { ...s.ui, actingArtisanId: a.artisanId, screen: a.next, loginNext: null } };

    case 'logout':
      return { ...s, ui: { ...s.ui, actingArtisanId: null, loginNext: null, screen: 'home' } };

    case 'vouchBlocked': {
      const artisan = byId(s.artisans, a.artisanId);
      const voucher = byId(s.artisans, a.voucherId);
      if (!artisan || !voucher) return s;
      return { ...s, audit: [...s.audit, audit(a.id, 'security', { event: 'vouch_blocked', voucher: voucher.name, name: artisan.name }, a.at)] };
    }

    case 'register': {
      const art = a.artisan;
      const voucherSms = ['seed-1', 'seed-2'].map((vid, i) => {
        const v = byId(s.artisans, vid);
        return v ? sms(a.ids[i], v.phone, 'sms.vouchRequest', { name: art.name, phone: art.phone, trade: art.trade }, a.at) : null;
      }).filter((m): m is SmsMessage => m !== null);
      return {
        ...s,
        artisans: [...s.artisans, art],
        sms: [...s.sms, ...voucherSms, sms(a.ids[2], art.phone, 'sms.welcome', {}, a.at)],
        audit: [...s.audit, audit(a.ids[3], 'verification', { event: 'registered', name: art.name }, a.at)],
        ui: { ...s.ui, actingArtisanId: art.id, screen: 'artisanStatus' },
      };
    }

    case 'vouch': {
      const artisan = byId(s.artisans, a.artisanId);
      const voucher = byId(s.artisans, a.voucherId);
      if (!artisan || !voucher) return s;
      if (!checkVouch(artisan, voucher, a.workedTogether, s.vouches, s.artisans).ok) return s;
      const vouch: Vouch = {
        id: a.vouchId, artisanId: artisan.id, voucherId: voucher.id, voucherPhone: voucher.phone,
        workedTogether: a.workedTogether, at: a.at,
        ...sealVouch(lastHash(s.vouches), artisan.id, voucher.id, a.at), // permanent seal, chained to the previous vouch
      };
      const vouches = [...s.vouches, vouch];
      const was = isVerified(artisan, s.vouches, s.artisans);
      const now = isVerified(artisan, vouches, s.artisans);
      const out: SmsMessage[] = [
        sms(a.ids[0], artisan.phone, 'sms.vouchRecorded', { voucher: voucher.name, seal: vouch.seal }, a.at),
        sms(a.ids[4], voucher.phone, 'sms.vouchSealed', { name: artisan.name, seal: vouch.seal }, a.at),
      ];
      const log: AuditEntry[] = [audit(a.ids[1], 'verification', { event: 'vouch', name: artisan.name, voucher: voucher.name, seal: vouch.seal }, a.at)];
      if (now && !was) {
        out.push(sms(a.ids[2], artisan.phone, 'sms.verified', {}, a.at));
        log.push(audit(a.ids[3], 'verification', { event: 'verified', name: artisan.name }, a.at));
      }
      return { ...s, vouches, sms: [...s.sms, ...out], audit: [...s.audit, ...log] };
    }

    case 'request':
      return { ...s, requests: [...s.requests, a.request], ui: { ...s.ui, requestId: a.request.id, screen: 'matches' } };

    case 'choose': {
      const artisan = byId(s.artisans, a.artisanId);
      const req = byId(s.requests, a.requestId);
      if (!artisan || !req) return s;
      const job: Job = {
        id: a.jobId, requestId: req.id, artisanId: artisan.id, customerPhone: req.customerPhone,
        status: 'REQUESTED', codeHash: null, codeUsed: false, price: a.price, priceSource: 'estimate', createdAt: a.at,
      };
      return {
        ...s,
        jobs: [...s.jobs, job],
        sms: [...s.sms, sms(a.ids[0], artisan.phone, 'sms.jobRequest', { customer: req.customerName, urgency: req.urgency, trade: req.trade }, a.at)],
        ui: { ...s.ui, jobId: job.id, screen: 'tracking' },
      };
    }

    case 'expire':
      return expireStale(s, a.at, a.stamp);

    case 'answer': {
      s = expireStale(s, a.at, a.ids[0]); // too late? then the offer lapses instead of being answered
      const job = byId(s.jobs, a.jobId);
      const artisan = job && byId(s.artisans, job.artisanId);
      if (!job || !artisan || job.status !== 'REQUESTED') return s;
      if (!a.accept) {
        return {
          ...s,
          jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, status: 'DECLINED' } : j)),
          chats: [...s.chats, { id: a.ids[1], jobId: job.id, from: 'system', text: '', key: 'chat.sysDeclined', params: { artisan: artisan.name }, at: a.at }],
          sms: [...s.sms, sms(a.ids[0], job.customerPhone, 'sms.jobDeclined', { artisan: artisan.name }, a.at)],
        };
      }
      return {
        ...s,
        // The price is now agreed and frozen. The job code is only created (and sent to the customer) once the payment succeeds.
        jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, status: 'ACCEPTED', acceptedAt: a.at } : j)),
        chats: [...s.chats, { id: a.ids[2], jobId: job.id, from: 'system', text: '', key: 'chat.sysAccepted', params: { price: job.price, artisan: artisan.name }, at: a.at }],
        sms: [...s.sms, sms(a.ids[0], job.customerPhone, 'sms.accepted', { artisan: artisan.name, price: job.price }, a.at)],
        audit: [...s.audit, audit(a.ids[1], 'job_accepted', { artisan: artisan.name }, a.at)],
      };
    }

    case 'chat': {
      const job = byId(s.jobs, a.jobId);
      const check = checkChatMessage(job, a.from, a.text); // re-validated here: the UI is not trusted
      if (!job || !check.ok) return s;
      const message: ChatMessage = {
        id: a.id, jobId: job.id, from: a.from, text: maskContacts(a.text.trim()), at: a.at,
        ...(check.price === 'applied' ? { price: check.amount ?? undefined } : {}),
      };
      if (check.price !== 'applied' || check.amount === null) return { ...s, chats: [...s.chats, message] };
      // The ARTISAN's amount (with its currency at the end) is the final price from now on; the commission follows from it.
      const tx = computeCommission(check.amount);
      const artisan = byId(s.artisans, job.artisanId);
      const req = byId(s.requests, job.requestId);
      const system: ChatMessage = {
        id: a.sysId, jobId: job.id, from: 'system', text: '', key: 'chat.sysPrice', at: a.at,
        params: { price: tx.price, rate: tx.ratePercent, commission: tx.commission, payout: tx.payout },
      };
      return {
        ...s,
        chats: [...s.chats, message, system],
        jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, price: tx.price, priceSource: 'chat' } : j)),
        // the customer is told which final price the artisan stated (the customer's consent is paying, see Payments)
        sms: [...s.sms, sms(a.ids[0], job.customerPhone, 'sms.priceProposed', { artisan: artisan?.name ?? '', customer: req?.customerName ?? '', price: tx.price }, a.at)],
        audit: [...s.audit, audit(a.ids[1], 'price', {
          artisan: artisan?.name ?? '', price: tx.price, rate: tx.ratePercent, commission: tx.commission,
        }, a.at)],
      };
    }

    case 'payStart': {
      const job = byId(s.jobs, a.jobId);
      if (!job || !checkPayStart(job, s.payments, a.method, a.phone).ok) return s; // the amount is read from the job, never from the UI
      const artisan = byId(s.artisans, job.artisanId);
      const payment: PaymentRec = {
        id: a.id, jobId: job.id, method: a.method, phone: a.phone ?? '', amount: job.price, status: 'pending', reference: a.ref, createdAt: a.at,
      };
      return {
        ...s,
        payments: [...s.payments, payment],
        audit: [...s.audit, audit(a.ids[0], 'payment', { event: 'started', artisan: artisan?.name ?? '', price: job.price, method: a.method }, a.at)],
      };
    }

    case 'paySettle': {
      const payment = byId(s.payments, a.id);
      const job = payment && byId(s.jobs, payment.jobId);
      const artisan = job && byId(s.artisans, job.artisanId);
      if (!payment || !job || !artisan || payment.status !== 'pending') return s; // a repeated callback changes nothing
      if (!a.ok) {
        return {
          ...s,
          payments: s.payments.map((p) => (p.id === payment.id ? { ...p, status: 'failed', settledAt: a.at } : p)),
          sms: [...s.sms, sms(a.ids[1], job.customerPhone, 'sms.payFailed', { price: payment.amount }, a.at)],
          audit: [...s.audit, audit(a.ids[3], 'payment', { event: 'failed', artisan: artisan.name, price: payment.amount }, a.at)],
        };
      }
      // Success: book the money. The commission is revenue NOW; the artisan's share waits as a pending payout.
      const split = paymentSucceededLines(payment.amount);
      const tx = computeCommission(payment.amount);
      const payout: Payout = {
        id: a.ids[0], jobId: job.id, artisanId: artisan.id, paymentId: payment.id, amount: split.payout, commission: split.commission,
        status: 'PENDING', createdAt: a.at,
      };
      return {
        ...s,
        payments: s.payments.map((p) => (p.id === payment.id ? { ...p, status: 'succeeded', settledAt: a.at } : p)),
        payouts: [...s.payouts, payout],
        ledger: postTx(s.ledger, `payment-succeeded:${payment.id}`, split.lines, a.at),
        // The job code (stored hashed) and the artisan's contact are unlocked only now.
        jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, codeHash: hashCode(a.code), commissionRate: tx.rate, commission: tx.commission, payout: tx.payout } : j)),
        sms: [
          ...s.sms,
          sms(a.ids[1], job.customerPhone, 'sms.jobCode', { artisan: artisan.name, code: a.code }, a.at),
          sms(a.ids[2], artisan.phone, 'sms.paymentReceived', { price: tx.price, rate: tx.ratePercent, commission: tx.commission, payout: tx.payout }, a.at),
        ],
        audit: [...s.audit, audit(a.ids[3], 'payment', {
          event: 'succeeded', artisan: artisan.name, price: tx.price, rate: tx.ratePercent, commission: tx.commission, payout: tx.payout,
        }, a.at)],
      };
    }

    case 'payoutHold': {
      const payout = byId(s.payouts, a.payoutId);
      if (!payout || !checkHold(payout, a.reason).ok) return s;
      const artisan = byId(s.artisans, payout.artisanId);
      return {
        ...s,
        payouts: s.payouts.map((p) => (p.id === payout.id ? { ...p, status: 'HELD', note: a.reason.trim() } : p)),
        audit: [...s.audit, audit(a.id, 'payout', { event: 'held', artisan: artisan?.name ?? '', payout: payout.amount, reason: a.reason.trim() }, a.at)],
      };
    }

    case 'payoutRelease': {
      const payout = byId(s.payouts, a.payoutId);
      const job = payout && byId(s.jobs, payout.jobId);
      if (!payout || !checkRelease(payout, job, a.reason).ok) return s;
      const artisan = byId(s.artisans, payout.artisanId);
      return {
        ...s,
        payouts: s.payouts.map((p) => (p.id === payout.id ? { ...p, status: 'PAID', paidAt: a.at, note: a.reason.trim() } : p)),
        ledger: postTx(s.ledger, `payout-paid:${payout.id}`, payoutPaidLines(payout.amount), a.at),
        sms: [...s.sms, sms(a.ids[0], artisan?.phone ?? '', 'sms.payoutPaid', { payout: payout.amount }, a.at)],
        audit: [...s.audit, audit(a.ids[1], 'payout', { event: 'released', artisan: artisan?.name ?? '', payout: payout.amount, reason: a.reason.trim() }, a.at)],
      };
    }

    case 'complete': {
      const job = byId(s.jobs, a.jobId);
      const artisan = job && byId(s.artisans, job.artisanId);
      if (!job || !artisan || !checkCompletion(job, a.entered).ok) return s;
      // The correct job code proves the work: the artisan's payout is released and paid unless an operator is holding it.
      const payout = s.payouts.find((p) => p.jobId === job.id);
      const pays = payout?.status === 'PENDING';
      return {
        ...s,
        jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, status: 'COMPLETED', codeUsed: true, completedAt: a.at } : j)),
        payouts: pays ? s.payouts.map((p) => (p.id === payout.id ? { ...p, status: 'PAID', paidAt: a.at } : p)) : s.payouts,
        ledger: pays ? postTx(s.ledger, `payout-paid:${payout.id}`, payoutPaidLines(payout.amount), a.at) : s.ledger,
        sms: [
          ...s.sms,
          sms(a.ids[0], job.customerPhone, 'sms.jobCompleted', { artisan: artisan.name, price: job.price }, a.at),
          ...(pays ? [sms(a.ids[2], artisan.phone, 'sms.payoutPaid', { payout: payout.amount }, a.at)] : []),
        ],
        audit: [
          ...s.audit,
          audit(a.ids[1], 'job_completed', { artisan: artisan.name }, a.at),
          ...(pays ? [audit(a.ids[3], 'payout', { event: 'paid', artisan: artisan.name, payout: payout.amount, reason: '' }, a.at)] : []),
        ],
      };
    }

    case 'rate': {
      const job = byId(s.jobs, a.jobId);
      if (!job || !checkRating(job, a.score, s.ratings).ok) return s;
      const artisan = byId(s.artisans, job.artisanId);
      const ratings = [...s.ratings, { id: a.ratingId, jobId: job.id, artisanId: job.artisanId, score: a.score, comment: a.comment.trim(), at: a.at }];
      const trust = artisan ? formatScore(trustFor(artisan, s.vouches, ratings, s.artisans)) : '';
      const rating: Rating = {
        id: a.ratingId, jobId: job.id, artisanId: job.artisanId, score: a.score, comment: a.comment.trim(), at: a.at,
      };
      return {
        ...s,
        ratings: [...s.ratings, rating],
        sms: [...s.sms, sms(a.ids[0], artisan?.phone ?? '', 'sms.rated', { score: a.score }, a.at)],
        audit: [
          ...s.audit,
          audit(a.ids[1], 'rating', { artisan: artisan?.name ?? '', score: a.score }, a.at),
          audit(a.ids[2], 'trust', { artisan: artisan?.name ?? '', trust }, a.at),
        ],
      };
    }

    case 'operator': {
      const artisan = byId(s.artisans, a.artisanId);
      if (!artisan) return s;
      return {
        ...s,
        artisans: s.artisans.map((x) =>
          x.id === artisan.id ? (a.approve ? { ...x, operatorApproved: true, rejected: false } : { ...x, rejected: true }) : x),
        sms: [...s.sms, sms(a.ids[0], artisan.phone, a.approve ? 'sms.verified' : 'sms.rejected', {}, a.at)],
        audit: [...s.audit, audit(a.ids[1], 'verification', { event: a.approve ? 'approved' : 'rejected', name: artisan.name }, a.at)],
      };
    }

    case 'patchArtisan':
      return { ...s, artisans: s.artisans.map((x) => (x.id === a.id ? { ...x, ...a.patch } : x)) };
    case 'patchRequest':
      return { ...s, requests: s.requests.map((x) => (x.id === a.id ? { ...x, ...a.patch } : x)) };
    case 'patchJob':
      return { ...s, jobs: s.jobs.map((x) => (x.id === a.id ? { ...x, ...a.patch } : x)) };

    case 'reset':
      return { ...initialState(), lang: a.lang };
  }
}

export const URGENCIES: Urgency[] = ['today', 'week', 'later'];
export const DEMO_CUSTOMER = SEED_CUSTOMER;
