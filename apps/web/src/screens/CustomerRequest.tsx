import { useState } from 'react';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { TradeField } from '../components/TradeField';
import type { Urgency } from '../domain/types';
import type { Key } from '../i18n';
import { useStore } from '../store';

const OPTIONS: { value: Urgency; icon: string }[] = [
  { value: 'today', icon: '🔥' },
  { value: 'week', icon: '📅' },
  { value: 'later', icon: '🕓' },
];

export function CustomerRequest() {
  const { actions, t } = useStore();
  const [urgency, setUrgency] = useState<Urgency>('today');
  const [description, setDescription] = useState('');
  const [trade, setTrade] = useState('');
  const [error, setError] = useState<Key | null>(null);

  return (
    <Screen title={t('request.title')} instruction={t('request.instruction')} back="home">
      <form className="stack" onSubmit={(e) => { e.preventDefault(); const r = actions.submitRequest({ trade, urgency, description }); if (!r.ok) setError(r.error); }}>
        <TradeField label={t('request.trade')} value={trade} onChange={(v) => { setTrade(v); setError(null); }} />
        <label>{t('request.neighbourhood')}<input value={t('common.neighbourhood')} readOnly /></label>
        <fieldset>
          <legend>{t('request.urgency')}</legend>
          <div className="choices" role="radiogroup" aria-label={t('request.urgency')}>
            {OPTIONS.map((o) => (
              <button key={o.value} type="button" role="radio" aria-checked={urgency === o.value}
                className={urgency === o.value ? 'choice active' : 'choice'} onClick={() => setUrgency(o.value)}>
                <span className="choice-icon" aria-hidden="true">{o.icon}</span>
                <span>{t(`urgency.${o.value}` as Key)}</span>
                {urgency === o.value && <span aria-hidden="true">✔</span>}
              </button>
            ))}
          </div>
        </fieldset>
        <p className="muted small">⏱️ {t('request.ttlHint')}</p>
        <label>{t('request.description')}
          <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t('request.descriptionHint')} />
        </label>
        <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
        <Button type="submit" big icon="🔍" label={t('request.submit')} />
      </form>
    </Screen>
  );
}
