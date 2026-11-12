import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import { API_MODE, NEIGHBOURHOOD, TRADE } from '../config';
import { SEED_CUSTOMER, SEED_VOUCHERS } from '../data/seed';
import {
  checkCompletion, checkRating, checkVouch, generateJobCode, normalizePhone, type CompletionCheck, type RatingCheck,
} from '../domain/rules';
import type { Artisan, Lang, Urgency } from '../domain/types';
import { translate, type Key, type Params } from '../i18n';
import * as bridge from '../api/bridge';
import { clearState, loadState, saveState } from './persistence';
import { reducer, type Action, type Screen, type State, type UiState } from './reducer';

const uid = (p: string): string => `${p}-${Math.random().toString(36).slice(2, 9)}${Date.now().toString(36).slice(-3)}`;
const ids = (n: number): string[] => Array.from({ length: n }, () => uid('e'));
const now = (): string => new Date().toISOString();

export type RegisterResult = { ok: true; id: string } | { ok: false; error: Key };
export type VouchResult = { ok: true } | { ok: false; error: Key };

const VOUCH_ERRORS: Record<string, Key> = {
  self: 'status.errSelf', not_verified: 'status.errNotVerified', same_phone: 'status.errSamePhone',
  duplicate: 'status.errDuplicate', no_job_together: 'status.errNoJob',
};

export interface Actions {
  setLang(l: Lang): void;
  go(screen: Screen, patch?: Partial<UiState>): void;
  registerArtisan(v: { name: string; phone: string; description: string }): RegisterResult;
  vouch(artisanId: string, seedIndex: number): VouchResult;
  submitRequest(v: { urgency: Urgency; description: string }): void;
  choose(artisanId: string): void;
  answer(jobId: string, accept: boolean): void;
  complete(jobId: string, entered: string): CompletionCheck;
  rate(jobId: string, score: number, comment: string): RatingCheck;
  operator(artisanId: string, approve: boolean): void;
  reset(): void;
}

interface Ctx {
  state: State;
  actions: Actions;
  t: (key: Key, params?: Params) => string;
  notice: string | null;
  clearNotice(): void;
}

