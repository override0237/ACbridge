import type { Artisan, Customer, Operator } from '../domain/types';
import { NEIGHBOURHOOD, OPERATOR_PIN } from '../config';

// SIMULATED demo people. The first six names/phones mirror backend/app/seed.py so both sides line up in API mode.
const base = { neighbourhood: NEIGHBOURHOOD, isSeed: true } as const;

export const SEED_ARTISANS: Artisan[] = [
  { ...base, id: 'seed-1', name: 'Grace', phone: '+237690000015', trade: 'plumbing', description: 'Plumber, 12 years', baseRating: 4.8, baseJobs: 24, avgResponseMin: 8, priceMin: 3000, priceMax: 8000, seedVerified: true },
  { ...base, id: 'seed-2', name: 'Paul', phone: '+237690000011', trade: 'electrical', description: 'Wiring and sockets', baseRating: 4.6, baseJobs: 31, avgResponseMin: 15, priceMin: 5000, priceMax: 12000, seedVerified: true },
  { ...base, id: 'seed-3', name: 'Esther', phone: '+237690000013', trade: 'electrical', description: 'Fault finding', baseRating: 4.3, baseJobs: 12, avgResponseMin: 12, priceMin: 4000, priceMax: 9000, seedVerified: true },
  { ...base, id: 'seed-4', name: 'Peter', phone: '+237690000014', trade: 'electrical', description: 'Breakers and lighting', baseRating: 3.9, baseJobs: 9, avgResponseMin: 25, priceMin: 3500, priceMax: 8000, seedVerified: true },
  // The pending candidate: not verified, never shown in match results until the operator approves.
  { ...base, id: 'seed-5', name: 'Samuel', phone: '+237690000012', trade: 'electrical', description: 'New electrician, waiting for review', baseRating: 0, baseJobs: 0, avgResponseMin: 30, priceMin: 3000, priceMax: 7000, seedVerified: false },
  { ...base, id: 'seed-6', name: 'Rose', phone: '+237690000016', trade: 'tailoring', description: 'Dresses and repairs', baseRating: 4.7, baseJobs: 40, avgResponseMin: 20, priceMin: 2000, priceMax: 15000, seedVerified: true },
  { ...base, id: 'seed-7', name: 'Daniel', phone: '+237690000017', trade: 'carpentry', description: 'Doors, tables, roofs', baseRating: 4.5, baseJobs: 18, avgResponseMin: 18, priceMin: 5000, priceMax: 20000, seedVerified: true },
  { ...base, id: 'seed-8', name: 'Fabrice', phone: '+237690000018', trade: 'mechanics', description: 'Cars and motorbikes', baseRating: 4.2, baseJobs: 22, avgResponseMin: 30, priceMin: 3000, priceMax: 25000, seedVerified: true },
  { ...base, id: 'seed-9', name: 'Blaise', phone: '+237690000019', trade: 'plumbing', description: 'Leaks and drains', baseRating: 4.1, baseJobs: 10, avgResponseMin: 14, priceMin: 2500, priceMax: 7000, seedVerified: true },
];

export const SEED_CUSTOMER: Customer = { name: 'Mary', phone: '+237690000030' };
export const SEED_OPERATOR: Operator = { name: 'Operator', pin: OPERATOR_PIN };

/** The two seeded verified artisans behind the "simulate vouch" buttons. */
export const SEED_VOUCHERS = ['seed-1', 'seed-2'] as const;
