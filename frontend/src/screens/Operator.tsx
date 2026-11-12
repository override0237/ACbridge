import { useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { VOUCHES_REQUIRED } from '../config';
import { SEED_OPERATOR } from '../data/seed';
import { countValidVouches, formatScore, isVerified, trustFor } from '../domain/rules';
import type { AuditEntry } from '../domain/types';
import type { Key } from '../i18n';
import { useStore } from '../store';

export function Operator() {
  const { state, actions, t } = useStore();
  const [unlocked, setUnlocked] = useState(false);
  const [pin, setPin] = useState('');
  const [wrong, setWrong] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  if (!unlocked) {
    return (
      <Screen title={t('operator.title')} instruction={t('operator.instruction')} back="home">
        <form className="stack" onSubmit={(e) => {
          e.preventDefault();
          if (pin === SEED_OPERATOR.pin) { setUnlocked(true); setWrong(false); } else { setWrong(true); setPin(''); }
        }}>
          <label>{t('operator.pin')}
            <input type="password" inputMode="numeric" autoComplete="off" value={pin} maxLength={8} onChange={(e) => { setWrong(false); setPin(e.target.value.replace(/\D/g, '')); }} />
          </label>
          <div role="alert" className="error" hidden={!wrong}>{wrong && t('operator.wrongPin')}</div>
          <Button type="submit" big icon="🔓" label={t('operator.unlock')} />
        </form>
      </Screen>
    );
  }

  const pending = state.artisans.filter((a) => !a.rejected && !isVerified(a, state.vouches, state.artisans));
  const verified = state.artisans.filter((a) => isVerified(a, state.vouches, state.artisans));
  const locale = state.lang === 'fr' ? 'fr-FR' : 'en-US';

  const describe = (e: AuditEntry): string => {
    const k = (e.kind === 'verification' ? `audit.${e.params.event}` : `audit.${e.kind}`) as Key;
    return t(k, e.params);
  };

  return (
    <Screen title={t('operator.title')} instruction={t('operator.pending')} back="home">
      <Card>
        <h2>{t('operator.pending')}</h2>
        {pending.length === 0 && <p className="muted">{t('operator.pendingNone')}</p>}
        {pending.map((a) => (
          <div key={a.id} className="pending">
            <p><strong>{a.name}</strong> <span className="muted small">{a.phone}</span><br />
              <Badge icon="⏳" text={t('operator.vouchCount', { n: Math.min(countValidVouches(a, state.vouches, state.artisans), VOUCHES_REQUIRED), total: VOUCHES_REQUIRED })} tone="warn" /></p>
            <div className="row-2">
              <Button icon="✅" label={t('operator.approve')} onClick={() => actions.operator(a.id, true)} />
              <Button variant="danger" icon="❌" label={t('operator.reject')} onClick={() => actions.operator(a.id, false)} />
            </div>
          </div>
        ))}
      </Card>

      <Card>
        <h2>{t('operator.trust')}</h2>
        <ul className="plain">
          {verified.map((a) => (
            <li key={a.id}>{a.name}: <strong>{formatScore(trustFor(a, state.vouches, state.ratings, state.artisans))}</strong></li>
          ))}
        </ul>
      </Card>

      <Card>
        <h2>{t('operator.audit')}</h2>
        {state.audit.length === 0 ? <p className="muted">{t('operator.auditEmpty')}</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t('operator.time')}</th><th>{t('operator.event')}</th></tr></thead>
              <tbody>
                {state.audit.map((e) => (
                  <tr key={e.id}>
                    <td><time dateTime={e.at}>{new Date(e.at).toLocaleString(locale)}</time></td>
                    <td>{describe(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="stack">
        {confirmReset ? (
          <div className="confirm" role="group">
            <p><strong>{t('operator.resetAsk')}</strong></p>
            <div className="row-2">
              <Button variant="danger" icon="🗑️" label={t('operator.resetYes')} onClick={() => { actions.reset(); setUnlocked(false); setConfirmReset(false); }} />
              <Button variant="ghost" icon="✖️" label={t('common.cancel')} onClick={() => setConfirmReset(false)} />
            </div>
          </div>
        ) : (
          <Button variant="danger" icon="♻️" label={t('operator.reset')} onClick={() => setConfirmReset(true)} />
        )}
        <Button variant="ghost" icon="🔒" label={t('operator.lock')} onClick={() => setUnlocked(false)} />
      </div>
    </Screen>
  );
}