const StoreContext = createContext<Ctx | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, loadState);
  const [notice, setNotice] = useState<string | null>(null);
  const ref = useRef(state);
  ref.current = state;

  useEffect(() => saveState(state), [state]);

  const t = useCallback((key: Key, params?: Params) => translate(state.lang, key, params), [state.lang]);

  /** API mode only: run a backend mirror step; on failure the demo keeps working offline and shows a notice. */
  const mirror = useCallback(async (step: () => Promise<void>) => {
    if (API_MODE !== 'api') return;
    try { await step(); } catch (e) { setNotice(`${translate(ref.current.lang, 'mode.api')}: ${(e as Error).message}`); }
  }, []);

  const actions = useMemo<Actions>(() => {
    const find = <T extends { id: string }>(list: T[], id: string | null | undefined) => list.find((x) => x.id === id);
    return {
      setLang: (lang) => dispatch({ type: 'setLang', lang }),
      go: (screen, patch) => dispatch({ type: 'nav', screen, patch }),

      registerArtisan({ name, phone, description }) {
        const s = ref.current;
        const cleanName = name.trim();
        if (cleanName.length < 2) return { ok: false, error: 'signup.errName' };
        const normalized = normalizePhone(phone);
        if (!normalized) return { ok: false, error: 'signup.errPhone' };
        if (s.artisans.some((a) => a.phone === normalized)) return { ok: false, error: 'signup.errTaken' };
        const artisan: Artisan = {
          id: uid('artisan'), name: cleanName, phone: normalized, trade: TRADE, neighbourhood: NEIGHBOURHOOD,
          description: description.trim(), baseRating: 0, baseJobs: 0, avgResponseMin: 20,
          priceMin: 3000, priceMax: 8000, seedVerified: false, isSeed: false,
        };
        dispatch({ type: 'register', artisan, at: now(), ids: ids(4) });
        void mirror(async () => {
          const remoteId = await bridge.registerArtisan(artisan);
          dispatch({ type: 'patchArtisan', id: artisan.id, patch: { remoteId } });
        });
        return { ok: true, id: artisan.id };
      },

      vouch(artisanId, seedIndex) {
        const s = ref.current;
        const artisan = find(s.artisans, artisanId);
        const voucher = find(s.artisans, SEED_VOUCHERS[seedIndex]);
        if (!artisan || !voucher) return { ok: false, error: 'status.noArtisan' };
        const check = checkVouch(artisan, voucher, true, s.vouches); // demo voucher attests a job together
        if (!check.ok) return { ok: false, error: VOUCH_ERRORS[check.reason] };
        dispatch({ type: 'vouch', artisanId, voucherId: voucher.id, workedTogether: true, vouchId: uid('vouch'), at: now(), ids: ids(4) });
        void mirror(async () => {
          // wait for the profile to be linked (registration mirror runs first)
          const linked = await waitForRemote(() => find(ref.current.artisans, artisanId));
          await bridge.vouch(linked, voucher);
          const count = ref.current.vouches.filter((v) => v.artisanId === artisanId).length;
          if (count >= 2) await bridge.verifyAfterVouches(linked);
        });
        return { ok: true };
      },

      submitRequest({ urgency, description }) {
        const request = {
          id: uid('req'), customerPhone: SEED_CUSTOMER.phone, customerName: SEED_CUSTOMER.name, trade: TRADE,
          neighbourhood: NEIGHBOURHOOD, urgency, description: description.trim(), at: now(),
        };
        dispatch({ type: 'request', request });
        void mirror(async () => {
          const { requestId, links } = await bridge.createRequest(request, ref.current.artisans);
          dispatch({ type: 'patchRequest', id: request.id, patch: { remoteId: requestId } });
          for (const [localId, remoteId] of Object.entries(links)) dispatch({ type: 'patchArtisan', id: localId, patch: { remoteId } });
        });
      },

      choose(artisanId) {
        const s = ref.current;
        const requestId = s.ui.requestId;
        if (!requestId) return;
        const jobId = uid('job');
        dispatch({ type: 'choose', jobId, requestId, artisanId, at: now(), ids: ids(1) });
        void mirror(async () => {
          const req = find(ref.current.requests, requestId);
          const artisan = find(ref.current.artisans, artisanId);
          if (!req || !artisan) return;
          const remoteId = await bridge.chooseArtisan(req, artisan);
          if (remoteId) dispatch({ type: 'patchJob', id: jobId, patch: { remoteId } });
        });
      },

      answer(jobId, accept) {
        // The job code is generated here (impure) and handed to the pure reducer, which stores only its hash.
        dispatch({ type: 'answer', jobId, accept, code: generateJobCode(), at: now(), ids: ids(2) });
        if (accept) {
          void mirror(async () => {
            const job = find(ref.current.jobs, jobId);
            const artisan = find(ref.current.artisans, job?.artisanId);
            if (job && artisan) await bridge.acceptJob(job, artisan);
          });
        }
      },

      complete(jobId, entered) {
        const job = find(ref.current.jobs, jobId);
        if (!job) return { ok: false, reason: 'not_accepted' };
        const result = checkCompletion(job, entered);
        if (!result.ok) return result;
        dispatch({ type: 'complete', jobId, entered, at: now(), ids: ids(2) });
        void mirror(async () => {
          const artisan = find(ref.current.artisans, job.artisanId);
          if (artisan) await bridge.completeJob(job, artisan);
        });
        return result;
      },

      rate(jobId, score, comment) {
        const s = ref.current;
        const result = checkRating(find(s.jobs, jobId), score, s.ratings);
        if (!result.ok) return result;
        dispatch({ type: 'rate', ratingId: uid('rating'), jobId, score, comment, at: now(), ids: ids(3) });
        void mirror(async () => {
          const job = find(ref.current.jobs, jobId);
          if (job) await bridge.review(job, score, comment);
        });
        return result;
      },

      operator(artisanId, approve) {
        dispatch({ type: 'operator', artisanId, approve, at: now(), ids: ids(2) });
        void mirror(async () => {
          const artisan = find(ref.current.artisans, artisanId);
          if (artisan) await bridge.operatorDecision(artisan, approve);
        });
      },

      reset() {
        clearState();
        dispatch({ type: 'reset', lang: ref.current.lang });
      },
    } satisfies Actions;
  }, [mirror]);

  const value = useMemo<Ctx>(
    () => ({ state, actions, t, notice, clearNotice: () => setNotice(null) }),
    [state, actions, t, notice],
  );
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

/** Poll briefly until the registration mirror has stored the backend artisan id. */
async function waitForRemote(get: () => Artisan | undefined): Promise<Artisan> {
  for (let i = 0; i < 40; i++) {
    const a = get();
    if (a?.remoteId) return a;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error('Artisan is not registered on the backend yet');
}

export function useStore(): Ctx {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStore must be used inside StoreProvider');
  return ctx;
}

export type { Action };
