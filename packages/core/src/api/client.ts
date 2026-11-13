/**
 * Typed API client. Platform-neutral: it takes `fetch` and a token getter, so the web app (httpOnly cookie, `credentials: 'include'`)
 * and the mobile app (token from secure storage) can both use it.
 *
 *  - every response body is validated with its zod schema before it is returned;
 *  - the client never sends an amount for a payment (the server reads it from the job);
 *  - error messages are scrubbed of phone numbers before they can reach logs or error reports.
 */
import { z } from 'zod';
import { stripPhones } from '../phone';
import {
  ChatMessageSchema, ChatSendSchema, JobSchema, LedgerSchema, MatchesSchema, PaymentSchema, PayoutSchema, ReconciliationSchema,
  ServiceRequestSchema, SkillSchema,
} from '../schemas';

export class ApiError extends Error {
  constructor(public readonly status: number, detail: string) {
    super(stripPhones(detail));
    this.name = 'ApiError';
  }
}

/** The server answered, but not with the shape the app expects. */
export class SchemaError extends Error {
  constructor(public readonly path: string, public readonly issues: string[]) {
    super(`Unexpected response from ${path}: ${issues.slice(0, 3).join('; ')}`);
    this.name = 'SchemaError';
  }
}

export interface ClientOptions {
  baseUrl: string;
  /** Mobile: returns the token from secure storage. Web: omit (the httpOnly session cookie is sent instead). */
  getToken?: () => string | null | Promise<string | null>;
  fetchImpl?: typeof fetch;
  /** Web sets this to 'include' so the session cookie travels with every request. */
  credentials?: RequestCredentials;
  /** Called on a 401 so the app can send the user back to sign-in with their place saved. */
  onUnauthorized?: () => void;
}

export function createApiClient(options: ClientOptions) {
  const doFetch = options.fetchImpl ?? fetch;

  async function request<S extends z.ZodTypeAny>(
    method: string, path: string, schema: S, init: { body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<z.infer<S>> {
    const token = options.getToken ? await options.getToken() : null;
    const res = await doFetch(`${options.baseUrl}${path}`, {
      method,
      credentials: options.credentials,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
    const data: unknown = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401) options.onUnauthorized?.();
      const detail = (data as { detail?: unknown } | null)?.detail;
      throw new ApiError(res.status, typeof detail === 'string' ? detail : `HTTP ${res.status}`);
    }
    const parsed = schema.safeParse(data);
    if (!parsed.success) throw new SchemaError(path, parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`));
    return parsed.data;
  }

  return {
    request,
    health: () => request('GET', '/health', z.object({ status: z.string() }).passthrough()),
    skills: () => request('GET', '/skills', z.array(SkillSchema)),
    createRequest: (body: { skill_id: string; description: string; location: string; urgency: 'TODAY' | 'THIS_WEEK' | 'NOT_URGENT' }) =>
      request('POST', '/service-requests', ServiceRequestSchema, { body }),
    matches: (requestId: string) => request('GET', `/matches/${requestId}`, MatchesSchema),
    job: (jobId: string) => request('GET', `/jobs/${jobId}`, JobSchema),
    /** Starts the payment for the job's agreed price. No amount is sent: the server reads it from the job. */
    pay: (jobId: string, idempotencyKey: string) =>
      request('POST', `/jobs/${jobId}/pay`, PaymentSchema, { headers: { 'Idempotency-Key': idempotencyKey } }),
    payment: (paymentId: string) => request('GET', `/payments/${paymentId}`, PaymentSchema),
    messages: (jobId: string) => request('GET', `/jobs/${jobId}/messages`, z.array(ChatMessageSchema)),
    sendMessage: (jobId: string, body: string) => request('POST', `/jobs/${jobId}/messages`, ChatSendSchema, { body: { body } }),
    operator: {
      ledger: () => request('GET', '/operator/ledger', LedgerSchema),
      payouts: () => request('GET', '/operator/payouts', z.array(PayoutSchema)),
      reconciliation: () => request('GET', '/operator/reconciliation', ReconciliationSchema),
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
