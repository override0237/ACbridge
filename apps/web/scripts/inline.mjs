// Inlines the Vite build into ONE html file that works when double-clicked (file://).
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
const dist = new URL('../dist/', import.meta.url);
const assets = readdirSync(new URL('assets/', dist));
const js = readFileSync(new URL('assets/' + assets.find((f) => f.endsWith('.js')), dist), 'utf8');
const css = readFileSync(new URL('assets/' + assets.find((f) => f.endsWith('.css')), dist), 'utf8');
const icon = readFileSync(new URL('../../../packages/brand/assets/app-icon.svg', import.meta.url), 'utf8');
const tokensCss = readFileSync(new URL('../../../packages/tokens/generated/tokens.css', import.meta.url), 'utf8');
const ink = tokensCss.match(/--acb-color-ink:[ ]*(#[0-9A-Fa-f]{6})/)[1];
const html = `<!doctype html>
<html lang="fr">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ACbridge</title>
<meta name="theme-color" content="${ink}" />
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,${encodeURIComponent(icon)}" />
<meta property="og:title" content="ACbridge" />
<meta property="og:description" content="Trusted artisans near you" />
<style>${css}</style>
</head>
<body>
<div id="root"></div>
<noscript>ACbridge needs JavaScript.</noscript>
<script type="module">${js.replace(/<\/script/gi, '<\\/script')}</script>
</body>
</html>
`;
writeFileSync(new URL('../acbridge.html', import.meta.url), html);
console.log('acbridge.html', (html.length / 1024).toFixed(0) + ' kB');
