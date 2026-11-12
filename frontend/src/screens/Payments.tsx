import { useEffect, useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { POLL_EVERY_MS, POLL_MAX_MS, type PayMethod } from '../domain/ledger';
import type { PaymentRec } from '../domain/types';
import type { Key } from '../i18n';
import { money } from '../i18n/format';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';

const METHODS: { id: PayMethod; icon: string; label: Key }[] = [
  { id: 'mtn', icon: '🟡', label: 'pay.mtn' },
  { id: 'orange', icon: '🟠', label: 'pay.orange' },
];

/** Customer Payments tab: agreed price -> method + phone -> waiting (polls every 3 s, max 3 min) -> result -> receipt.
 *  The amount is read from the job; the customer never types it, and no commission breakdown is shown here. */
export function Payments() {
  const { state, actions, t } = useStore();
  const [step, setStep] = useState<'card' | 'method'>('card');
  const [method, setMethod] = useState<PayMethod | null>(null);
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<Key | null>(null);
  const [, setTick] = useState(0);

  const job = state.jobs.find((j) => j.id === state.ui.jobId);
  const artisan = state.artisans.find((a) => a.id === job?.artisanId);
  const request = state.requests.find((r) => r.id === job?.requestId);
  const payments = state.payments.filter((p) => p.jobId === job?.id);
  const latest: PaymentRec | undefined = payments[payments.length - 1];
  const waiting = latest?.status === 'pending';

  // Polling the status every 3 seconds while a payment is pending (the sandbox answers after 5 s).
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => setTick((n) => n + 1), POLL_EVERY_MS);
    return () => clearInterval(id);
  }, [waiting]);

  if (!job || !artisan) return <Screen title={t('pay.title')} instruction={t('tracking.none')} back="home"><span /></Screen>;

  const firstName = artisan.name.split(' ')[0];
  const timedOut = waiting && Date.now() - new Date(latest!.createdAt).getTime() > POLL_MAX_MS;
  const when = (iso?: string) => (iso ? new Date(iso).toLocaleString(state.lang === 'fr' ? 'fr-FR' : 'en-US') : '');

  const start = (e: React.FormEvent) => {
    e.preventDefault();
    if (!method) { setError('pay.errMethod'); return; }
    const r = actions.startPayment(job.id, method, phone);
    if (!r.ok) setError(({ bad_phone: 'pay.errPhone', bad_method: 'pay.errMethod', already_live: 'pay.errLive' } as Record<string, Key>)[r.reason] ?? 'pay.errNotReady');
    else { setError(null); setStep('card'); }
  };
  const press = (d: string) => { setError(null); setPhone((p) => (p.length < 12 ? p + d : p)); };

  // ---------------------------------------------------------------- 3. waiting
  if (waiting) {
    return (
      <Screen title={t('pay.title')} instruction={t('pay.waiting')} back="tracking">
        <Card>
          <p className="big-number" aria-live="polite">⏳ {t('pay.waiting')}</p>
          <p className="muted">{t('pay.waitingHint')}</p>
          {timedOut && <p role="alert" className="error">{t('pay.timeout')}</p>}
        </Card>
      </Screen>
    );
  }

  // ---------------------------------------------------------------- 4/5. result + receipt
  if (latest && (latest.status === 'succeeded' || (latest.status === 'failed' && step === 'card'))) {
    const ok = latest.status === 'succeeded';
    return (
      <Screen title={t('pay.title')} instruction={ok ? t('pay.notified') : t('pay.failedWhy')} back="tracking">
        <Card>
          <p role="status"><Badge icon={ok ? '✅' : '❌'} text={ok ? t('pay.success') : t('pay.failed')} tone={ok ? 'good' : 'bad'} /></p>
          {ok ? <p>{t('pay.notified')}</p> : <p className="error">{t('pay.failedWhy')}</p>}
          {ok && (
            <dl className="facts" aria-label={t('pay.receipt')}>
              <dt>{t('pay.ref')}</dt><dd>{latest.reference}</dd>
              <dt>{t('pay.date')}</dt><dd>{when(latest.settledAt)}</dd>
              <dt>{t('pay.amount')}</dt><dd><strong>{money(latest.amount, state.lang)} {t('common.currency')}</strong></dd>
              <dt>{t('pay.artisan')}</dt><dd>{firstName}</dd>
              <dt>{t('pay.status')}</dt><dd>{t('pay.status.succeeded')}</dd>
            </dl>
          )}
        </Card>
        {!ok && <Button big icon="🔁" label={t('pay.again')} onClick={() => { setStep('method'); setMethod(null); setPhone(''); setError(null); }} />}
        <p className="muted small">🧪 {t('pay.sandbox')}</p>
      </Screen>
    );
  }

  // ---------------------------------------------------------------- 2. method + phone
  if (step === 'method') {
    return (
      <Screen title={t('pay.method')} instruction={t('pay.method')} back="tracking">
        <form className="stack" onSubmit={start}>
          <div className="choices" role="radiogroup" aria-label={t('pay.method')}>
            {METHODS.map((m) => (
              <button key={m.id} type="button" role="radio" aria-checked={method === m.id}
                className={method === m.id ? 'choice active' : 'choice'} onClick={() => { setMethod(m.id); setError(null); }}>
                <span className="choice-icon" aria-hidden="true">{m.icon}</span><span>{t(m.label)}</span>
                {method === m.id && <span aria-hidden="true">✔</span>}
              </button>
            ))}
          </div>
          <label>{t('pay.phone')}
            <input className="code-input" inputMode="numeric" pattern="[0-9]*" autoComplete="tel" placeholder={t('pay.phoneHint')}
              value={phone} onChange={(e) => { setError(null); setPhone(e.target.value.replace(/[^\d+]/g, '').slice(0, 13)); }} />
          </label>
          <div className="keypad" role="group" aria-label={t('complete.keypad')}>
            {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => <button key={d} type="button" className="key" onClick={() => press(d)}>{d}</button>)}
            <button type="button" className="key key-sub" aria-label={t('complete.delete')} onClick={() => setPhone((p) => p.slice(0, -1))}>⌫</button>
            <button type="button" className="key" onClick={() => press('0')}>0</button>
            <span />
          </div>
          <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
          <Button type="submit" big icon="💳" label={t('pay.confirm')} />
        </form>
        <p className="muted small">🧪 {t('pay.sandbox')}</p>
      </Screen>
    );
  }

  // ---------------------------------------------------------------- 1. agreed price card
  const ready = job.status === 'ACCEPTED';
  return (
    <Screen title={t('pay.title')} instruction={t('pay.instruction')} back="tracking">
      <Card>
        <dl className="facts">
          <dt>{t('pay.artisan')}</dt><dd>{artisan.name} · {tradeLabel(t, artisan.trade)}</dd>
          <dt>{t('pay.job')}</dt><dd>{request?.description || tradeLabel(t, request?.trade ?? artisan.trade)}</dd>
          <dt>{t('pay.price')}</dt><dd>{money(job.price, state.lang)} {t('common.currency')}</dd>
          <dt>{t('pay.youPay')}</dt><dd><strong className="big-number">{money(job.price, state.lang)} {t('common.currency')}</strong></dd>
        </dl>
        <p>{t('pay.instruction')}</p>
        <p className="muted small">{t('pay.fee')}</p>
        <p className="notice">🛡️ {t('pay.protect')}</p>
      </Card>
      {!ready && <p className="notice" role="status">{t('pay.notReady')}</p>}
      <Button big icon="💳" label={t('pay.now')} disabled={!ready} onClick={() => setStep('method')} />
      <p className="muted small">🧪 {t('pay.sandbox')}</p>
    </Screen>
  );
}
