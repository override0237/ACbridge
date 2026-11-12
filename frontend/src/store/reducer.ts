import type {
  Artisan, AuditEntry, AuditKind, Job, Lang, Rating, ServiceRequest, SmsMessage, Urgency, Vouch,
} from '../domain/types';
import { SEED_ARTISANS, SEED_CUSTOMER } from '../data/seed';
import {
  checkCompletion, checkRating, checkVouch, formatScore, hashCode, isVerified, trustFor,
} from '../domain/rules';

export type Screen =
  | 'home' | 'artisanSignup' | 'artisanStatus' | 'artisanInbox' | 'artisanComplete'
  | 'customerRequest' | 'matches' | 'tracking' | 'rate' | 'operator' | 'profile';

export interface UiState {
  screen: Screen;
  actingArtisanId: string | null;
  requestId: string | null;
  jobId: string | null;
  profileId: string | null;
  back: Screen;
}

export interface State {
  v: 1;
  lang: Lang;
  artisans: Artisan[];
  vouches: Vouch[];
  requests: ServiceRequest[];
  jobs: Job[];
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
  ratings: [],
  sms: [],
  audit: [],
  ui: { screen: 'home', actingArtisanId: null, requestId: null, jobId: null, profileId: null, back: 'home' },
});

export type Action =
  | { type: 'setLang'; lang: Lang }
  | { type: 'nav'; screen: Screen; patch?: Partial<UiState> }
  | { type: 'register'; artisan: Artisan; at: string; ids: string[] }
  | { type: 'vouch'; artisanId: string; voucherId: string; workedTogether: boolean; vouchId: string; at: string; ids: string[] }
  | { type: 'request'; request: ServiceRequest }
  | { type: 'choose'; jobId: string; requestId: string; artisanId: string; at: string; ids: string[] }
  | { type: 'answer'; jobId: string; accept: boolean; code: string; at: string; ids: string[] }
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

export function reducer(s: State, a: Action): State {
  switch (a.type) {
    case 'setLang':
      return { ...s, lang: a.lang };

    case 'nav':
      return { ...s, ui: { ...s.ui, ...a.patch, screen: a.screen } };

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
      if (!checkVouch(artisan, voucher, a.workedTogether, s.vouches).ok) return s;
      const vouch: Vouch = {
        id: a.vouchId, artisanId: artisan.id, voucherId: voucher.id, voucherPhone: voucher.phone,
        workedTogether: a.workedTogether, at: a.at,
      };
      const vouches = [...s.vouches, vouch];
      const was = isVerified(artisan, s.vouches, s.artisans);
      const now = isVerified(artisan, vouches, s.artisans);
      const out: SmsMessage[] = [sms(a.ids[0], artisan.phone, 'sms.vouchRecorded', { voucher: voucher.name }, a.at)];
      const log: AuditEntry[] = [audit(a.ids[1], 'verification', { event: 'vouch', name: artisan.name, voucher: voucher.name }, a.at)];
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
        status: 'REQUESTED', codeHash: null, codeUsed: false, createdAt: a.at,
      };
      return {
        ...s,
        jobs: [...s.jobs, job],
        sms: [...s.sms, sms(a.ids[0], artisan.phone, 'sms.jobRequest', { customer: req.customerName, urgency: req.urgency, trade: req.trade }, a.at)],
        ui: { ...s.ui, jobId: job.id, screen: 'tracking' },
      };
    }

    case 'answer': {
      const job = byId(s.jobs, a.jobId);
      const artisan = job && byId(s.artisans, job.artisanId);
      if (!job || !artisan || job.status !== 'REQUESTED') return s;
      if (!a.accept) {
        return {
          ...s,
          jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, status: 'DECLINED' } : j)),
          sms: [...s.sms, sms(a.ids[0], job.customerPhone, 'sms.jobDeclined', { artisan: artisan.name }, a.at)],
        };
      }
      return {
        ...s,
        jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, status: 'ACCEPTED', codeHash: hashCode(a.code), acceptedAt: a.at } : j)),
        // The plain code exists only inside this SMS to the customer; the job stores its hash.
        sms: [...s.sms, sms(a.ids[0], job.customerPhone, 'sms.jobCode', { artisan: artisan.name, code: a.code }, a.at)],
        audit: [...s.audit, audit(a.ids[1], 'job_accepted', { artisan: artisan.name }, a.at)],
      };
    }

    case 'complete': {
      const job = byId(s.jobs, a.jobId);
      const artisan = job && byId(s.artisans, job.artisanId);
      if (!job || !artisan || !checkCompletion(job, a.entered).ok) return s;
      return {
        ...s,
        jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, status: 'COMPLETED', codeUsed: true, completedAt: a.at } : j)),
        sms: [...s.sms, sms(a.ids[0], job.customerPhone, 'sms.jobCompleted', { artisan: artisan.name }, a.at)],
        audit: [...s.audit, audit(a.ids[1], 'job_completed', { artisan: artisan.name }, a.at)],
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
