import { Badge, Card } from '../components/Card';
import { Screen } from '../components/Screen';
import { StarRating } from '../components/StarRating';
import { completedJobs, countValidVouches, formatScore, isVerified, priceRangeLabel, trustFor } from '../domain/rules';
import { COMMISSION_RATE } from '../config';
import { netRange } from '../domain/money';
import { money } from '../i18n/format';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';

export function ArtisanProfile() {
  const { state, t } = useStore();
  const artisan = state.artisans.find((a) => a.id === state.ui.profileId);
  const back = state.ui.back;
  if (!artisan) return <Screen title={t('profile.title')} instruction={t('profile.notFound')} back={back}><span /></Screen>;

  const verified = isVerified(artisan, state.vouches, state.artisans);
  const trust = trustFor(artisan, state.vouches, state.ratings, state.artisans);
  const ratings = state.ratings.filter((r) => r.artisanId === artisan.id).slice().reverse();
  const locale = state.lang === 'fr' ? 'fr-FR' : 'en-US';

  return (
    <Screen title={artisan.name} instruction={t('profile.instruction')} back={back}>
      <Card>
        <p>{verified ? <Badge icon="✅" text={t('common.verified')} tone="good" /> : <Badge icon="⏳" text={t('common.notVerified')} tone="warn" />}</p>
        <dl className="facts">
          <dt>{t('profile.trade')}</dt><dd>{tradeLabel(t, artisan.trade)}</dd>
          <dt>{t('profile.neighbourhood')}</dt><dd>{t('common.neighbourhood')}</dd>
          <dt>{t('profile.trust')}</dt><dd><StarRating value={trust} /> <strong data-testid="trust">{formatScore(trust)}</strong> / 5</dd>
          <dt>{t('profile.jobs')}</dt><dd>{completedJobs(artisan, state.jobs)}</dd>
          <dt>{t('profile.vouches')}</dt><dd>{artisan.isSeed ? '✔' : countValidVouches(artisan, state.vouches, state.artisans)}</dd>
          <dt>{t('profile.price')}</dt><dd>{priceRangeLabel(artisan, t('common.currency'), locale)}</dd>
          <dt>{t('money.netRange', { rate: COMMISSION_RATE * 100 })}</dt><dd>{money(netRange(artisan).min, state.lang)} – {money(netRange(artisan).max, state.lang)} {t('common.currency')}</dd>
        </dl>
        {artisan.description && <p className="quote">“{artisan.description}”</p>}
      </Card>
      <Card>
        <h2>{t('profile.ratings')}</h2>
        {ratings.length === 0 ? <p className="muted">{t('profile.noRatings')}</p> : (
          <ul className="plain">
            {ratings.map((r) => (
              <li key={r.id}><StarRating value={r.score} /> <strong>{r.score}/5</strong>{r.comment && <p className="quote">“{r.comment}”</p>}</li>
            ))}
          </ul>
        )}
      </Card>
    </Screen>
  );
}
