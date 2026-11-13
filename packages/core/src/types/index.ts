/** Types and enums shared by the web and mobile apps (and mirrored from the backend's API). */
export type Lang = 'fr' | 'en';
export type Role = 'CUSTOMER' | 'ARTISAN' | 'VERIFIER' | 'ADMIN';
export type Urgency = 'TODAY' | 'THIS_WEEK' | 'NOT_URGENT';
export type JobStatus =
  | 'REQUESTED' | 'ACCEPTED' | 'IN_PROGRESS' | 'PENDING_CONFIRMATION' | 'COMPLETED' | 'DISPUTED' | 'CANCELLED';
export type PaymentStatus = 'PENDING' | 'SUCCEEDED' | 'FAILED' | 'RELEASED' | 'REFUNDED';
export type PayoutStatus = 'PENDING' | 'RELEASED' | 'HELD' | 'PAID' | 'FAILED';
export type ThemeChoice = 'system' | 'light' | 'dark';
