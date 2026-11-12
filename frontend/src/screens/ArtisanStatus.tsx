import { useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { SEED_VOUCHERS } from '../data/seed';
import { countValidVouches, isVerified } from '../domain/rules';
import { hasVouched } from '../domain/security';
import { VOUCHES_REQUIRED } from '../config';
import type { Key } from '../i18n';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';
import { ArtisanLogin } from './ArtisanLogin';

export function ArtisanStatus() {
  const { state, actions, t } = useStore();
  const [error, setError] = useState<Key | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [worked, setWorked] = useState(false);
  const [sealedFor, setSealedFor] = useState<string | null>(null); // artisan I just vouched for
  const [vouchError, setVouchError] = useState<Key | null>(null);
  const artisan = state.artisans.find((a) => a.id === state.ui.actingArtisanId);

  if (!artisan) return <ArtisanLogin next="artisanStatus" />;

  const count = countValidVouches(artisan, state.vouches, state.artisans);
  const verified = isVerified(artisan, state.vouches, state.artisans);
  const mine = state.vouches.filter((v) => v.artisanId === artisan.id);
  const given = state.vouches.filter((v) => v.voucherId === artisan.id);
  const justSealed = sealedFor ? given.find((v) => v.artisanId === sealedFor) : undefined;
  const candidates = state.artisans.filter((a) => a.id !== artisan.id && !a.rejected && !isVerified(a, state.vouches, state.artisans));

  const seal = (candidateId: string) => {
    if (!worked) { setVouchError('vouch.errWorked'); return; }
    const r = actions.vouch(candidateId, artisan.id, true);
    if (r.ok) {
      setSealedFor(candidateId);
      setVouchError(null);
      setConfirming(null);
      setWorked(false);
    } else setVouchError(r.error);
  };

  return (
    <Screen title={t('status.title')} instruction={verified ? t('status.verifiedMsg') : t('status.instruction')} back="home">
      <p className="logged">👤 {t('login.loggedAs', { name: artisan.name })} <button type="button" className="link" onClick={actions.logout}>{t('login.logout')}</button></p>
      <Card>
        <p className="big-number" aria-live="polite">{t('status.count', { n: Math.min(count, VOUCHES_REQUIRED), total: VOUCHES_REQUIRED })}</p>
        <p>
          {verified
            ? <Badge icon="✅" text={t('common.verified')} tone="good" />
            : <Badge icon="⏳" text={artisan.rejected ? t('common.notVerified') : t('signup.waiting')} tone="warn" />}
        </p>
        <h2>{t('status.who')}</h2>
        {mine.length === 0 ? <p className="muted">{t('status.none')}</p> : (
          <ul className="plain">
            {mine.map((v) => (
              <li key={v.id}>👍 {state.artisans.find((a) => a.id === v.voucherId)?.name} <span className="seal-chip">🔒 {v.seal}</span></li>
            ))}
          </ul>
        )}
      </Card>

      {!verified && (
        <div className="stack">
          {SEED_VOUCHERS.map((id, i) => {
            const seed = state.artisans.find((a) => a.id === id);
            const done = mine.some((v) => v.voucherId === id);
            return (
              <div key={id}>
                <Button variant="secondary" disabled={done} icon={done ? '✔️' : '🤝'} label={done ? t('status.done') : t('status.simulate', { n: i + 1 })}
                  onClick={() => { const r = actions.vouch(artisan.id, id); setError(r.ok ? null : r.error); }} />
                <p className="muted small">{t('status.simulateFrom', { n: i + 1, name: seed?.name ?? '' })}</p>
              </div>
            );
          })}
          <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
        </div>
      )}

      <Card className="seal-card">
        <h2>🔒 {t('vouch.title')}</h2>
        <p className="notice">{t('vouch.rule')}</p>
        {!verified ? <p className="muted">{t('vouch.needVerified')}</p> : (
          <>
            <h3>{t('vouch.panel')}</h3>
            {candidates.length === 0 && <p className="muted">{t('vouch.none')}</p>}
            {candidates.map((c) => {
              const sealed = hasVouched(artisan.id, c.id, state.vouches);
              return (
                <div key={c.id} className="candidate">
                  <p><strong>{c.name}</strong> · {tradeLabel(t, c.trade)} {sealed && <span className="seal-chip">🔒 {t('vouch.sealed')}</span>}</p>
                  {confirming === c.id ? (
                    <div className="confirm" role="group" aria-label={t('vouch.confirmTitle', { name: c.name })}>
                      <p><strong>{t('vouch.confirmTitle', { name: c.name })}</strong></p>
                      <p className="warn-text">⚠️ {t('vouch.warn', { name: c.name })}</p>
                      <label className="check"><input type="checkbox" checked={worked} onChange={(e) => setWorked(e.target.checked)} /> {t('vouch.worked')}</label>
                      <div className="row-2">
                        <Button icon="🔏" label={t('vouch.confirm')} onClick={() => seal(c.id)} />
                        <Button variant="ghost" icon="✖️" label={t('common.cancel')} onClick={() => { setConfirming(null); setVouchError(null); }} />
                      </div>
                    </div>
                  ) : (
                    <Button variant={sealed ? 'ghost' : 'secondary'} icon={sealed ? '🔒' : '🤝'} label={t('vouch.button')}
                      onClick={() => {
                        setSealedFor(null);
                        if (sealed) { const r = actions.vouch(c.id, artisan.id, true); setVouchError(r.ok ? null : r.error); } // refused + logged as a security event
                        else { setConfirming(c.id); setVouchError(null); }
                      }} />
                  )}
                </div>
              );
            })}
            <div role="alert" className="error" hidden={!vouchError}>{vouchError && t(vouchError)}</div>
            {justSealed && <p role="status" className="seal-ok">🔏 {t('vouch.done', { seal: justSealed.seal })}</p>}
            {given.length > 0 && (
              <>
                <h3>{t('vouch.mine')}</h3>
                <ul className="plain">
                  {given.map((v) => <li key={v.id}>🔒 {state.artisans.find((a) => a.id === v.artisanId)?.name} <span className="seal-chip">{v.seal}</span></li>)}
                </ul>
              </>
            )}
          </>
        )}
      </Card>

      <div className="row-2">
        <Button icon="📥" label={t('status.inbox')} onClick={() => actions.go('artisanInbox')} />
        <Button variant="secondary" icon="👤" label={t('status.profile')} onClick={() => actions.go('profile', { profileId: artisan.id, back: 'artisanStatus' })} />
      </div>
    </Screen>
  );
}
