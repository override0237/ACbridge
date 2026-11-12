// Turns the data you created in the browser demo into a SQLite database you can open.
//   1. In the demo: Operator (PIN 1234) -> "Export data" -> saves acbridge-demo-data.json
//   2. node --no-warnings database/build-demo-db.mjs path/to/acbridge-demo-data.json [output-folder]
// Output (in this folder): demo-from-browser.db, demo-from-browser.html (double-click to browse) and csv-from-browser/*.csv
// Uses Node's built-in SQLite (node:sqlite, Node 22.5+). Nothing to install. Password hashes are never exported.
import { DatabaseSync } from 'node:sqlite';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const file = process.argv[2];
const outDir = process.argv[3] ?? here;
mkdirSync(outDir, { recursive: true });
if (!file || !existsSync(file)) {
  console.error('usage: node --no-warnings database/build-demo-db.mjs <acbridge-demo-data.json>');
  process.exit(1);
}
const snap = JSON.parse(readFileSync(file, 'utf8'));
if (snap.format !== 'acbridge-demo-export' || typeof snap.tables !== 'object') {
  console.error('This is not an ACbridge demo export (use Operator -> Export data in the demo).');
  process.exit(1);
}

const dbPath = join(outDir, 'demo-from-browser.db');
rmSync(dbPath, { force: true });
const db = new DatabaseSync(dbPath);
const kind = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? 'INTEGER' : 'REAL') : typeof v === 'boolean' ? 'INTEGER' : 'TEXT');
const cell = (v) => (v === undefined || v === null ? null : typeof v === 'boolean' ? (v ? 1 : 0) : typeof v === 'object' ? JSON.stringify(v) : v);

for (const [name, rows] of Object.entries(snap.tables)) {
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  if (cols.length === 0) { db.exec(`CREATE TABLE "${name}" (id TEXT)`); continue; }
  const types = Object.fromEntries(cols.map((c) => [c, kind(rows.find((r) => r[c] != null)?.[c])]));
  db.exec(`CREATE TABLE "${name}" (${cols.map((c) => `"${c}" ${types[c]}`).join(', ')})`);
  const ins = db.prepare(`INSERT INTO "${name}" (${cols.map((c) => `"${c}"`).join(',')}) VALUES (${cols.map(() => '?').join(',')})`);
  for (const r of rows) ins.run(...cols.map((c) => cell(r[c])));
}

const has = (t) => db.prepare("SELECT 1 FROM sqlite_master WHERE name = ?").get(t);
if (has('requests') && has('jobs') && has('artisans')) db.exec(`
  CREATE VIEW v_requests AS SELECT r.id AS request_id, r.customerName, r.customerPhone, r.trade, r.urgency, r.description, r.at AS requested_at,
    j.id AS job_id, a.name AS artisan_name, j.status AS job_status, j.price, j.priceSource, j.commission, j.payout
  FROM requests r LEFT JOIN jobs j ON j.requestId = r.id LEFT JOIN artisans a ON a.id = j.artisanId;`);
if (has('payments') && has('jobs') && has('artisans')) db.exec(`
  CREATE VIEW v_payments AS SELECT p.id, p.reference, p.method, p.amount, p.status, a.name AS artisan_name, p.createdAt, p.settledAt
  FROM payments p LEFT JOIN jobs j ON j.id = p.jobId LEFT JOIN artisans a ON a.id = j.artisanId;`);
if (has('ledger')) db.exec(`
  CREATE VIEW v_ledger_balances AS SELECT account,
    CASE WHEN account = 'collection' THEN SUM(CASE WHEN direction='DEBIT' THEN amount ELSE -amount END)
         ELSE SUM(CASE WHEN direction='CREDIT' THEN amount ELSE -amount END) END AS balance FROM ledger GROUP BY account;`);

const csvDir = join(outDir, 'csv-from-browser');
rmSync(csvDir, { recursive: true, force: true });
mkdirSync(csvDir);
const esc = (v) => (v === null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
for (const { name } of db.prepare("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'").all()) {
  const rows = db.prepare(`SELECT * FROM "${name}"`).all();
  const cols = rows.length ? Object.keys(rows[0]) : [];
  writeFileSync(join(csvDir, `${name}.csv`), '﻿' + [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n'));
}
db.close();
console.log(`Wrote ${dbPath}`);
const out = spawnSync(process.execPath, ['--no-warnings', join(here, 'make-browser.mjs'), dbPath, join(outDir, 'demo-from-browser.html'), 'ACbridge demo data (from the browser)'], { stdio: 'inherit' });
process.exit(out.status ?? 0);
