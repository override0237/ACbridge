import { useId } from 'react';
import { TRADE_KEYS } from '../domain/trades';
import type { Key } from '../i18n';
import { useStore } from '../store';

/** Free-text trade input with suggestions from the catalogue, so any artisan can be entered. */
export function TradeField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const { t } = useStore();
  const listId = useId();
  return (
    <label>{label}
      <input list={listId} value={value} onChange={(e) => onChange(e.target.value)} placeholder={t('trade.hint')} autoComplete="off" required />
      <datalist id={listId}>
        {TRADE_KEYS.map((k) => <option key={k} value={t(`trade.${k}` as Key)} />)}
      </datalist>
    </label>
  );
}
