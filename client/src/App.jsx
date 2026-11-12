import { useEffect, useState } from 'react';
import { api } from './api.js';
import ItemList from './components/ItemList.jsx';

export default function App() {
  const [items, setItems] = useState([]);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const [online, setOnline] = useState(null);

  const run = async (fn) => {
    try {
      setError('');
      await fn();
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    api.health().then(() => setOnline(true)).catch(() => setOnline(false));
    run(async () => setItems(await api.list()));
  }, []);

  const add = (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    run(async () => {
      const item = await api.create(title);
      setItems((prev) => [...prev, item]);
      setTitle('');
    });
  };

  const toggle = (item) =>
    run(async () => {
      const updated = await api.setDone(item.id, !item.done);
      setItems((prev) => prev.map((i) => (i.id === item.id ? updated : i)));
    });

  const remove = (item) =>
    run(async () => {
      await api.remove(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
    });

  return (
    <main>
      <header>
        <h1>ACbridge</h1>
        <span className={`status ${online ? 'up' : 'down'}`}>
          API: {online === null ? '...' : online ? 'connected' : 'offline'}
        </span>
      </header>
      <form onSubmit={add}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add an item..." />
        <button type="submit">Add</button>
      </form>
      {error && <p className="error">{error}</p>}
      <ItemList items={items} onToggle={toggle} onDelete={remove} />
    </main>
  );
}
