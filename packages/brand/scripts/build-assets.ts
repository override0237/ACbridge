/**
 * Writes the static SVG assets of the brand into packages/brand/assets from the renderers (single source of truth).
 *   pnpm --filter @acbridge/brand build            write
 *   pnpm --filter @acbridge/brand build -- --check fail if the committed files are out of date
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderAdaptiveForeground, renderAppIcon, renderCanvas, renderMark, renderMotif, renderWordmark } from '../src/render';

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'assets');
const files: Record<string, string> = {
  'wordmark.svg': renderWordmark('light'),
  'wordmark-on-ink.svg': renderWordmark('on-ink'),
  'mark.svg': renderMark(),
  'app-icon.svg': renderAppIcon({ rounded: true }),
  'app-icon-square.svg': renderAppIcon({ rounded: false }),
  'adaptive-foreground.svg': renderAdaptiveForeground(),
  'splash.svg': renderCanvas(1284, 2778, 0.7),
  'social-card.svg': renderCanvas(1200, 630, 0.6),
  'motif-arch.svg': renderMotif('arch'),
  'motif-post.svg': renderMotif('post'),
  'motif-baseline.svg': renderMotif('baseline'),
  'motif-span.svg': renderMotif('span'),
};

if (process.argv.includes('--check')) {
  const stale = Object.entries(files).filter(([name, svg]) => !existsSync(join(out, name)) || readFileSync(join(out, name), 'utf8').trim() !== svg.trim());
  if (stale.length) {
    console.error('Brand SVG assets are out of date. Run: pnpm --filter @acbridge/brand build\n  ' + stale.map(([n]) => n).join('\n  '));
    process.exit(1);
  }
  console.log('Brand SVG assets are up to date.');
} else {
  mkdirSync(out, { recursive: true });
  for (const [name, svg] of Object.entries(files)) writeFileSync(join(out, name), svg + '\n');
  console.log(`Wrote ${Object.keys(files).length} SVG assets to ${out}`);
}
