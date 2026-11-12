import { useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { StarRating } from '../components/StarRating';
import type { Key } from '../i18n';
import { useStore } from '../store';

const ERRORS: Record<string, Key> = {
  bad_score: 'rate.errNone', already_rated: 'rate.errDone', not_completed: 'rate.errNotCompleted',
};

export function Rate() {
  const { state, actions, t } = useStore();
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState('');
  const [error, setError] = useState<Key | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const job = state.jobs.find((j) => j.id === state.ui.jobId);
  const rated = !!job && state.ratings.some((r) => r.jobId === job.id);
  const justRecorded = rated && submitted;

  if (!job) return <Screen title={t('rate.title')} instruction={t('rate.noJob')} back="home"><span /></Screen>;

  const submit = () => {
    const r = actions.rate(job.id, score, comment);
    setError(r.ok ? null : ERRORS[r.reason]);
    if (r.ok) setSubmitted(true);
  };

  return (
    <Screen title={t('rate.title')} instruction={rated ? t('rate.thanks') : t('rate.instruction')} back="tracking">
      <Card>
        {rated && !submitted ? (
          <p role="alert" className="error">{t('rate.errDone')}</p>
        ) : justRecorded ? (
          <p role="status"><Badge icon="🎉" text={t('rate.thanks')} tone="good" /></p>
        ) : (
          <div className="stack">
            <StarRating value={score} onChange={(n) => { setScore(n); setError(null); }} />
            <label>{t('rate.comment')}
              <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t('rate.commentHint')} maxLength={1000} />
            </label>
            <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
            <Button big icon="📤" label={t('rate.submit')} onClick={submit} />
          </div>
        )}
      </Card>
      {rated && (
        <div className="stack">
          <Button icon="👤" variant="secondary" label={t('tracking.profile')} onClick={() => actions.go('profile', { profileId: job.artisanId, back: 'tracking' })} />
          <Button icon="🏠" variant="ghost" label={t('common.home')} onClick={() => actions.go('home')} />
        </div>
      )}
    </Screen>
  );
}
