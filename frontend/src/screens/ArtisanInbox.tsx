import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import type { Key } from '../i18n';
import { useStore } from '../store';

export function ArtisanInbox() {
  const { state, actions, t } = useStore();
  const actingId = state.ui.actingArtisanId ?? state.artisans[0].id;
  const jobs = state.jobs.filter((j) => j.artisanId === actingId).slice().reverse();

  return (
    <Screen title={t('inbox.title')} instruction={t('inbox.instruction')} back="home">
      <label>{t('inbox.actingAs')}
        <select value={actingId} onChange={(e) => actions.go('artisanInbox', { actingArtisanId: e.target.value })}>
          {state.artisans.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      {jobs.length === 0 && <p className="muted">{t('inbox.empty')}</p>}
      {jobs.map((j) => {
        const req = state.requests.find((r) => r.id === j.requestId);
        return (
          <Card key={j.id} as="article">
            <h2>{t('inbox.from', { customer: req?.customerName ?? '' })}</h2>
            <p>⏱️ {req ? t(`urgency.${req.urgency}` as Key) : ''}</p>
            {req?.description && <p className="quote">“{req.description}”</p>}
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
