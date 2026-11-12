async function request(path, options) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res.status === 204 ? null : res.json();
}

export const api = {
  health: () => request('/health'),
  list: () => request('/items'),
  create: (title) => request('/items', { method: 'POST', body: JSON.stringify({ title }) }),
  setDone: (id, done) => request(`/items/${id}`, { method: 'PATCH', body: JSON.stringify({ done }) }),
  remove: (id) => request(`/items/${id}`, { method: 'DELETE' }),
};
