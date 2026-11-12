import { useState } from 'react';
import { Badge, Card } from './Card';
import { Button } from './Button';
import { ACCOUNTS, balances, maskPhone, reconcile, unbalancedTransactions, type Account } from '../domain/ledger';
import type { Key } from '../i18n';
import { money } from '../i18n/format';
import { useStore } from '../store';

const PAYOUT_TONE = { PENDING: 'warn', HELD: 'bad', PAID: 'good', FAILED: 'info' } as const;
const PAYOUT_ICON = { PENDING: '⏳', HELD: '⛔', PAID: '✅', FAILED: '🚫' } as const;
const ERR: Record<string, Key> = {
  bad_reason: 'opay.errReason', not_completed: 'opay.errNotCompleted', not_holdable: 'opay.errState', not_releasable: 'opay.errState', no_payout: 'opay.errState',
};

/** Operator payments panel (shown inside the PIN-protected operator screen). */
export function OperatorPayments() {
  const { state, actions, t } = useStore();
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, Key | null>>({});
  const [override, setOverride] = useState<number | null>(null);

  const cur = t('common.currency');
  const bal = balances(state.ledger);
  const balanced = unbalancedTransactions(state.ledger).length === 0;
  const rec = reconcile(state.ledger, state.payments, state.payouts, state.jobs, override);
  const nameOf = (id: string) => state.artisans.find((a) => a.id === id)?.name ?? '';

  const act = (kind: 'hold' | 'release', payoutId: string) => {
    const reason = reasons[payoutId] ?? '';
    const r = kind === 'hold' ? actions.holdPayout(payoutId, reason) : actions.releasePayout(payoutId, reason);
    setErrors((e) => ({ ...e, [payoutId]: r.ok ? null : ERR[r.reason] }));
    if (r.ok) setReasons((x) => ({ ...x, [payoutId]: '' }));
  };

  return (
    <>
      <Card>
        <h2>💳 {t('opay.payments')}</h2>
        {state.payments.length === 0 ? <p className="muted">{t('opay.none')}</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t('pay.status')}</th><th>{t('pay.amount')}</th><th>{t('opay.ref')}</th><th>{t('pay.date')}</th></tr></thead>
              <tbody>
                {state.payments.map((p) => (
                  <tr key={p.id}>
                    <td><Badge icon={p.status === 'succeeded' ? '✅' : p.status === 'failed' ? '❌' : '⏳'} text={t(`pay.status.${p.status}` as Key)} tone={p.status === 'succeeded' ? 'good' : p.status === 'failed' ? 'bad' : 'warn'} /></td>
                    <td>{money(p.amount, state.lang)} {cur}</td>
                    <td>{p.reference}<br /><span className="muted small">{maskPhone(p.phone)}</span></td>
                    <td>{new Date(p.createdAt).toLocaleString(state.lang === 'fr' ? 'fr-FR' : 'en-US')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="seal-card">
        <h2>📒 {t('opay.ledger')}</h2>
        <p role="status">{balanced ? <Badge icon="🛡️" text={t('opay.balanced')} tone="good" /> : <span className="error">🚨 {t('opay.unbalanced')}</span>}</p>
        <dl className="facts" data-testid="ledger">
          {ACCOUNTS.map((a: Account) => (<><dt key={`${a}-k`}>{t(`acct.${a}` as Key)}</dt><dd key={`${a}-v`}><strong>{money(bal[a], state.lang)} {cur}</strong></dd></>))}
        </dl>
      </Card>

      <Card>
        <h2>💸 {t('opay.payouts')}</h2>
        {state.payouts.length === 0 && <p className="muted">{t('opay.payoutsNone')}</p>}
        {state.payouts.map((p) => (
          <div key={p.id} className="pending">
            <p><strong>{nameOf(p.artisanId)}</strong> · {money(p.amount, state.lang)} {cur}{' '}
              <Badge icon={PAYOUT_ICON[p.status]} text={t(`payout.${p.status}` as Key)} tone={PAYOUT_TONE[p.status]} />
              {p.note && <><br /><span className="muted small">{p.note}</span></>}</p>
            {(p.status === 'PENDING' || p.status === 'HELD') && (
              <>
                <label>{t('opay.reason')}
                  <input value={reasons[p.id] ?? ''} onChange={(e) => { setReasons((x) => ({ ...x, [p.id]: e.target.value })); setErrors((x) => ({ ...x, [p.id]: null })); }} />
                </label>
                <div className="row-2">
                  <Button variant="danger" icon="⛔" label={t('opay.hold')} disabled={p.status === 'HELD'} onClick={() => act('hold', p.id)} />
                  <Button icon="✅" label={t('opay.release')} onClick={() => act('release', p.id)} />
                </div>
                <div role="alert" className="error" hidden={!errors[p.id]}>{errors[p.id] && t(errors[p.id] as Key)}</div>
              </>
            )}
          </div>
        ))}
      </Card>

      <Card>
        <h2>⚖️ {t('opay.recon')}</h2>
        {rec.mismatch
          ? <p role="alert" className="error">⚠️ {t('opay.mismatch')}</p>
          : <p role="status"><Badge icon="✅" text={t('opay.reconOk')} tone="good" /></p>}
        <div className="table-wrap">
          <table>
            <thead><tr><th /><th>{t('opay.provider')}</th><th>{t('opay.ledgerSays')}</th><th>{t('opay.difference')}</th></tr></thead>
            <tbody>
              <tr><td>{t('opay.collected')}</td><td>{money(rec.provider.collected, state.lang)}</td><td>{money(rec.ledger.collection, state.lang)}</td>
                <td className={rec.differences.collected !== 0 ? 'diff-bad' : ''}>{rec.differences.collected !== 0 ? '⚠️ ' : ''}{money(rec.differences.collected, state.lang)}</td></tr>
              <tr><td>{t('opay.disbursed')}</td><td>{money(rec.provider.disbursed, state.lang)}</td><td>{money(rec.ledger.artisan_paid, state.lang)}</td>
                <td className={rec.differences.disbursed !== 0 ? 'diff-bad' : ''}>{rec.differences.disbursed !== 0 ? '⚠️ ' : ''}{money(rec.differences.disbursed, state.lang)}</td></tr>
            </tbody>
          </table>
        </div>
        <div className="row-2">
          <Button variant="secondary" icon="🧪" label={t('opay.simulate')} onClick={() => setOverride(rec.ledger.collection + 500)} />
          <Button variant="ghost" icon="↩️" label={t('opay.clearSim')} disabled={override === null} onClick={() => setOverride(null)} />
        </div>
        <h3>{t('opay.unpaid')}</h3>
        {rec.unpaidCompleted.length === 0 ? <p className="muted">{t('opay.unpaidNone')}</p> : (
          <ul className="plain">{rec.unpaidCompleted.map((u) => <li key={u.artisanId} className="error">⚠️ {t('opay.unpaidWarn', { name: nameOf(u.artisanId), n: u.jobs })}</li>)}</ul>
        )}
      </Card>
    </>
  );
}
