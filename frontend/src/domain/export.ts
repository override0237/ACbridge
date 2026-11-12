/**
 * Export of everything the browser demo has stored, as flat tables, so it can be turned into a real SQLite database with
 * database/build-demo-db.mjs. Secrets never leave: password hashes and salts are NOT exported.
 */
import type { State } from '../store/reducer';

export type Row = Record<string, string | number | boolean | null>;
export interface Snapshot { format: 'acbridge-demo-export'; version: 1; exportedAt: string; tables: Record<string, Row[]> }

const json = (v: unknown): string => JSON.stringify(v ?? {});

export function exportSnapshot(s: State, now: Date = new Date()): Snapshot {
  const artisans: Row[] = s.artisans.map((a) => ({
    id: a.id, name: a.name, username: a.username, phone: a.phone, trade: a.trade, neighbourhood: a.neighbourhood, description: a.description,
    seedAccount: a.isSeed, seedVerified: a.seedVerified, operatorApproved: a.operatorApproved ?? false, rejected: a.rejected ?? false,
    baseRating: a.baseRating, baseJobs: a.baseJobs, priceMin: a.priceMin, priceMax: a.priceMax, avgResponseMin: a.avgResponseMin,
    backendId: a.remoteId ?? null,
  }));
  const customers = new Map<string, Row>();
  for (const r of s.requests) customers.set(r.customerPhone, { phone: r.customerPhone, name: r.customerName });
  return {
    format: 'acbridge-demo-export', version: 1, exportedAt: now.toISOString(),
    tables: {
      artisans,
      customers: [...customers.values()],
      vouches: s.vouches.map((v) => ({ ...v })),
      requests: s.requests.map((r) => ({ ...r })),
      jobs: s.jobs.map((j) => ({ ...j })), // codeHash is a one-way hash of the job code
      chats: s.chats.map((m) => ({ id: m.id, jobId: m.jobId, from: m.from, text: m.text, key: m.key ?? null, params: json(m.params), price: m.price ?? null, at: m.at })),
      payments: s.payments.map((p) => ({ ...p })),
      payouts: s.payouts.map((p) => ({ ...p })),
      ledger: s.ledger.map((l) => ({ ...l })),
      ratings: s.ratings.map((r) => ({ ...r })),
      sms: s.sms.map((m) => ({ id: m.id, to: m.to, key: m.key, params: json(m.params), at: m.at })),
      audit: s.audit.map((e) => ({ id: e.id, kind: e.kind, params: json(e.params), at: e.at })),
    },
  };
}

/** Triggers a download of the snapshot as acbridge-demo-data.json (browser only). */
export function downloadSnapshot(s: State): void {
  const blob = new Blob([JSON.stringify(exportSnapshot(s), null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'acbridge-demo-data.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
