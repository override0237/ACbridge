/**
 * zod schemas for the backend's API payloads (mapped from backend/openapi.json). Every response is validated with one of these
 * BEFORE the apps use it. Schemas are tolerant of extra fields (`passthrough`) so a backend that adds a field does not break the apps,
 * and strict about the fields the apps rely on.
 */
import { z } from 'zod';

const uuid = z.string().min(8);
const money = z.number().int();
const iso = z.string().min(10);

export const RoleSchema = z.enum(['CUSTOMER', 'ARTISAN', 'VERIFIER', 'ADMIN']);
export const UrgencySchema = z.enum(['TODAY', 'THIS_WEEK', 'NOT_URGENT']);
export const JobStatusSchema = z.enum([
  'REQUESTED', 'ACCEPTED', 'IN_PROGRESS', 'PENDING_CONFIRMATION', 'COMPLETED', 'DISPUTED', 'CANCELLED',
]);
export const PaymentStatusSchema = z.enum(['PENDING', 'SUCCEEDED', 'FAILED', 'RELEASED', 'REFUNDED']);
export const PayoutStatusSchema = z.enum(['PENDING', 'RELEASED', 'HELD', 'PAID', 'FAILED']);

export const ErrorSchema = z.object({ detail: z.union([z.string(), z.array(z.unknown())]) }).passthrough();

export const TokenSchema = z.object({
  access_token: z.string().min(10),
  token_type: z.string(),
  user_id: uuid,
  role: RoleSchema,
}).passthrough();

export const SkillSchema = z.object({
  skill_id: uuid,
  skill_name: z.string(),
  description: z.string().nullable().optional(),
  safety_critical: z.boolean(),
}).passthrough();

export const ReputationSchema = z.object({
  artisan_id: uuid,
  reputation_score: z.number(),
  verified_reviews: z.number().int().nonnegative(),
  average_rating: z.number().nullable(),
  completed_jobs: z.number().int().nonnegative(),
}).passthrough();

export const ArtisanSchema = z.object({
  artisan_id: uuid,
  full_name: z.string(),
  location: z.string(),
  description: z.string().nullable(),
  availability_status: z.enum(['AVAILABLE', 'BUSY', 'UNAVAILABLE']),
  is_suspended: z.boolean(),
  identity_verified: z.boolean(),
  skills: z.array(z.object({
    skill_id: uuid, skill_name: z.string(), proficiency_level: z.string(),
    verification_status: z.string(), typical_price: money.nullable(),
  }).passthrough()),
  endorsement_count: z.number().int().nonnegative(),
  reputation: ReputationSchema,
}).passthrough();

export const ServiceRequestSchema = z.object({
  request_id: uuid,
  customer_id: uuid,
  skill_id: uuid,
  description: z.string(),
  location: z.string(),
  budget: money.nullable(),
  needs_inspection: z.boolean(),
  urgency: UrgencySchema,
  status: z.string(),
  created_at: iso,
}).passthrough();

export const MatchSchema = z.object({
  artisan_id: uuid,
  full_name: z.string(),
  location: z.string(),
  availability_status: z.string(),
  skill_verification_status: z.string(),
  typical_price: money.nullable(),
  verified_reviews: z.number().int().nonnegative(),
  reputation_score: z.number(),
  match_score: z.number(),
}).passthrough();

export const MatchesSchema = z.object({
  request_id: uuid,
  service_area_supported: z.boolean(),
  matches: z.array(MatchSchema),
  excluded_summary: z.record(z.number()),
  disclaimer: z.string(),
}).passthrough();

export const PaymentSchema = z.object({
  payment_id: uuid,
  job_id: uuid,
  payment_type: z.string(),
  amount: money,
  currency: z.string(),
  status: PaymentStatusSchema,
  created_at: iso,
}).passthrough();

export const JobEventSchema = z.object({ event_type: z.string(), created_at: iso }).passthrough();

export const JobSchema = z.object({
  job_id: uuid,
  request_id: uuid,
  artisan_id: uuid,
  customer_id: uuid,
  pricing_mode: z.string(),
  proposed_price: money.nullable(),
  proposed_by: z.string().nullable(),
  agreed_price: money.nullable(),
  artisan_agreed: z.boolean(),
  offer_expires_at: iso.nullable().optional(),
  status: JobStatusSchema,
  customer_confirmed: z.boolean(),
  artisan_confirmed: z.boolean(),
  created_at: iso,
  counterpart_phone: z.string().nullable(),
  events: z.array(JobEventSchema),
}).passthrough();

export const ChatMessageSchema = z.object({
  message_id: uuid,
  job_id: uuid,
  sender_role: z.enum(['CUSTOMER', 'ARTISAN']),
  body: z.string(),
  created_at: iso,
  proposed_price: money.nullable(),
  commission_if_agreed: money.nullable(),
  artisan_receives_if_agreed: money.nullable(),
}).passthrough();

export const ChatSendSchema = z.object({
  message: ChatMessageSchema,
  price_status: z.enum(['NONE', 'APPLIED', 'OUT_OF_RANGE', 'LOCKED', 'NOT_APPLICABLE', 'NOT_ARTISAN']),
}).passthrough();

export const PayoutSchema = z.object({
  payout_id: uuid,
  job_id: uuid,
  artisan_name: z.string(),
  amount: money,
  commission: money,
  status: PayoutStatusSchema,
  note: z.string().nullable(),
}).passthrough();

export const LedgerSchema = z.object({
  balances: z.record(money),
  balanced: z.boolean(),
  unbalanced_transactions: z.array(z.string()),
}).passthrough();

export const ReconciliationSchema = z.object({
  ledger: z.record(money),
  differences: z.record(money),
  mismatch: z.boolean(),
  status: z.enum(['OK', 'MISMATCH']),
  completed_jobs_without_payment: z.array(z.object({ artisan_name: z.string(), jobs: z.number().int() }).passthrough()),
}).passthrough();

export type Token = z.infer<typeof TokenSchema>;
export type Skill = z.infer<typeof SkillSchema>;
export type Artisan = z.infer<typeof ArtisanSchema>;
export type ServiceRequest = z.infer<typeof ServiceRequestSchema>;
export type Match = z.infer<typeof MatchSchema>;
export type Matches = z.infer<typeof MatchesSchema>;
export type Payment = z.infer<typeof PaymentSchema>;
export type Job = z.infer<typeof JobSchema>;
export type ChatMessage = z.infer<typeof ChatMessageSchema>;
export type ChatSend = z.infer<typeof ChatSendSchema>;
export type Payout = z.infer<typeof PayoutSchema>;
export type Ledger = z.infer<typeof LedgerSchema>;
export type Reconciliation = z.infer<typeof ReconciliationSchema>;
