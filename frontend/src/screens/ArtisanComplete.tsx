import { useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import type { Key } from '../i18n';
import { useStore } from '../store';

const ERRORS: Record<string, Key> = {
  wrong_code: 'complete.errWrong', bad_format: 'complete.errFormat', not_accepted: 'complete.errNone', already_used: 'complete.errUsed',
};

export function ArtisanComplete() {
  const { state, actions, t } = useStore();
  const [code, setCode] = useState('');
  const [error, setError] = useState<Key | null>(null);

  const actingId = state.ui.actingArtisanId;
  const job =
    state.jobs.find((j) => j.id === state.ui.jobId && j.status !== 'DECLINED' && j.status !== 'REQUESTED') ??
    state.jobs.find((j) => j.artisanId === actingId && j.status === 'ACCEPTED');
  const req = job && state.requests.find((r) => r.id === job.requestId);

  const press = (d: string) => { setError(null); setCode((c) => (c.length < 6 ? c + d : c)); };
  const submit = () => {
    if (!job) return;
    const r = actions.complete(job.id, code);
    if (!r.ok) { setError(ERRORS[r.reason]); setCode(''); } else setError(null);
  };

  if (!job) {
    return (
      <Screen title={t('complete.title')} instruction={t('complete.noJob')} back="artisanInbox">
        <p className="muted">{t('complete.errNone')}</p>
      </Screen>
    );
  }

  const done = job.status === 'COMPLETED';
  return (
    <Screen title={t('complete.title')} instruction={t('complete.instruction')} back="artisanInbox">
      <Card>
        <p><strong>{t('complete.forJob', { customer: req?.customerName ?? '' })}</strong></p>
        {done ? (
          <>
            <p role="status"><Badge icon="🏁" text={t('complete.success')} tone="good" /></p>
            <Button big icon="👤" label={t('complete.toCustomer')} onClick={() => actions.go('tracking', { jobId: job.id })} />
          </>
        ) : (
          <>
            <label>{t('complete.codeField')}
              <input className="code-input" inputMode="numeric" pattern="[0-9]*" maxLength={6} autoComplete="one-time-code"
                value={code} onChange={(e) => { setError(null); setCode(e.target.value.replace(/\D/g, '').slice(0, 6)); }} />
            </label>
            <div className="keypad" role="group" aria-label={t('complete.keypad')}>
              {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
                <button key={d} type="button" className="key" onClick={() => press(d)}>{d}</button>
              ))}
              <button type="button" className="key key-sub" onClick={() => setCode((c) => c.slice(0, -1))} aria-label={t('complete.delete')}>⌫</button>
              <button type="button" className="key" onClick={() => press('0')}>0</button>
              <button type="button" className="key key-ok" onClick={submit} aria-label={t('complete.confirm')}>✔</button>
            </div>
            <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
            <Button big icon="✅" label={t('complete.confirm')} onClick={submit} />
          </>
        )}
      </Card>
    </Screen>
  );
}
