import { useState } from 'react';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
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

  return (
    <Screen title={t('request.title')} instruction={t('request.instruction')} back="home">
      <form className="stack" onSubmit={(e) => { e.preventDefault(); actions.submitRequest({ urgency, description }); }}>
        <div className="row-2">
          <label>{t('request.trade')}<input value={t('common.trade')} readOnly /></label>
          <label>{t('request.neighbourhood')}<input value={t('common.neighbourhood')} readOnly /></label>
        </div>
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
        <label>{t('request.description')}
          <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t('request.descriptionHint')} />
        </label>
        <Button type="submit" big icon="🔍" label={t('request.submit')} />
      </form>
    </Screen>
  );
}
