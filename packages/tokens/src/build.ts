/**
 * Generates, from tokens.ts:
 *   generated/tokens.css  CSS custom properties for the web (light, dark by system, and a manual data-theme override)
 *   generated/theme.ts    a plain theme object for React Native
 *
 *   tsx packages/tokens/src/build.ts            writes the files
 *   tsx packages/tokens/src/build.ts --check    fails if the committed files are out of date
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderCss, renderTheme } from './render';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..', 'generated');

const files: [string, string][] = [
  [join(out, 'tokens.css'), renderCss()],
  [join(out, 'theme.ts'), renderTheme()],
];

if (process.argv.includes('--check')) {
  const stale = files.filter(([path, content]) => !existsSync(path) || readFileSync(path, 'utf8').replace(/\r\n/g, '\n') !== content);
  if (stale.length) {
    console.error('Generated token files are out of date. Run: pnpm tokens:build\n  ' + stale.map(([p]) => p).join('\n  '));
    process.exit(1);
  }
  console.log('Generated token files are up to date.');
} else {
  mkdirSync(out, { recursive: true });
  for (const [path, content] of files) writeFileSync(path, content);
  console.log(`Wrote ${files.map(([p]) => p).join(', ')}`);
}
