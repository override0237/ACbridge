/**
 * Mirrors the local demo journey onto the real backend (API mode). The UI state stays the source of truth for
 * display; the backend is the system of record. Each step maps to one backend rule:
 *
 *   vouch               -> POST /artisans/{id}/endorsements          (backend "endorsement")
 *   2nd vouch           -> POST /verifications + verifier APPROVED    (simulated verifier, see README)
 *   artisan taps YES    -> POST /jobs/{id}/accept
 *   correct job code    -> artisan AND customer POST confirm-completion (backend needs both sides)
 *   customer rates      -> POST /jobs/{id}/reviews
 *
 * The 6-digit job code itself is a front-end mechanism; the backend has no code endpoint (see README).
 */
import type { Artisan, Job, ServiceRequest } from '../domain/types';
import { NEIGHBOURHOOD } from '../config';
import { api, login } from './client';

const VERIFIER_PHONE = '+237670000002';
const TOWN = 'Buea'; // backend supports buea,limbe; "Neighbourhood A" is a placeholder inside Buea
const LOCATION = `${NEIGHBOURHOOD}, ${TOWN}`;

let plumbingId: string | null = null;
async function plumbing(): Promise<string> {
  if (plumbingId) return plumbingId;
  const skills = await api.skills();
  const s = skills.find((x) => x.skill_name.toLowerCase() === 'plumbing');
  if (!s) throw new Error('Plumbing skill not found on the backend (run python -m app.seed)');
  plumbingId = s.skill_id;
  return plumbingId;
}

/** Register the new artisan on the backend. Returns the backend artisan_id. */
export async function registerArtisan(a: Artisan): Promise<string> {
  await api.register(a.phone, 'ARTISAN').catch(() => undefined); // already registered is fine
  const t = await login(a.phone);
  const profile = await api.createProfile(t, { full_name: a.name, location: LOCATION, description: a.description || undefined });
  await api.addSkill(t, profile.artisan_id, await plumbing(), Math.round((a.priceMin + a.priceMax) / 2));
  return profile.artisan_id;
}

export async function vouch(artisan: Artisan, voucher: Artisan): Promise<void> {
  if (!artisan.remoteId) return;
  const t = await login(voucher.phone);
  await api.endorse(t, artisan.remoteId, `${voucher.name} worked with ${artisan.name} on plumbing jobs in ${NEIGHBOURHOOD}.`);
}

/** After 2 vouches the artisan asks for skill verification and the (simulated) verifier approves. */
export async function verifyAfterVouches(artisan: Artisan): Promise<void> {
  if (!artisan.remoteId) return;
  const t = await login(artisan.phone);
  const check = await api.submitCheck(t, await plumbing(), `Plumber in ${NEIGHBOURHOOD}, vouched by two verified plumbers.`);
  const v = await login(VERIFIER_PHONE);
  await api.decide(v, check.check_id, 'UNDER_REVIEW');
  await api.decide(v, check.check_id, 'APPROVED', 'SIMULATED: demo approval after 2 vouches');
}

/** Operator panel decision on a pending artisan. */
export async function operatorDecision(artisan: Artisan, approve: boolean): Promise<void> {
  if (!artisan.remoteId) return;
  const t = await login(artisan.phone);
  const check = await api.submitCheck(t, await plumbing(), 'Operator review').catch(() => null);
  if (!check) return;
  const v = await login(VERIFIER_PHONE);
  await api.decide(v, check.check_id, 'UNDER_REVIEW');
  await api.decide(v, check.check_id, approve ? 'APPROVED' : 'REJECTED', 'SIMULATED operator decision');
}

/** Create the backend service request and link local artisans to backend ids by name. */
export async function createRequest(
  req: ServiceRequest, artisans: Artisan[],
): Promise<{ requestId: string; links: Record<string, string> }> {
  await api.register(req.customerPhone, 'CUSTOMER').catch(() => undefined);
  const t = await login(req.customerPhone);
  const created = await api.createRequest(t, {
    skill_id: await plumbing(),
    description: req.description || 'Plumbing help needed',
    location: LOCATION,
  });
  const { matches } = await api.matches(t, created.request_id);
  const links: Record<string, string> = {};
  for (const m of matches) {
    const local = artisans.find((a) => !a.remoteId && m.full_name.toLowerCase().startsWith(a.name.toLowerCase()));
    if (local) links[local.id] = m.artisan_id;
  }
  return { requestId: created.request_id, links };
}

export async function chooseArtisan(req: ServiceRequest, artisan: Artisan): Promise<string | null> {
  if (!req.remoteId || !artisan.remoteId) return null;
  const t = await login(req.customerPhone);
  const job = await api.createJob(t, req.remoteId, artisan.remoteId, Math.round((artisan.priceMin + artisan.priceMax) / 2));
  return job.job_id;
}

export async function acceptJob(job: Job, artisan: Artisan): Promise<void> {
  if (!job.remoteId) return;
  await api.jobAction(await login(artisan.phone), job.remoteId, 'accept');
}

/** The correct job code stands for both parties confirming; the backend needs each side's confirmation. */
export async function completeJob(job: Job, artisan: Artisan): Promise<void> {
  if (!job.remoteId) return;
  const at = await login(artisan.phone);
  await api.jobAction(at, job.remoteId, 'start');
  await api.jobAction(at, job.remoteId, 'confirm-completion');
  await api.jobAction(await login(job.customerPhone), job.remoteId, 'confirm-completion');
}

export async function review(job: Job, score: number, comment: string): Promise<void> {
  if (!job.remoteId) return;
  await api.review(await login(job.customerPhone), job.remoteId, score, comment);
}

