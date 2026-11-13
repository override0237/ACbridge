import { useStore } from '../store';

/** Read-only stars (value may be fractional) or, with onChange, five large star buttons. */
export function StarRating({ value, onChange }: { value: number; onChange?: (n: number) => void }) {
  const { t } = useStore();
  if (!onChange) {
    const full = Math.round(value);
    return (
      <span className="stars" role="img" aria-label={`${value.toFixed(1)} / 5`}>
        {[1, 2, 3, 4, 5].map((n) => <span key={n} className={n <= full ? 'star on' : 'star'} aria-hidden="true">{n <= full ? '★' : '☆'}</span>)}
      </span>
    );
  }
  return (
    <div className="stars stars-input" role="radiogroup" aria-label={t('rate.instruction')}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n} type="button" role="radio" aria-checked={value === n} aria-label={t('rate.stars', { n })}
          className={n <= value ? 'star-btn on' : 'star-btn'} onClick={() => onChange(n)}
        >
          <span aria-hidden="true">{n <= value ? '★' : '☆'}</span>
          <span className="star-num">{n}</span>
        </button>
      ))}
    </div>
  );
}
