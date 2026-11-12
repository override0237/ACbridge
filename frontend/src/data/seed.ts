import type { Artisan, Customer, Operator } from '../domain/types';
import { NEIGHBOURHOOD, OPERATOR_PIN, TRADE } from '../config';

// SIMULATED demo people. Names and phones mirror backend/app/seed.py so both sides line up in API mode.
const base = { trade: TRADE, neighbourhood: NEIGHBOURHOOD, isSeed: true } as const;

export const SEED_ARTISANS: Artisan[] = [
  { ...base, id: 'seed-1', name: 'Grace', phone: '+237690000015', description: 'Plumber, 12 years', baseRating: 4.8, baseJobs: 24, avgResponseMin: 8, priceMin: 3000, priceMax: 8000, seedVerified: true },
  { ...base, id: 'seed-2', name: 'Paul', phone: '+237690000011', description: 'Pipes and taps', baseRating: 4.6, baseJobs: 31, avgResponseMin: 15, priceMin: 3500, priceMax: 9000, seedVerified: true },
  { ...base, id: 'seed-3', name: 'Esther', phone: '+237690000013', description: 'Water heaters and drains', baseRating: 4.3, baseJobs: 12, avgResponseMin: 12, priceMin: 2500, priceMax: 7000, seedVerified: true },
  { ...base, id: 'seed-4', name: 'Peter', phone: '+237690000014', description: 'Leaks and repairs', baseRating: 3.9, baseJobs: 9, avgResponseMin: 25, priceMin: 2000, priceMax: 6000, seedVerified: true },
  // The pending candidate: not verified, never shown in match results until the operator approves.
  { ...base, id: 'seed-5', name: 'Samuel', phone: '+237690000012', description: 'New plumber, waiting for review', baseRating: 0, baseJobs: 0, avgResponseMin: 30, priceMin: 2500, priceMax: 6500, seedVerified: false },
];

export const SEED_CUSTOMER: Customer = { name: 'Mary', phone: '+237690000030' };
export const SEED_OPERATOR: Operator = { name: 'Operator', pin: OPERATOR_PIN };

/** The two seeded verified artisans behind the "simulate vouch" buttons. */
export const SEED_VOUCHERS = ['seed-1', 'seed-2'] as const;
