import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/app.js';
import { createStore } from '../src/store.js';

async function withServer(fn) {
  const server = createApp(createStore(null)).listen(0);
  const base = `http://localhost:${server.address().port}`;
  try {
    await fn(base);
  } finally {
    server.close();
  }
}

const json = (body, method = 'POST') => ({
  method,
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body),
});

test('health check', () =>
  withServer(async (base) => {
    const res = await fetch(`${base}/api/health`);
    assert.equal((await res.json()).status, 'ok');
  }));

test('create, toggle, delete item', () =>
  withServer(async (base) => {
    const created = await (await fetch(`${base}/api/items`, json({ title: 'Test' }))).json();
    assert.equal(created.title, 'Test');

    const toggled = await (await fetch(`${base}/api/items/${created.id}`, json({ done: true }, 'PATCH'))).json();
    assert.equal(toggled.done, true);

    const del = await fetch(`${base}/api/items/${created.id}`, { method: 'DELETE' });
    assert.equal(del.status, 204);
    assert.equal((await fetch(`${base}/api/items/${created.id}`, { method: 'DELETE' })).status, 404);
  }));

test('rejects empty title', () =>
  withServer(async (base) => {
    const res = await fetch(`${base}/api/items`, json({ title: '  ' }));
    assert.equal(res.status, 400);
  }));
