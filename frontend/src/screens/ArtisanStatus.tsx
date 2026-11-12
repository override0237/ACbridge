import { useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { SEED_VOUCHERS } from '../data/seed';
import { countValidVouches, isVerified } from '../domain/rules';
import { VOUCHES_REQUIRED } from '../config';
import type { Key } from '../i18n';
import { useStore } from '../store';

export function ArtisanStatus() {
  const { state, actions, t } = useStore();
  const [error, setError] = useState<Key | null>(null);
  const artisan = state.artisans.find((a) => a.id === state.ui.actingArtisanId);

  if (!artisan) {
    return (
      <Screen title={t('status.title')} instruction={t('status.noArtisan')} back="home">
        <Button big icon="📝" label={t('signup.submit')} onClick={() => actions.go('artisanSignup')} />
      </Screen>
    );
  }

  const count = countValidVouches(artisan, state.vouches, state.artisans);
  const verified = isVerified(artisan, state.vouches, state.artisans);
  const mine = state.vouches.filter((v) => v.artisanId === artisan.id);

  return (
    <Screen title={t('status.title')} instruction={verified ? t('status.verifiedMsg') : t('status.instruction')} back="home">
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
              <li key={v.id}>👍 {state.artisans.find((a) => a.id === v.voucherId)?.name} <span className="muted small">{v.voucherPhone}</span></li>
            ))}
          </ul>
        )}
      </Card>
      <div className="stack">
        {SEED_VOUCHERS.map((id, i) => {
          const seed = state.artisans.find((a) => a.id === id);
          const done = mine.some((v) => v.voucherId === id);
          return (
            <div key={id}>
              <Button variant="secondary" disabled={done} icon={done ? '✔️' : '🤝'} label={done ? t('status.done') : t('status.simulate', { n: i + 1 })}
                onClick={() => { const r = actions.vouch(artisan.id, i); setError(r.ok ? null : r.error); }} />
              <p className="muted small">{t('status.simulateFrom', { n: i + 1, name: seed?.name ?? '' })}</p>
            </div>
          );
        })}
        <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
        <div className="row-2">
          <Button icon="📥" label={t('status.inbox')} onClick={() => actions.go('artisanInbox')} />
          <Button variant="secondary" icon="👤" label={t('status.profile')} onClick={() => actions.go('profile', { profileId: artisan.id, back: 'artisanStatus' })} />
        </div>
      </div>
    </Screen>
  );
}
