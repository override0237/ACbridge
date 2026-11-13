/**
 * Security sweep of BUILT client output: no provider keys, webhook secrets, operator PIN hashes, database URLs, tokens or
 * private keys may reach a client bundle.
 *   pnpm check:bundles [folder-or-file ...]      (default: apps/web/dist and apps/web/acbridge.html)
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const targets = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const roots = (targets.length ? targets : ['apps/web/dist', 'apps/web/acbridge.html']).map((t) => join(root, t));

const PATTERNS: [string, RegExp][] = [
  ['webhook secret', /WEBHOOK_SECRET|webhook[_-]?secret/i],
  ['JWT secret', /JWT_SECRET/],
  ['database URL', /postgres(?:ql)?(?:\+\w+)?:\/\/[^\s"']+/i],
  ['provider key', /(?:MTN|ORANGE)[_-]?(?:MOMO)?[_-]?(?:API|SUBSCRIPTION|SECRET|KEY)[\w-]*/i],
  ['private key block', /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/],
  ['bearer token literal', /Bearer\s+[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}/],
  ['JWT literal', /eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/],
  ['operator PIN hash', /operator[_-]?pin[_-]?hash/i],
  ['generic secret assignment', /(?:secret|api[_-]?key|password)["']?\s*[:=]\s*["'][A-Za-z0-9_\-+/=]{16,}["']/i],
];

function* files(path: string): Generator<string> {
  if (!existsSync(path)) return;
  if (statSync(path).isFile()) { yield path; return; }
  for (const name of readdirSync(path)) yield* files(join(path, name));
}

let scanned = 0;
const findings: string[] = [];
for (const r of roots) {
  for (const f of files(r)) {
    if (!/\.(js|mjs|css|html|json|map|txt)$/.test(f)) continue;
    scanned++;
    const text = readFileSync(f, 'utf8');
    for (const [name, re] of PATTERNS) {
      const m = re.exec(text);
      if (m) findings.push(`${relative(root, f)}: ${name} -> ${m[0].slice(0, 60)}`);
    }
  }
}
if (scanned === 0) { console.error('No built files found to scan. Build the apps first.'); process.exit(1); }
if (findings.length) { console.error('Secrets or secret-like values found in built output:\n  ' + findings.join('\n  ')); process.exit(1); }
console.log(`Scanned ${scanned} built file(s): no secrets, provider keys or tokens found.`);
