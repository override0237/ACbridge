import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as bridge from '../api/bridge';
import { SEED_ARTISANS } from '../data/seed';
import type { Artisan, Job, ServiceRequest } from '../domain/types';

// Routes that exist in backend/app/routers/*.py (method + path pattern).
const BACKEND_ROUTES = [
  'POST /auth/register', 'POST /auth/login', 'GET /skills', 'POST /artisans', 'POST /artisans/:id/skills',
  'POST /artisans/:id/endorsements', 'POST /verifications', 'POST /verifications/:id/decision',
  'POST /service-requests', 'GET /matches/:id', 'POST /jobs', 'POST /jobs/:id/accept', 'POST /jobs/:id/start',
  'POST /jobs/:id/confirm-completion', 'POST /jobs/:id/reviews',
];
const pattern = (m: string, p: string) => `${m} ${p.replace(/\/[0-9a-f-]{8,}/g, '/:id').replace(/\/(?=[a-z])/g, '/')}`;

const calls: { route: string; body: unknown; auth: string | null }[] = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = url.replace(/^.*?\/api/, '');
    const method = init.method ?? 'GET';
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ route: pattern(method, path), body, auth: (init.headers as Record<string, string>).Authorization ?? null });
    const json = (data: unknown, status = 200) => ({ ok: status < 300, status, json: async () => data });
    if (path === '/skills') return json([{ skill_id: 'aaaaaaaa-1111', skill_name: 'Plumbing' }]);
    if (path === '/auth/login') return json({ access_token: `tok-${body.phone}`, user_id: 'u', role: 'X' });
    if (path === '/auth/register') return json({}, 201);
    if (path === '/artisans') return json({ artisan_id: 'bbbbbbbb-2222' }, 201);
    if (path === '/verifications') return json({ check_id: 'cccccccc-3333' }, 201);
    if (path === '/service-requests') return json({ request_id: 'dddddddd-4444' }, 201);
    if (path.startsWith('/matches/')) return json({ matches: [{ artisan_id: 'eeeeeeee-5555', full_name: 'Grace Ndifor' }] });
    if (path === '/jobs') return json({ job_id: 'ffffffff-6666', status: 'REQUESTED' }, 201);
    return json({ job_id: 'ffffffff-6666', status: 'OK' });
  }));
});
afterEach(() => vi.unstubAllGlobals());

const joel: Artisan = { ...SEED_ARTISANS[0], id: 'new', name: 'Joel', phone: '+237670111222', isSeed: false, seedVerified: false };
const grace = SEED_ARTISANS[0];

describe('API bridge calls only routes the backend defines', () => {
  it('runs the whole journey and uses the right accounts', async () => {
    const remoteId = await bridge.registerArtisan(joel);
    expect(remoteId).toBe('bbbbbbbb-2222');
    const linked = { ...joel, remoteId };
    await bridge.vouch(linked, SEED_ARTISANS[0]);
    await bridge.vouch(linked, SEED_ARTISANS[1]);
    await bridge.verifyAfterVouches(linked);
    const req: ServiceRequest = { id: 'r', customerPhone: '+237690000030', customerName: 'Mary', trade: 'Plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: '', at: '' };
    const created = await bridge.createRequest(req, [...SEED_ARTISANS]);
    expect(created.links['seed-1']).toBe('eeeeeeee-5555'); // Grace linked by name
    const jobId = await bridge.chooseArtisan({ ...req, remoteId: created.requestId }, { ...grace, remoteId: 'eeeeeeee-5555' });
    expect(jobId).toBe('ffffffff-6666');
    const job: Job = { id: 'j', requestId: 'r', artisanId: 'seed-1', customerPhone: req.customerPhone, status: 'ACCEPTED', codeHash: 'x', codeUsed: false, createdAt: '', remoteId: jobId! };
    await bridge.acceptJob(job, grace);
    await bridge.completeJob(job, grace);
    await bridge.review(job, 5, 'Good');

    for (const c of calls) expect(BACKEND_ROUTES).toContain(c.route);
    const routes = calls.map((c) => c.route);
    expect(routes.filter((r) => r === 'POST /artisans/:id/endorsements')).toHaveLength(2);
    expect(routes.filter((r) => r === 'POST /jobs/:id/confirm-completion')).toHaveLength(2); // artisan + customer
    // endorsements are made by the seeded artisans, completion confirmed by BOTH parties
    const ends = calls.filter((c) => c.route.endsWith('/endorsements')).map((c) => c.auth);
    expect(ends).toEqual(['Bearer tok-+237690000015', 'Bearer tok-+237690000011']);
    const confirms = calls.filter((c) => c.route.endsWith('/confirm-completion')).map((c) => c.auth);
    expect(new Set(confirms).size).toBe(2);
    expect(calls.find((c) => c.route === 'POST /jobs/:id/reviews')?.body).toEqual({ rating: 5, comment: 'Good' });
    expect((calls.find((c) => c.route === 'POST /artisans')?.body as { location: string }).location).toBe('Neighbourhood A, Buea');
  });
});
