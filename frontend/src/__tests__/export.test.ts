// @ts-nocheck  (Node-only test: it runs the database scripts; the app itself has no Node typings)
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { exportSnapshot } from '../domain/export';
import { generateJobCode } from '../domain/rules';
import { initialState, reducer, type State } from '../store/reducer';

const { DatabaseSync } = createRequire(import.meta.url)('node:sqlite'); // Vite cannot bundle node:sqlite, so load it at run time
const at = '2026-01-01T00:00:00Z';
const ids = (n: number) => Array.from({ length: n }, (_, i) => `i${i}${Math.random()}`);

function journey(): State {
  let s = initialState();
  s = reducer(s, { type: 'request', request: { id: 'rq', customerPhone: '+237690000030', customerName: 'Mary', trade: 'plumbing', neighbourhood: 'Neighbourhood A', urgency: 'today', description: 'Leaking tap', at } });
  s = reducer(s, { type: 'choose', jobId: 'job', requestId: 'rq', artisanId: 'seed-1', price: 6000, at, ids: ids(1) });
  s = reducer(s, { type: 'chat', id: 'm1', sysId: 's1', jobId: 'job', from: 'customer', text: 'Final price: 6000 FCFA', at, ids: ids(2) });
  s = reducer(s, { type: 'answer', jobId: 'job', accept: true, at, ids: ids(3) });
  s = reducer(s, { type: 'payStart', id: 'p1', jobId: 'job', method: 'mtn', phone: '+237670123456', ref: 'SIM-1', at, ids: ids(1) });
  return reducer(s, { type: 'paySettle', id: 'p1', ok: true, code: generateJobCode(), at, ids: ids(4) });
}

describe('exporting the demo data as a database', () => {
  it('never exports password hashes or salts', () => {
    const text = JSON.stringify(exportSnapshot(journey()));
    expect(text).not.toMatch(/passwordHash|"salt"/);
    expect(text).toContain('"username":"grace"');         // accounts are exported, secrets are not
  });

  it('covers accounts, requests, jobs, chat, payments, payouts and the ledger', () => {
    const t = exportSnapshot(journey()).tables;
    expect(t.artisans).toHaveLength(9);
    expect(t.requests).toHaveLength(1);
    expect(t.customers).toEqual([{ phone: '+237690000030', name: 'Mary' }]);
    expect(t.payments[0]).toMatchObject({ amount: 6000, status: 'succeeded' });
    expect(t.payouts[0]).toMatchObject({ amount: 5700, commission: 300, status: 'PENDING' });
    expect(t.ledger).toHaveLength(3);
  });

  it('becomes a real SQLite database through database/build-demo-db.mjs (and a browsable HTML page)', () => {
    const dir = mkdtempSync(join(tmpdir(), 'acbridge-db-'));
    const file = join(dir, 'export.json');
    writeFileSync(file, JSON.stringify(exportSnapshot(journey())));
    const run = spawnSync(process.execPath, ['--no-warnings', 'database/build-demo-db.mjs', file, dir], { encoding: 'utf8' });
    expect(run.status, run.stderr).toBe(0);

    const db = new DatabaseSync(join(dir, 'demo-from-browser.db'), { readOnly: true });
    expect(db.prepare('SELECT COUNT(*) AS n FROM artisans').get()).toEqual({ n: 9 });
    expect(db.prepare("SELECT customerName, trade, artisan_name, price FROM v_requests").get()).toMatchObject({ customerName: 'Mary', artisan_name: 'Grace', price: 6000 });
    const balances = Object.fromEntries((db.prepare('SELECT account, balance FROM v_ledger_balances').all() as { account: string; balance: number }[]).map((r) => [r.account, r.balance]));
    expect(balances).toMatchObject({ collection: 6000, platform_revenue: 300, artisan_pending: 5700 });
    expect(db.prepare('SELECT status FROM v_payments').get()).toEqual({ status: 'succeeded' });
    db.close();
    const html = readFileSync(join(dir, 'demo-from-browser.html'), 'utf8');
    expect(html).toContain('Leaking tap');
    expect(html).not.toMatch(/passwordHash/);
  });

  it('rejects a file that is not an ACbridge export', () => {
    const dir = mkdtempSync(join(tmpdir(), 'acbridge-db-'));
    const file = join(dir, 'x.json');
    writeFileSync(file, JSON.stringify({ hello: 'world' }));
    const run = spawnSync(process.execPath, ['--no-warnings', 'database/build-demo-db.mjs', file, dir], { encoding: 'utf8' });
    expect(run.status).toBe(1);
    expect(run.stderr).toContain('not an ACbridge demo export');
  });
});
