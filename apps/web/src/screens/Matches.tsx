import { useMemo, useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { Screen } from '../components/Screen';
import { StarRating } from '../components/StarRating';
import { agreedPrice, computeCommission, netRange } from '../domain/money';
import { formatScore, priceRangeLabel, rankArtisans } from '../domain/rules';
import { money } from '../i18n/format';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';

export function Matches() {
  const { state, actions, t } = useStore();
  const [confirming, setConfirming] = useState<string | null>(null);
  // Computed synchronously from local state: well under the 1 second budget.
  const request = state.requests.find((r) => r.id === state.ui.requestId);
  const trade = request?.trade ?? '';
  const ranked = useMemo(
    () => rankArtisans(state.artisans, state.vouches, state.ratings, state.jobs, trade),
    [state.artisans, state.vouches, state.ratings, state.jobs, trade],
  );
  const currency = t('common.currency');
  const ratePercent = computeCommission(0).ratePercent;
  const locale = state.lang === 'fr' ? 'fr-FR' : 'en-US';

  return (
    <Screen title={t('matches.title')} instruction={t('matches.instruction')} back="customerRequest">
      <p><strong>{t('matches.request')}:</strong> {tradeLabel(t, trade)} · {t('common.neighbourhood')}</p>
      <p className="notice">✂️ {t('matches.fee', { rate: ratePercent })}</p>
      {ranked.length === 0 && <p className="muted">{t('matches.none')}</p>}
      {ranked.map(({ artisan, trust, jobs }, i) => {
        const net = netRange(artisan);
        return (
          <Card key={artisan.id} as="article" highlight={i === 0}>
            {i === 0 && <p><Badge icon="🏆" text={t('matches.best')} tone="good" /></p>}
            <h2>{artisan.name} <span className="muted">· {tradeLabel(t, artisan.trade)}</span> <Badge icon="✅" text={t('common.verified')} tone="good" /></h2>
            <p className="rating-line"><StarRating value={trust} /> <strong>{formatScore(trust)}</strong> <span className="muted">· {t('common.jobs', { n: jobs })}</span></p>
            <p>💵 {t('matches.price')}: <strong>{priceRangeLabel(artisan, currency, locale)}</strong></p>
            <p className="muted small">✂️ {t('money.netRange', { rate: ratePercent })}: {money(net.min, state.lang)} – {money(net.max, state.lang)} {currency}</p>
            {confirming === artisan.id ? (
              <div className="confirm" role="group" aria-label={t('matches.confirmTitle')}>
                <p><strong>{t('matches.confirmTitle')}: {artisan.name}</strong></p>
                <PriceBreakdown price={agreedPrice(artisan)} />
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
        );
      })}
    </Screen>
  );
}
