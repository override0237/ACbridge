/**
 * Copies the brand assets the web app needs into public/ and writes the web app manifest, from the single source
 * (packages/brand/assets, colours from @acbridge/tokens). Runs before dev and build; the output is not committed.
 */
import { copyFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { colors } from '@acbridge/tokens';

const here = dirname(fileURLToPath(import.meta.url));
const assets = join(here, '..', '..', '..', 'packages', 'brand', 'assets');
const pub = join(here, '..', 'public');
const brand = join(pub, 'brand');
mkdirSync(brand, { recursive: true });

const copies: [string, string][] = [
  ['app-icon.svg', 'favicon.svg'],
  ['favicon.ico', 'favicon.ico'],
  ['png/apple-touch-icon-180.png', 'apple-touch-icon.png'],
  ['png/icon-192.png', 'icon-192.png'],
  ['png/icon-512.png', 'icon-512.png'],
  ['png/icon-maskable-512.png', 'icon-maskable-512.png'],
  ['png/social-card-1200x630.png', 'social-card.png'],
  ['wordmark.svg', 'wordmark.svg'],
  ['wordmark-on-ink.svg', 'wordmark-on-ink.svg'],
  ['mark.svg', 'mark.svg'],
];
for (const [from, to] of copies) copyFileSync(join(assets, from), join(brand, to));

const manifest = {
  name: 'ACbridge',
  short_name: 'ACbridge',
  description: 'Trusted artisans near you',
  start_url: '/',
  display: 'standalone',
  background_color: colors.light.ink,
  theme_color: colors.light.ink,
  lang: 'fr',
  icons: [
    { src: '/brand/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
    { src: '/brand/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
    { src: '/brand/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
  ],
};
writeFileSync(join(pub, 'manifest.webmanifest'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Synced ${copies.length} brand files and manifest.webmanifest into apps/web/public`);
