import { describe, expect, it } from 'vitest';
import {
  ChatSendSchema, JobSchema, LedgerSchema, MatchesSchema, PaymentSchema, PayoutSchema, ReconciliationSchema, ServiceRequestSchema,
  SkillSchema, TokenSchema,
} from './index';

const id = '11111111-2222-3333-4444-555555555555';
const at = '2026-01-01T00:00:00Z';

describe('API schemas accept what the backend sends and reject what it should not', () => {
  it('token', () => {
    expect(TokenSchema.parse({ access_token: 'x'.repeat(20), token_type: 'bearer', user_id: id, role: 'ARTISAN' }).role).toBe('ARTISAN');
    expect(TokenSchema.safeParse({ access_token: 'short', token_type: 'bearer', user_id: id, role: 'ARTISAN' }).success).toBe(false);
    expect(TokenSchema.safeParse({ access_token: 'x'.repeat(20), token_type: 'bearer', user_id: id, role: 'KING' }).success).toBe(false);
  });

  it('skill, service request and matches (price ranges stay integers)', () => {
    expect(SkillSchema.safeParse({ skill_id: id, skill_name: 'Plumbing', safety_critical: false }).success).toBe(true);
    const req = { request_id: id, customer_id: id, skill_id: id, description: 'Leaking tap', location: 'Buea', budget: null, needs_inspection: false, urgency: 'TODAY', status: 'OPEN', created_at: at };
    expect(ServiceRequestSchema.safeParse(req).success).toBe(true);
    expect(ServiceRequestSchema.safeParse({ ...req, urgency: 'ASAP' }).success).toBe(false);
    const match = { artisan_id: id, full_name: 'Grace', location: 'Molyko', availability_status: 'AVAILABLE', skill_verification_status: 'VERIFIED', typical_price: 6000, verified_reviews: 3, reputation_score: 4.5, match_score: 80.1 };
    const body = { request_id: id, service_area_supported: true, matches: [match], excluded_summary: { not_available: 1 }, disclaimer: 'x' };
    expect(MatchesSchema.safeParse(body).success).toBe(true);
    expect(MatchesSchema.safeParse({ ...body, matches: [{ ...match, typical_price: 6000.5 }] }).success).toBe(false);
  });

  it('job, payment, chat, payout, ledger and reconciliation', () => {
    const job = { job_id: id, request_id: id, artisan_id: id, customer_id: id, pricing_mode: 'FIXED_PRICE', proposed_price: 9000, proposed_by: 'ARTISAN', agreed_price: null, artisan_agreed: false, status: 'REQUESTED', customer_confirmed: false, artisan_confirmed: false, created_at: at, counterpart_phone: null, events: [], extra_field_from_a_newer_backend: 1 };
    expect(JobSchema.safeParse(job).success).toBe(true); // unknown fields are tolerated
    expect(JobSchema.safeParse({ ...job, status: 'ON_FIRE' }).success).toBe(false);
    expect(PaymentSchema.safeParse({ payment_id: id, job_id: id, payment_type: 'JOB_PAYMENT', amount: 9000, currency: 'XAF', status: 'SUCCEEDED', created_at: at }).success).toBe(true);
    const msg = { message_id: id, job_id: id, sender_role: 'ARTISAN', body: 'final price 9000 FCFA', created_at: at, proposed_price: 9000, commission_if_agreed: 450, artisan_receives_if_agreed: 8550 };
    expect(ChatSendSchema.safeParse({ message: msg, price_status: 'APPLIED' }).success).toBe(true);
    expect(ChatSendSchema.safeParse({ message: msg, price_status: 'NOT_CUSTOMER' }).success).toBe(false); // the old status no longer exists
    expect(PayoutSchema.safeParse({ payout_id: id, job_id: id, artisan_name: 'Grace', amount: 5700, commission: 300, status: 'HELD', note: 'dispute' }).success).toBe(true);
    expect(LedgerSchema.safeParse({ balances: { collection: 6000 }, balanced: true, unbalanced_transactions: [] }).success).toBe(true);
    expect(ReconciliationSchema.safeParse({ ledger: {}, differences: { collected: 500 }, mismatch: true, status: 'MISMATCH', completed_jobs_without_payment: [] }).success).toBe(true);
    expect(ReconciliationSchema.safeParse({ ledger: {}, differences: {}, mismatch: false, status: 'MAYBE', completed_jobs_without_payment: [] }).success).toBe(false);
  });
});
