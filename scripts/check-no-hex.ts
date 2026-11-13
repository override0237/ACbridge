/**
 * "No hex value may appear in a component": colours live ONLY in packages/tokens.
 * Scans the source of the apps and packages and fails on any #rgb / #rrggbb / #rrggbbaa literal outside the token package.
 * scripts/hex-allowlist.json lists LEGACY demo files that still contain colours until their screens are rebuilt on the new design
 * system; the list may only shrink.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const allow: string[] = JSON.parse(readFileSync(join(root, 'scripts', 'hex-allowlist.json'), 'utf8')).files;
const SKIP_DIRS = new Set(['node_modules', 'dist', 'generated', '.expo', 'database', 'coverage']);
const EXT = /\.(ts|tsx|css|js|jsx|mjs)$/;
const HEX = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/g;

function* walk(dir: string): Generator<string> {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* walk(path);
    else if (EXT.test(name)) yield path;
  }
}

const offenders: string[] = [];
for (const base of ['apps', 'packages']) {
  for (const file of walk(join(root, base))) {
    const rel = relative(root, file).split('\\').join('/');
    if (rel.startsWith('packages/tokens/')) continue;     // the one place colours may be defined
    if (/__tests__|\.test\.|\.spec\./.test(rel)) continue; // tests may assert on literal values
    if (allow.includes(rel)) continue;
    const hits = readFileSync(file, 'utf8').match(HEX);
    if (hits) offenders.push(`${rel}: ${[...new Set(hits)].join(', ')}`);
  }
}

if (offenders.length) {
  console.error('Hex colours found outside packages/tokens (use a token instead):\n  ' + offenders.join('\n  '));
  process.exit(1);
}
console.log(`No hex colours outside packages/tokens (${allow.length} legacy file(s) still allowed).`);
