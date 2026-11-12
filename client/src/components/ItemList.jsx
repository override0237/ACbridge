export default function ItemList({ items, onToggle, onDelete }) {
  if (!items.length) return <p className="empty">Nothing here yet - add something above.</p>;
  return (
    <ul className="items">
      {items.map((item) => (
        <li key={item.id} className={item.done ? 'done' : ''}>
          <label>
            <input type="checkbox" checked={item.done} onChange={() => onToggle(item)} />
            <span>{item.title}</span>
          </label>
          <button className="del" onClick={() => onDelete(item)} aria-label={`Delete ${item.title}`}>
            ✕
          </button>
        </li>
      ))}
    </ul>
  );
}
