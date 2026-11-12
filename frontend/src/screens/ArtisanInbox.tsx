import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { Screen } from '../components/Screen';
import { formatLeft, offerDeadline, timeLeftMs } from '../domain/offers';
import type { Key } from '../i18n';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';
import { useEffect, useState } from 'react';
import { ArtisanLogin } from './ArtisanLogin';

export function ArtisanInbox() {
  const { state, actions, t } = useStore();
  const me = state.artisans.find((a) => a.id === state.ui.actingArtisanId);
  if (!me) return <ArtisanLogin next="artisanInbox" />;
  const jobs = state.jobs.filter((j) => j.artisanId === me.id).slice().reverse();
  const [, setTick] = useState(0);
  const [late, setLate] = useState<string | null>(null);
  useEffect(() => { const id = setInterval(() => setTick((n) => n + 1), 30_000); return () => clearInterval(id); }, []);

  return (
    <Screen title={t('inbox.title')} instruction={t('inbox.instruction')} back="artisanStatus">
      <p className="logged">👤 {t('login.loggedAs', { name: me.name })} <button type="button" className="link" onClick={actions.logout}>{t('login.logout')}</button></p>
      {jobs.length === 0 && <p className="muted">{t('inbox.empty')}</p>}
      {jobs.map((j) => {
        const req = state.requests.find((r) => r.id === j.requestId);
        const left = timeLeftMs(j, req, Date.now());
        return (
          <Card key={j.id} as="article">
            <h2>{t('inbox.from', { customer: req?.customerName ?? '' })}</h2>
            <p>🛠️ {req ? tradeLabel(t, req.trade) : ''} · ⏱️ {req ? t(`urgency.${req.urgency}` as Key) : ''}</p>
            {req?.description && <p className="quote">“{req.description}”</p>}
            {j.status === 'REQUESTED' && (
              <p className="deadline" role="timer">⏱️ {t('inbox.deadline', { time: new Date(offerDeadline(j, req)).toLocaleString(state.lang === 'fr' ? 'fr-FR' : 'en-US') })} · {t('inbox.left', { left: formatLeft(left) })}</p>
            )}
            {j.status === 'EXPIRED' && <p><Badge icon="⌛" text={t('inbox.expired')} tone="bad" /></p>}
            {late === j.id && <div role="alert" className="error">{t('inbox.expiredNow')}</div>}
            {j.status !== 'DECLINED' && j.status !== 'EXPIRED' && <PriceBreakdown price={j.price} rate={j.commissionRate} done={j.status === 'COMPLETED'} />}
            {(j.status === 'REQUESTED' || j.status === 'ACCEPTED') && (
              <Button variant="secondary" icon="💬" label={t('chat.openArtisan')} onClick={() => actions.go('chat', { chatAs: 'artisan', jobId: j.id })} />
            )}
            {j.status === 'REQUESTED' && (
              <div className="row-2">
                <Button big icon="👍" label={t('common.yes')} onClick={() => { if (actions.answer(j.id, true).expired) setLate(j.id); }} />
                <Button big variant="danger" icon="👎" label={t('common.no')} onClick={() => { if (actions.answer(j.id, false).expired) setLate(j.id); }} />
              </div>
            )}
            {j.status === 'ACCEPTED' && (
              <>
                <p><Badge icon="✅" text={t('inbox.accepted')} tone="good" /></p>
                {j.codeHash
                  ? <Button big icon="🔢" label={t('inbox.finish')} onClick={() => actions.go('artisanComplete', { jobId: j.id })} />
                  : <p className="notice">{t('complete.waitPay')}</p>}
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
