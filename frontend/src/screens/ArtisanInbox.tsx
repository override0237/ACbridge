import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { Screen } from '../components/Screen';
import type { Key } from '../i18n';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';
import { ArtisanLogin } from './ArtisanLogin';

export function ArtisanInbox() {
  const { state, actions, t } = useStore();
  const me = state.artisans.find((a) => a.id === state.ui.actingArtisanId);
  if (!me) return <ArtisanLogin next="artisanInbox" />;
  const jobs = state.jobs.filter((j) => j.artisanId === me.id).slice().reverse();

  return (
    <Screen title={t('inbox.title')} instruction={t('inbox.instruction')} back="artisanStatus">
      <p className="logged">👤 {t('login.loggedAs', { name: me.name })} <button type="button" className="link" onClick={actions.logout}>{t('login.logout')}</button></p>
      {jobs.length === 0 && <p className="muted">{t('inbox.empty')}</p>}
      {jobs.map((j) => {
        const req = state.requests.find((r) => r.id === j.requestId);
        return (
          <Card key={j.id} as="article">
            <h2>{t('inbox.from', { customer: req?.customerName ?? '' })}</h2>
            <p>🛠️ {req ? tradeLabel(t, req.trade) : ''} · ⏱️ {req ? t(`urgency.${req.urgency}` as Key) : ''}</p>
            {req?.description && <p className="quote">“{req.description}”</p>}
            {j.status !== 'DECLINED' && <PriceBreakdown price={j.price} rate={j.commissionRate} done={j.status === 'COMPLETED'} />}
            {(j.status === 'REQUESTED' || j.status === 'ACCEPTED') && (
              <Button variant="secondary" icon="💬" label={t('chat.openArtisan')} onClick={() => actions.go('chat', { chatAs: 'artisan', jobId: j.id })} />
            )}
            {j.status === 'REQUESTED' && (
              <div className="row-2">
                <Button big icon="👍" label={t('common.yes')} onClick={() => actions.answer(j.id, true)} />
                <Button big variant="danger" icon="👎" label={t('common.no')} onClick={() => actions.answer(j.id, false)} />
              </div>
            )}
            {j.status === 'ACCEPTED' && (
              <>
                <p><Badge icon="✅" text={t('inbox.accepted')} tone="good" /></p>
                <Button big icon="🔢" label={t('inbox.finish')} onClick={() => actions.go('artisanComplete', { jobId: j.id })} />
              </>
            )}
            {j.status === 'DECLINED' && <p><Badge icon="🚫" text={t('inbox.declined')} tone="bad" /></p>}
            {j.status === 'COMPLETED' && <p><Badge icon="🏁" text={t('tracking.step.completed')} tone="info" /></p>}
          </Card>
        );
      })}
    </Screen>
  );
}
