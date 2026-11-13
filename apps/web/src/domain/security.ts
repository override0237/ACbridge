/**
 * Account credentials and the VOUCH SEAL ledger (pure).
 *
 * Vouch Seal rules, enforced in four independent layers (rules -> store action -> reducer -> ledger audit):
 *   1. One vouch per (voucher, artisan) pair, ever. A vouch can never be withdrawn or repeated.
 *   2. Every vouch is sealed: it gets a seal code and is chained to the previous vouch by hash,
 *      so deleting, editing or re-inserting a vouch breaks the chain and the operator panel shows it.
 *   3. The audit log records blocked duplicate attempts as security events.
 *   4. In API mode the backend's UNIQUE(artisan_id, endorser_id) constraint is the final guard.
 *
 * NOTE: hashes here are DEMO-GRADE (stretched FNV-1a). They make tampering visible in a demo; they are not
 * cryptographically secure. The real backend stores passwords with Argon2id.
 */
import type { Artisan, Vouch } from './types';

export const PASSWORD_MIN = 8; // same minimum as the backend (RegisterIn.password)
export const GENESIS_HASH = '0'.repeat(16);

/** 64-bit-looking salted, stretched hash (two FNV-1a lanes, 2000 rounds). Demo-grade only. */
export function hashSecret(secret: string, salt: string): string {
  const lane = (seed: number): string => {
    let h = seed >>> 0;
    for (const ch of `${salt}\u0000${secret}\u0000${salt}`) {
      h ^= ch.charCodeAt(0);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    for (let i = 0; i < 2000; i++) {
      h ^= i;
      h = Math.imul(h, 0x01000193) >>> 0;
      h = ((h << 13) | (h >>> 19)) >>> 0;
    }
    return h.toString(16).padStart(8, '0');
  };
  return lane(0x811c9dc5) + lane(0xdeadbeef);
}

// ---------------------------------------------------------------- credentials
export const normalizeUsername = (u: string): string => u.trim().toLowerCase();
export const isValidUsername = (u: string): boolean => /^[a-z0-9._-]{3,20}$/.test(normalizeUsername(u));

export type CredentialCheck =
  | { ok: true }
  | { ok: false; reason: 'username_format' | 'username_taken' | 'password_short' | 'password_mismatch' };

export function checkNewCredentials(username: string, password: string, confirm: string, artisans: Artisan[]): CredentialCheck {
  if (!isValidUsername(username)) return { ok: false, reason: 'username_format' };
  const n = normalizeUsername(username);
  if (artisans.some((a) => a.username === n)) return { ok: false, reason: 'username_taken' };
  if (password.length < PASSWORD_MIN) return { ok: false, reason: 'password_short' };
  if (password !== confirm) return { ok: false, reason: 'password_mismatch' };
  return { ok: true };
}

export function makeCredentials(username: string, password: string, salt: string): Pick<Artisan, 'username' | 'salt' | 'passwordHash'> {
  return { username: normalizeUsername(username), salt, passwordHash: hashSecret(password, salt) };
}

/** Returns the artisan when username AND password match, otherwise null (callers show one generic message). */
export function verifyLogin(artisans: Artisan[], username: string, password: string): Artisan | null {
  const a = artisans.find((x) => x.username === normalizeUsername(username));
  // Hash even for unknown users so both failures cost the same.
  const hash = hashSecret(password, a?.salt ?? 'no-such-user');
  return a && !a.rejected && hash === a.passwordHash ? a : null;
}

// ---------------------------------------------------------------- vouch seals
export const hasVouched = (voucherId: string, artisanId: string, vouches: Vouch[]): boolean =>
  vouches.some((v) => v.voucherId === voucherId && v.artisanId === artisanId);

export interface Seal { prevHash: string; hash: string; seal: string }

/** Seals a new vouch onto the end of the chain. */
export function sealVouch(prevHash: string, artisanId: string, voucherId: string, at: string): Seal {
  const hash = hashSecret(`${voucherId}>${artisanId}@${at}`, prevHash);
  return { prevHash, hash, seal: `VS-${hash.slice(0, 8).toUpperCase()}` };
}

export const lastHash = (vouches: Vouch[]): string => (vouches.length ? vouches[vouches.length - 1].hash : GENESIS_HASH);

export type LedgerCheck = { ok: true } | { ok: false; index: number; reason: 'broken_chain' | 'bad_hash' | 'duplicate_pair' };

/** Re-computes the whole chain. Any edited, removed, reordered or duplicated vouch is reported with its position. */
export function verifyLedger(vouches: Vouch[]): LedgerCheck {
  let prev = GENESIS_HASH;
  const pairs = new Set<string>();
  for (let i = 0; i < vouches.length; i++) {
    const v = vouches[i];
    if (v.prevHash !== prev) return { ok: false, index: i, reason: 'broken_chain' };
    if (sealVouch(prev, v.artisanId, v.voucherId, v.at).hash !== v.hash) return { ok: false, index: i, reason: 'bad_hash' };
    const key = `${v.voucherId}>${v.artisanId}`;
    if (pairs.has(key)) return { ok: false, index: i, reason: 'duplicate_pair' };
    pairs.add(key);
    prev = v.hash;
  }
  return { ok: true };
}
