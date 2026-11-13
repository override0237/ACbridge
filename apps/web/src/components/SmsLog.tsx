import { useState } from 'react';
import type { Key } from '../i18n';
import { renderParams } from '../i18n/format';
import { useStore } from '../store';

const time = (iso: string): string => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

/** Every SMS the system would send, in order, with the recipient. Side panel on wide screens, collapsible on phones. */
export function SmsLog() {
  const { state, t } = useStore();
  const [open, setOpen] = useState(false);
  const count = state.sms.length;
  return (
    <aside className={`sms ${open ? 'sms-open' : ''}`} aria-label={t('sms.title')}>
      <button type="button" className="sms-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden="true">💬</span> {open ? t('sms.hide') : t('sms.show')} <span className="sms-count">{count}</span>
      </button>
      <div className="sms-body">
        <h2 className="sms-title"><span aria-hidden="true">💬</span> {t('sms.title')}</h2>
        <p className="muted small">{t('sms.note')}</p>
        <ol className="sms-list" aria-live="polite" aria-relevant="additions">
          {count === 0 && <li className="muted">{t('sms.empty')}</li>}
          {state.sms.map((m) => {
            // trade/urgency/amount params are stored raw so the log re-renders in the selected language
            const params = renderParams(m.params, t, state.lang);
            return (
              <li key={m.id} className="sms-item">
                <div className="sms-meta"><strong>{t('sms.to')}: {m.to}</strong> <time dateTime={m.at}>{time(m.at)}</time></div>
                <div className="sms-text">{t(m.key as Key, params)}</div>
              </li>
            );
          })}
        </ol>
      </div>
    </aside>
  );
}
