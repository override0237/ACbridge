import { describe, expect, it, vi } from 'vitest';
import { ApiError, SchemaError, createApiClient } from './client';

const id = '11111111-2222-3333-4444-555555555555';
const reply = (status: number, body: unknown) => ({ ok: status < 300, status, json: async () => body }) as Response;

describe('the typed API client', () => {
  it('validates responses, sends the bearer token and never sends an amount when paying', async () => {
    const fetchImpl = vi.fn(async () =>
      reply(201, { payment_id: id, job_id: id, payment_type: 'JOB_PAYMENT', amount: 9000, currency: 'XAF', status: 'PENDING', created_at: '2026-01-01T00:00:00Z' }));
    const api = createApiClient({ baseUrl: 'https://api.test', fetchImpl: fetchImpl as unknown as typeof fetch, getToken: () => 'tok-123' });
    const payment = await api.pay(id, 'idem-1');
    expect(payment.amount).toBe(9000);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`https://api.test/jobs/${id}/pay`);
    expect(init.body).toBeUndefined(); // the client never sends an amount
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('idem-1');
  });

  it('rejects a response that is not the expected shape', async () => {
    const api = createApiClient({ baseUrl: 'x', fetchImpl: (async () => reply(200, { status: 123 })) as unknown as typeof fetch });
    await expect(api.health()).rejects.toBeInstanceOf(SchemaError);
  });

  it('turns HTTP errors into ApiError, scrubs phone numbers from the message and signals a 401', async () => {
    const onUnauthorized = vi.fn();
    const api = createApiClient({
      baseUrl: 'x',
      onUnauthorized,
      fetchImpl: (async () => reply(401, { detail: 'No account for +237670123456' })) as unknown as typeof fetch,
    });
    const err = await api.health().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.message).not.toContain('670123456');
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it('web mode sends the session cookie instead of a token', async () => {
    const fetchImpl = vi.fn(async () => reply(200, { status: 'ok' }));
    const api = createApiClient({ baseUrl: 'x', credentials: 'include', fetchImpl: fetchImpl as unknown as typeof fetch });
    await api.health();
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.credentials).toBe('include');
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});
