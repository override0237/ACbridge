import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import type { Key } from '../i18n';
import { isChatOpen } from '../domain/chat';
import { isPaid } from '../domain/ledger';
import { money } from '../i18n/format';
import { useStore } from '../store';

const STEPS: { key: Key; icon: string }[] = [
  { key: 'tracking.step.requested', icon: '📨' },
  { key: 'tracking.step.accepted', icon: '👍' },
  { key: 'tracking.step.completed', icon: '🏁' },
  { key: 'tracking.step.rated', icon: '⭐' },
];

export function Tracking() {
  const { state, actions, t } = useStore();
  const job = state.jobs.find((j) => j.id === state.ui.jobId);
  if (!job) return <Screen title={t('tracking.title')} instruction={t('tracking.none')} back="home"><span /></Screen>;

  const artisan = state.artisans.find((a) => a.id === job.artisanId);
  const rated = state.ratings.some((r) => r.jobId === job.id);
  const current = rated ? 3 : job.status === 'COMPLETED' ? 2 : job.status === 'ACCEPTED' ? 1 : 0;
  const declined = job.status === 'DECLINED' || job.status === 'EXPIRED';
  const paid = isPaid(job, state.payments);
  const msgKey: Key = job.status === 'EXPIRED' ? 'tracking.msgExpired' : declined ? 'tracking.msgDeclined' : rated ? 'tracking.msgRated'
    : job.status === 'COMPLETED' ? 'tracking.msgCompleted' : job.status === 'ACCEPTED' ? 'tracking.msgAccepted' : 'tracking.msgRequested';
  const msg = t(msgKey, { artisan: artisan?.name ?? '' });

  return (
    <Screen title={t('tracking.title')} instruction={msg} back="home">
      <Card>
        <ol className="steps" aria-label={t('tracking.title')}>
          {STEPS.map((s, i) => {
            const state_ = i < current || (rated && i === 3) ? 'done' : i === current ? 'current' : 'todo';
            return (
              <li key={s.key} className={`step step-${state_}`} aria-current={i === current ? 'step' : undefined}>
                <span className="step-dot" aria-hidden="true">{state_ === 'done' ? '✔' : s.icon}</span>
                <span className="step-label">{t(s.key)}</span>
                {i === current && !declined && <span className="step-now">{t('tracking.current')}</span>}
              </li>
            );
          })}
        </ol>
        <p role="status" className="notice">{msg}</p>
      </Card>
      {!declined && (
        <Card>
          <dl className="facts">
            <dt>{t('pay.price')}</dt><dd><strong>{money(job.price, state.lang)} {t('common.currency')}</strong></dd>
            <dt>{t('pay.contact')}</dt><dd>{paid && artisan ? artisan.phone : `🔒 ${t('pay.contactLocked')}`}</dd>
          </dl>
        </Card>
      )}
      <div className="stack">
        {(job.status === 'ACCEPTED' || job.status === 'COMPLETED') && (
          <Button big icon="💳" label={t('pay.open')} onClick={() => actions.go('payments')} />
        )}
        {isChatOpen(job) && (
          <Button big icon="💬" label={t('chat.open')} onClick={() => actions.go('chat', { chatAs: 'customer' })} />
        )}
        {declined && <Button big icon="🔁" label={t('tracking.again')} onClick={() => actions.go('matches')} />}
        {job.status === 'COMPLETED' && !rated && <Button big icon="⭐" label={t('tracking.rate')} onClick={() => actions.go('rate')} />}
        {!declined && !rated && job.status !== 'COMPLETED' && (
          <Button variant="secondary" icon="🛠️" label={t('tracking.asArtisan')} onClick={() => (state.ui.actingArtisanId === job.artisanId
            ? actions.go('artisanInbox')
            : actions.go('artisanLogin', { actingArtisanId: null, loginNext: 'artisanInbox' }))} />
        )}
        <Button variant="ghost" icon="👤" label={t('tracking.profile')} onClick={() => actions.go('profile', { profileId: job.artisanId, back: 'tracking' })} />
      </div>
    </Screen>
  );
}
