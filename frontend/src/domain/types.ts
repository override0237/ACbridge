export type Lang = 'fr' | 'en';
export type Urgency = 'today' | 'week' | 'later';
export type JobStatus = 'REQUESTED' | 'ACCEPTED' | 'DECLINED' | 'EXPIRED' | 'COMPLETED';

export interface Artisan {
  id: string;
  name: string;
  phone: string;
  /** Login name (lower case, unique) and salted password hash. The password itself is never stored. */
  username: string;
  salt: string;
  passwordHash: string;
  /** Catalogue key (see domain/trades.ts) or normalised free text. */
  trade: string;
  neighbourhood: string;
  description: string;
  /** Seed history: average rating over `baseJobs` earlier completed jobs (0 jobs => no history). */
  baseRating: number;
  baseJobs: number;
  avgResponseMin: number;
  priceMin: number;
  priceMax: number;
  /** Seeded as already verified (by simulated community + verifier). */
  seedVerified: boolean;
  operatorApproved?: boolean;
  rejected?: boolean;
  isSeed: boolean;
  /** Backend artisan_id when API mode created or linked this artisan. */
  remoteId?: string;
}

export interface Vouch {
  id: string;
  artisanId: string;
  voucherId: string;
  voucherPhone: string;
  /** Voucher attests they completed a job with this artisan. */
  workedTogether: boolean;
  at: string;
  /** Vouch Seal: human-readable seal code, previous link and this link of the tamper-evident chain. */
  seal: string;
  prevHash: string;
  hash: string;
}

export interface ServiceRequest {
  id: string;
  customerPhone: string;
  customerName: string;
  trade: string;
  neighbourhood: string;
  urgency: Urgency;
  description: string;
  at: string;
  remoteId?: string;
}

export interface Job {
  id: string;
  requestId: string;
  artisanId: string;
  customerPhone: string;
  status: JobStatus;
  codeHash: string | null;
  codeUsed: boolean;
  /** Simulated agreed price (FCFA) and, once completed, the commission taken from the artisan. */
  price: number;
  /** 'estimate' until the customer writes an amount in the chat ('chat'). Locked once the artisan says YES. */
  priceSource: 'estimate' | 'chat';
  commissionRate?: number;
  commission?: number;
  payout?: number;
  createdAt: string;
  acceptedAt?: string;
  completedAt?: string;
  remoteId?: string;
}

export interface Rating {
  id: string;
  jobId: string;
  artisanId: string;
  score: number;
  comment: string;
  at: string;
}

export interface SmsMessage {
  id: string;
  to: string;
  key: string; // i18n key, so the log re-renders in the selected language
  params: Record<string, string | number>;
  at: string;
}

export type AuditKind = 'verification' | 'job_accepted' | 'job_completed' | 'transaction' | 'price' | 'expiry' | 'payment' | 'payout' | 'rating' | 'trust' | 'security';
export interface AuditEntry {
  id: string;
  kind: AuditKind;
  params: Record<string, string | number>;
  at: string;
}

export interface PaymentRec {
  id: string;
  jobId: string;
  method: 'mtn' | 'orange';
  /** Customer's mobile-money number (kept only to mask it in operator views). */
  phone: string;
  /** Always copied from the job when the payment starts, never typed by the customer. */
  amount: number;
  status: 'pending' | 'succeeded' | 'failed';
  reference: string;
  createdAt: string;
  settledAt?: string;
}

export interface LedgerLine {
  id: string;
  txKey: string;
  account: 'collection' | 'platform_revenue' | 'artisan_pending' | 'artisan_paid' | 'refund_payable';
  direction: 'DEBIT' | 'CREDIT';
  amount: number;
  at: string;
}

export interface Payout {
  id: string;
  jobId: string;
  artisanId: string;
  paymentId: string;
  /** What the artisan receives (price minus commission). */
  amount: number;
  commission: number;
  status: 'PENDING' | 'HELD' | 'PAID' | 'FAILED';
  note?: string;
  createdAt: string;
  paidAt?: string;
}

export interface ChatMessage {
  id: string;
  jobId: string;
  from: 'customer' | 'artisan' | 'system';
  /** Plain text for people (already contact-masked). System messages use key + params so they translate. */
  text: string;
  key?: string;
  params?: Record<string, string | number>;
  /** Set when this customer message became the job price. */
  price?: number;
  at: string;
}

export interface Customer { name: string; phone: string }
export interface Operator { name: string; pin: string }
