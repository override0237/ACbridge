/**
 * Fails (exit 1) if any foreground/background pair in packages/tokens is below its required WCAG contrast ratio.
 *   pnpm contrast               print the table and fail on any miss
 *   pnpm contrast -- --write    also (re)write the results table in docs/ACCESSIBILITY.md
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkAllPairs, colors } from '../packages/tokens/src/index';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const results = checkAllPairs();
const failed = results.filter((r) => !r.pass);

const line = (r: (typeof results)[number]): string =>
  `${r.pass ? 'PASS' : 'FAIL'}  ${r.mode.padEnd(5)}  ${String(r.fg).padEnd(17)} on ${String(r.bg).padEnd(14)} ${r.ratio.toFixed(2).padStart(5)}:1  (needs ${r.min}:1)  ${r.fgHex} / ${r.bgHex}`;
console.log(results.map(line).join('\n'));

// The spec's explicit rule: blue text on dark surfaces must use accent-text-on-dark, never the accent token itself.
if (colors.dark.accentText === colors.dark.accent) {
  console.error('\nFAIL: in dark mode accentText must be accent-text-on-dark, not the accent colour (it is below 4.5:1 for text).');
  failed.push(results[0]);
}

console.log(`\n${results.length - failed.length}/${results.length} pairs pass.`);

if (process.argv.includes('--write')) {
  const table = [
    '| Mode | Foreground | Background | Ratio | Needs | Use | Result |',
    '|---|---|---|---|---|---|---|',
    ...results.map((r) => `| ${r.mode} | \`${r.fg}\` ${r.fgHex} | \`${r.bg}\` ${r.bgHex} | ${r.ratio.toFixed(2)}:1 | ${r.min}:1 | ${r.why} | ${r.pass ? 'pass' : '**FAIL**'} |`),
  ].join('\n');
  const file = join(root, 'docs', 'ACCESSIBILITY.md');
  const text = readFileSync(file, 'utf8');
  const start = '<!-- contrast:start -->';
  const end = '<!-- contrast:end -->';
  const a = text.indexOf(start);
  const b = text.indexOf(end);
  if (a < 0 || b < 0) throw new Error('docs/ACCESSIBILITY.md is missing the contrast markers');
  writeFileSync(file, `${text.slice(0, a + start.length)}\n\n${table}\n\n${text.slice(b)}`);
  console.log('Updated docs/ACCESSIBILITY.md');
}

process.exit(failed.length ? 1 : 0);
