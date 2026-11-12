import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { itemsRouter } from './routes/items.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function createApp(store) {
  const app = express();
  app.use(cors());
  app.use(express.json());

  app.get('/api/health', (_req, res) => res.json({ status: 'ok', app: 'ACbridge' }));
  app.use('/api/items', itemsRouter(store));

  // Serve the built client (after `npm run build`) so one process runs everything.
  const dist = path.join(__dirname, '..', '..', 'client', 'dist');
  if (fs.existsSync(dist)) {
    app.use(express.static(dist));
    app.get(/^(?!\/api).*/, (_req, res) => res.sendFile(path.join(dist, 'index.html')));
  }
  return app;
}
