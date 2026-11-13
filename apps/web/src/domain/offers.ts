/**
 * Job offers expire. An artisan who does not ACCEPT an offer in time loses it and the offer is nullified:
 *   urgent (Today) = 1 hour, This week = 1 day, Not urgent = 5 days.
 * Same windows as the backend (OFFER_TTL_HOURS_*). Only an offer that is still waiting for an answer can expire:
 * once the artisan has said YES (or NO) the offer is answered.
 */
import type { Job, ServiceRequest, Urgency } from './types';

const HOUR = 60 * 60 * 1000;
export const OFFER_TTL_MS: Record<Urgency, number> = { today: 1 * HOUR, week: 24 * HOUR, later: 5 * 24 * HOUR };

export const offerDeadline = (job: Job, request: ServiceRequest | undefined): number =>
  new Date(job.createdAt).getTime() + OFFER_TTL_MS[request?.urgency ?? 'later'];

/** True when the offer is still unanswered and its deadline has passed at `nowMs`. */
export const isOfferExpired = (job: Job, request: ServiceRequest | undefined, nowMs: number): boolean =>
  job.status === 'REQUESTED' && nowMs > offerDeadline(job, request);

/** Milliseconds the artisan has left to answer (never negative). */
export const timeLeftMs = (job: Job, request: ServiceRequest | undefined, nowMs: number): number =>
  Math.max(0, offerDeadline(job, request) - nowMs);

/** "59 min", "5 h 20 min", "2 d 3 h": short, language-neutral. */
export function formatLeft(ms: number): string {
  const min = Math.ceil(ms / 60000);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ${min % 60} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}
