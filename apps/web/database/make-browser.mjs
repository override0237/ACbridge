// Turns a SQLite file into ONE self-contained HTML page you can open by double-clicking (tabs per table, search, row counts).
//   node --no-warnings database/make-browser.mjs <database.db> <output.html> "<title>"
// Uses Node's built-in SQLite (node:sqlite, Node 22.5+). Nothing to install. The database is opened READ-ONLY.
import { DatabaseSync } from 'node:sqlite';
import { writeFileSync } from 'node:fs';

const [dbPath, outPath, title = 'ACbridge database'] = process.argv.slice(2);
if (!dbPath || !outPath) {
  console.error('usage: node --no-warnings database/make-browser.mjs <database.db> <output.html> "<title>"');
  process.exit(1);
}

const DESCRIPTIONS = {
  // backend database
  users: 'Every account (customers, artisans, verifiers, administrators). Phone is the login; only a password HASH is stored.',
  artisan_profiles: 'The public profile of each artisan: name, area, availability.',
  skills: 'The catalogue of trades (Plumbing, Electrical Repair, ...).',
  artisan_skills: 'Which trades each artisan offers, their level, typical price and whether the skill is verified.',
  endorsements: 'Vouches: one row per person who vouched for an artisan (unique per pair).',
  verification_checks: 'Verification requests reviewed by a verifier (SIMULATED verification).',
  service_requests: 'What customers asked for: trade, place, budget, urgency, status.',
  jobs: 'A customer request given to one artisan: prices, status, confirmations.',
  job_events: 'Append-only history of everything that happened to a job.',
  job_messages: 'The chat between customer and artisan ("connect flexibly"). Phone numbers are hidden.',
  payments: 'Payments through ACbridge (sandbox): customer escrow payments and artisan fees.',
  payouts: "The artisan's share of a paid job: PENDING, HELD, PAID.",
  ledger_entries: 'Double-entry ledger lines. For every tx_key the DEBITS equal the CREDITS.',
  audit_log: 'Money events and operator actions, stored as a hash of the payload.',
  webhook_events: 'Provider callbacks already processed (replay protection).',
  reviews: 'Ratings left by customers for completed jobs.',
  hardship_claims: 'Refund claims after a death or serious illness (document-backed).',
  v_accounts: 'VIEW: all accounts with the artisan name where there is one.',
  v_artisans: 'VIEW: artisans with their trade, price and verification.',
  v_customer_requests: 'VIEW: customer requests with the chosen artisan and job status.',
  v_payments: 'VIEW: payments with artisan and masked-able payer phone.',
  v_payouts: 'VIEW: payouts per artisan.',
  v_ledger_balances: 'VIEW: balance of each ledger account.',
  v_chat: 'VIEW: chat messages in time order.',
  // browser demo export
  artisans: 'Registered artisans (usernames; password hashes are NOT exported).',
  vouches: 'Sealed vouches: seal code and hash chain.',
  requests: 'Customer requests.',
  chats: 'Chat messages and system lines.',
  ledger: 'Double-entry ledger lines.',
  ratings: 'Ratings.',
  sms: 'Every simulated SMS, in order.',
  audit: 'Operator audit log.',
  v_requests: 'VIEW: requests with job and artisan.',
};

const db = new DatabaseSync(dbPath, { readOnly: true });
const names = db.prepare("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name").all();
const LIMIT = 5000;
const data = names.map(({ name, type }) => {
  const total = db.prepare(`SELECT COUNT(*) AS c FROM "${name}"`).get().c;
  const stmt = db.prepare(`SELECT * FROM "${name}" LIMIT ${LIMIT}`);
  const rows = stmt.all();
  const columns = rows.length ? Object.keys(rows[0]) : stmt.columns().map((c) => c.name);
  return {
    name, type, total, columns, description: DESCRIPTIONS[name] ?? '',
    rows: rows.map((r) => columns.map((c) => {
      const v = r[c];
      if (/password/i.test(c) && typeof v === 'string') return `${v.slice(0, 14)}… (hash)`;
      return v === null ? null : typeof v === 'bigint' ? Number(v) : v;
    })),
  };
});

