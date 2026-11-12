import { useMemo, useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { StarRating } from '../components/StarRating';
import { COMPLETION_FEE_FCFA } from '../config';
import { formatScore, priceRangeLabel, rankArtisans } from '../domain/rules';
import { useStore } from '../store';

export function Matches() {
  const { state, actions, t } = useStore();
  const [confirming, setConfirming] = useState<string | null>(null);
  // Computed synchronously from local state: well under the 1 second budget.
  const ranked = useMemo(
    () => rankArtisans(state.artisans, state.vouches, state.ratings, state.jobs),
    [state.artisans, state.vouches, state.ratings, state.jobs],
  );
  const currency = t('common.currency');
  const fee = `${COMPLETION_FEE_FCFA.toLocaleString('fr-FR')} ${currency}`;
  const locale = state.lang === 'fr' ? 'fr-FR' : 'en-US';

  return (
    <Screen title={t('matches.title')} instruction={t('matches.instruction')} back="customerRequest">
      <p className="notice">💰 {t('matches.fee')} <strong>{fee}</strong></p>
      {ranked.length === 0 && <p className="muted">{t('matches.none')}</p>}
      {ranked.map(({ artisan, trust, jobs }, i) => (
        <Card key={artisan.id} as="article" highlight={i === 0}>
          {i === 0 && <p><Badge icon="🏆" text={t('matches.best')} tone="good" /></p>}
          <h2>{artisan.name} <Badge icon="✅" text={t('common.verified')} tone="good" /></h2>
          <p className="rating-line"><StarRating value={trust} /> <strong>{formatScore(trust)}</strong> <span className="muted">· {t('common.jobs', { n: jobs })}</span></p>
          <p>💵 {t('matches.price')}: <strong>{priceRangeLabel(artisan, currency, locale)}</strong></p>
          {confirming === artisan.id ? (
            <div className="confirm" role="group" aria-label={t('matches.confirmTitle')}>
              <p><strong>{t('matches.confirmTitle')}: {artisan.name}</strong></p>
              <p>💰 {t('matches.fee')} <strong>{fee}</strong></p>
              <div className="row-2">
                <Button icon="✅" label={t('matches.confirmOk')} onClick={() => actions.choose(artisan.id)} />
                <Button variant="ghost" icon="✖️" label={t('common.cancel')} onClick={() => setConfirming(null)} />
              </div>
            </div>
          ) : (
            <div className="row-2">
              <Button icon="👉" label={t('matches.choose')} onClick={() => setConfirming(artisan.id)} />
              <Button variant="secondary" icon="👤" label={t('matches.profile')} onClick={() => actions.go('profile', { profileId: artisan.id, back: 'matches' })} />
            </div>
          )}
        </Card>
      ))}
    </Screen>
  );
}
