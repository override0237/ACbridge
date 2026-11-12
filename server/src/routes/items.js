import { Router } from 'express';

export function itemsRouter(store) {
  const router = Router();

  router.get('/', (_req, res) => res.json(store.list()));

  router.post('/', (req, res) => {
    const title = typeof req.body?.title === 'string' ? req.body.title.trim() : '';
    if (!title) return res.status(400).json({ error: 'title is required' });
    res.status(201).json(store.create(title));
  });

  router.patch('/:id', (req, res) => {
    const patch = {};
    if (typeof req.body?.done === 'boolean') patch.done = req.body.done;
    if (typeof req.body?.title === 'string' && req.body.title.trim()) patch.title = req.body.title.trim();
    const item = store.update(Number(req.params.id), patch);
    if (!item) return res.status(404).json({ error: 'not found' });
    res.json(item);
  });

  router.delete('/:id', (req, res) => {
    if (!store.remove(Number(req.params.id))) return res.status(404).json({ error: 'not found' });
    res.status(204).end();
  });

  return router;
}