const json = JSON.stringify({ title, generated: new Date().toISOString(), tables: data }).replace(/</g, '\\u003c');
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title.replace(/[<&]/g, '')}</title>
<style>
  :root{--bg:#f6f7f9;--ink:#14202b;--muted:#4a5a68;--line:#c9d2da;--brand:#0b5d9e}
  @media (prefers-color-scheme: dark){:root{--bg:#10161c;--ink:#e8eef3;--muted:#9fb0bf;--line:#2c3a46;--brand:#6db3f2}}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,Segoe UI,sans-serif}
  header{padding:12px 16px;border-bottom:1px solid var(--line)} h1{font-size:1.2rem;margin:0} .muted{color:var(--muted)}
  main{display:grid;grid-template-columns:250px 1fr;min-height:calc(100vh - 70px)} nav{border-right:1px solid var(--line);padding:8px;overflow:auto;max-height:calc(100vh - 70px)}
  nav button{display:flex;justify-content:space-between;gap:8px;width:100%;text-align:left;padding:8px 10px;margin:2px 0;border:0;border-radius:8px;background:none;color:inherit;font:inherit;cursor:pointer}
  nav button[aria-current=true]{background:var(--brand);color:#fff} nav small{opacity:.8} nav h2{font-size:.8rem;text-transform:uppercase;color:var(--muted);margin:12px 8px 4px}
  section{padding:12px 16px;min-width:0} .tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0}
  input{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:transparent;color:inherit;font:inherit;min-width:240px}
  .wrap{overflow:auto;max-height:calc(100vh - 230px);border:1px solid var(--line);border-radius:8px}
  table{border-collapse:collapse;width:100%;font-size:.9rem} th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;max-width:420px;overflow:hidden;text-overflow:ellipsis}
  th{position:sticky;top:0;background:var(--bg);z-index:1} td.null{color:var(--muted);font-style:italic}
  @media (max-width:760px){main{grid-template-columns:1fr} nav{max-height:none;border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header><h1>${title.replace(/[<&]/g, '')}</h1><div class="muted" id="meta"></div></header>
<main><nav id="nav" aria-label="Tables"></nav><section><h2 id="tname"></h2><p class="muted" id="tdesc"></p>
<div class="tools"><input id="q" type="search" placeholder="Search this table" aria-label="Search this table"><span class="muted" id="count"></span></div>
<div class="wrap"><table><thead id="head"></thead><tbody id="body"></tbody></table></div></section></main>
<script id="data" type="application/json">${json}</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
document.getElementById('meta').textContent = 'Read-only snapshot generated ' + D.generated.slice(0,19).replace('T',' ') + ' UTC. Simulated data: no real people or money.';
const nav = document.getElementById('nav'); let current = null;
function render(t){ current = t;
  [...nav.querySelectorAll('button')].forEach(b => b.setAttribute('aria-current', b.dataset.n === t.name));
  document.getElementById('tname').textContent = t.name + (t.type === 'view' ? ' (view)' : '');
  document.getElementById('tdesc').textContent = t.description;
  document.getElementById('head').innerHTML = '<tr>' + t.columns.map(c => '<th></th>').join('') + '</tr>';
  [...document.getElementById('head').querySelectorAll('th')].forEach((th,i) => th.textContent = t.columns[i]);
  filter(); }
function filter(){ const q = document.getElementById('q').value.toLowerCase(); const body = document.getElementById('body'); body.textContent = '';
  let shown = 0; for (const r of current.rows) { if (q && !r.some(v => String(v ?? '').toLowerCase().includes(q))) continue;
    const tr = document.createElement('tr'); for (const v of r) { const td = document.createElement('td'); if (v === null) { td.className = 'null'; td.textContent = 'null'; } else { td.textContent = String(v); td.title = String(v); } tr.appendChild(td); }
    body.appendChild(tr); shown++; }
  document.getElementById('count').textContent = shown + ' of ' + current.total + ' rows' + (current.total > current.rows.length ? ' (first ' + current.rows.length + ' loaded)' : ''); }
let lastType = null;
for (const t of D.tables) { if (t.type !== lastType) { const h = document.createElement('h2'); h.textContent = t.type === 'table' ? 'Tables' : 'Views'; nav.appendChild(h); lastType = t.type; }
  const b = document.createElement('button'); b.dataset.n = t.name; b.innerHTML = '<span></span><small></small>'; b.children[0].textContent = t.name; b.children[1].textContent = t.total; b.onclick = () => render(t); nav.appendChild(b); }
document.getElementById('q').oninput = filter; if (D.tables.length) render(D.tables.find(t => t.name === 'users' || t.name === 'artisans') ?? D.tables[0]);
</script></body></html>
`;
writeFileSync(outPath, html);
console.log(`${outPath}: ${data.length} tables/views, ${data.reduce((n, t) => n + t.total, 0)} rows`);
