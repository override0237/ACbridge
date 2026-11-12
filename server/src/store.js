import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_FILE = path.join(__dirname, '..', 'data', 'db.json');

/** Tiny JSON-file store so the demo needs no database. Pass file=null for in-memory. */
export function createStore(file = DEFAULT_FILE) {
  let items = [];
  let nextId = 1;

  if (file && fs.existsSync(file)) {
    try {
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      items = saved.items ?? [];
      nextId = saved.nextId ?? items.length + 1;
    } catch {
      /* corrupt file: start fresh */
    }
  } else {
    items = [
      { id: 1, title: 'Welcome to ACbridge', done: false, createdAt: new Date().toISOString() },
      { id: 2, title: 'Add, toggle or delete items', done: false, createdAt: new Date().toISOString() },
    ];
    nextId = 3;
  }

  const persist = () => {
    if (!file) return;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify({ items, nextId }, null, 2));
  };

  return {
    list: () => items,
    get: (id) => items.find((i) => i.id === id),
    create(title) {
      const item = { id: nextId++, title, done: false, createdAt: new Date().toISOString() };
      items.push(item);
      persist();
      return item;
    },
    update(id, patch) {
      const item = items.find((i) => i.id === id);
      if (!item) return null;
      Object.assign(item, patch);
      persist();
      return item;
    },
    remove(id) {
      const idx = items.findIndex((i) => i.id === id);
      if (idx === -1) return false;
      items.splice(idx, 1);
      persist();
      return true;
    },
  };
}
