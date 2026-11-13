// Rasterises the brand SVGs into PNG (and a PNG-in-ICO favicon) using a locally installed Edge or Chrome in headless mode.
// Run it on a developer machine after changing the logo; the PNGs are committed, so CI does not need a browser.
//   node packages/brand/scripts/build-png.mjs
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const assets = resolve(here, '..', 'assets');
const out = join(assets, 'png');
mkdirSync(out, { recursive: true });

const candidates = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
];
const browser = candidates.find(existsSync);
if (!browser) { console.error('No Edge or Chrome found. Install one to regenerate PNGs.'); process.exit(1); }

/** [source svg, output png, width, height, transparent background?] */
const targets = [
  ['app-icon.svg', 'favicon-32.png', 32, 32, true],
  ['app-icon.svg', 'favicon-48.png', 48, 48, true],
  ['app-icon-square.svg', 'apple-touch-icon-180.png', 180, 180, false],
  ['app-icon.svg', 'icon-192.png', 192, 192, true],
  ['app-icon.svg', 'icon-512.png', 512, 512, true],
  ['app-icon-square.svg', 'icon-maskable-512.png', 512, 512, false],
  ['app-icon-square.svg', 'app-icon-1024.png', 1024, 1024, false],
  ['adaptive-foreground.svg', 'adaptive-foreground-1024.png', 1024, 1024, true],
  ['splash.svg', 'splash-1284x2778.png', 1284, 2778, false],
  ['social-card.svg', 'social-card-1200x630.png', 1200, 630, false],
  ['wordmark.svg', 'wordmark-1200.png', 1200, 300, true],
  ['wordmark-on-ink.svg', 'wordmark-on-ink-1200.png', 1200, 300, true],
];

const tmp = join(out, '_page.html');
for (const [svg, png, w, h, transparent] of targets) {
  const svgText = readFileSync(join(assets, svg), 'utf8').replace(/ width="[\d.]+" height="[\d.]+"/, ` width="${w}" height="${h}"`);
  writeFileSync(tmp, `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:transparent;overflow:hidden}svg{display:block}</style></head><body>${svgText}</body></html>`);
  const res = spawnSync(browser, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', `--window-size=${w},${h}`, '--force-device-scale-factor=1',
    `--default-background-color=${transparent ? '00000000' : 'FFFFFFFF'}`, `--screenshot=${join(out, png)}`, pathToFileURL(tmp).href,
  ], { encoding: 'utf8', timeout: 60000 });
  if (!existsSync(join(out, png))) { console.error(`failed: ${png}\n${res.stderr}`); process.exit(1); }
  console.log(`${png} (${w}x${h})`);
}
rmSync(tmp, { force: true });

// favicon.ico: an ICO container holding the 32x32 and 48x48 PNGs (modern browsers read PNG-in-ICO).
const pngs = [[32, readFileSync(join(out, 'favicon-32.png'))], [48, readFileSync(join(out, 'favicon-48.png'))]];
const header = Buffer.alloc(6); header.writeUInt16LE(0, 0); header.writeUInt16LE(1, 2); header.writeUInt16LE(pngs.length, 4);
let offset = 6 + 16 * pngs.length;
const dirs = pngs.map(([size, data]) => {
  const e = Buffer.alloc(16);
  e.writeUInt8(size, 0); e.writeUInt8(size, 1); e.writeUInt8(0, 2); e.writeUInt8(0, 3); e.writeUInt16LE(1, 4); e.writeUInt16LE(32, 6);
  e.writeUInt32LE(data.length, 8); e.writeUInt32LE(offset, 12); offset += data.length; return e;
});
writeFileSync(join(assets, 'favicon.ico'), Buffer.concat([header, ...dirs, ...pngs.map(([, d]) => d)]));
console.log('favicon.ico');
