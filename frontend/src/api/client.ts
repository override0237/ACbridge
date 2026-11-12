/**
 * Minimal typed client for the ACbridge FastAPI backend (backend/app/routers/*).
 * Calls go to /api/* and the Vite dev proxy forwards them to the backend, so no CORS change is needed.
 * Only used when VITE_API_MODE=api.
 */
import { API_BASE, DEMO_PASSWORD } from '../config';

const BASE = API_BASE ?? '/api';
const tokens = new Map<string, string>(); // phone -> bearer token (memory only)
const passwords = new Map<string, string>(); // phone -> password typed this session (memory only, never stored)

/** Called when someone registers or logs in so the backend login uses their real password; seeded accounts use the demo one. */
export function rememberPassword(phone: string, password: string): void {
  passwords.set(phone, password);
  tokens.delete(phone);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, token?: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `HTTP ${res.status}`);
  }
  return data as T;
}

export interface TokenOut { access_token: string; user_id: string; role: string }
export interface SkillOut { skill_id: string; skill_name: string }
export interface ArtisanOut { artisan_id: string; full_name: string; identity_verified: boolean; skills: { skill_id: string; verification_status: string }[] }
export interface MatchOut { artisan_id: string; full_name: string; typical_price: number | null; reputation_score: number; verified_reviews: number }
export interface JobOut { job_id: string; status: string }

export async function login(phone: string, password = passwords.get(phone) ?? DEMO_PASSWORD): Promise<string> {
  const cached = tokens.get(phone);
  if (cached) return cached;
  const out = await call<TokenOut>('POST', '/auth/login', undefined, { phone, password });
  tokens.set(phone, out.access_token);
  return out.access_token;
}

export const api = {
  health: () => call<{ status: string }>('GET', '/health'),
  register: (phone: string, role: 'CUSTOMER' | 'ARTISAN', password = passwords.get(phone) ?? DEMO_PASSWORD) =>
    call('POST', '/auth/register', undefined, { phone, password, role }),
  skills: () => call<SkillOut[]>('GET', '/skills'),
  createProfile: (t: string, body: { full_name: string; location: string; description?: string }) =>
    call<ArtisanOut>('POST', '/artisans', t, { availability_status: 'AVAILABLE', ...body }),
  addSkill: (t: string, artisanId: string, skillId: string, typicalPrice: number) =>
    call('POST', `/artisans/${artisanId}/skills`, t, { skill_id: skillId, proficiency_level: 'INTERMEDIATE', typical_price: typicalPrice }),
  endorse: (t: string, artisanId: string, evidence: string) =>
    call('POST', `/artisans/${artisanId}/endorsements`, t, { evidence_description: evidence }),
  submitCheck: (t: string, skillId: string, evidence: string) =>
    call<{ check_id: string }>('POST', '/verifications', t, { check_type: 'SKILL', skill_id: skillId, evidence_description: evidence }),
  decide: (t: string, checkId: string, decision: 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED', notes?: string) =>
    call('POST', `/verifications/${checkId}/decision`, t, { decision, decision_notes: notes }),
  createRequest: (t: string, body: { skill_id: string; description: string; location: string; budget?: number }) =>
    call<{ request_id: string }>('POST', '/service-requests', t, body),
  matches: (t: string, requestId: string) => call<{ matches: MatchOut[] }>('GET', `/matches/${requestId}`, t),
  createJob: (t: string, requestId: string, artisanId: string, agreedPrice: number) =>
    call<JobOut>('POST', '/jobs', t, { request_id: requestId, artisan_id: artisanId, agreed_price: agreedPrice }),
  jobAction: (t: string, jobId: string, action: 'accept' | 'start' | 'confirm-completion') =>
    call<JobOut>('POST', `/jobs/${jobId}/${action}`, t),
  review: (t: string, jobId: string, rating: number, comment: string) =>
    call('POST', `/jobs/${jobId}/reviews`, t, { rating, comment: comment || null }),
};
