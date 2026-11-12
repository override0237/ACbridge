import { useEffect, useRef, useState } from 'react';
import { Badge, Card } from '../components/Card';
import { Button } from '../components/Button';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { Screen } from '../components/Screen';
import { MAX_BODY, MAX_PRICE, MIN_PRICE, isChatOpen, type PriceStatus } from '../domain/chat';
import type { Key } from '../i18n';
import { money, renderParams } from '../i18n/format';
import { tradeLabel } from '../i18n/trade';
import { useStore } from '../store';
import { ArtisanLogin } from './ArtisanLogin';

type Feedback = { tone: 'good' | 'warn' | 'bad'; key: Key; params?: Record<string, string | number> };

/** "Connect flexibly": the customer and the artisan talk and bargain; the customer's amount-with-currency fixes the price. */
export function Chat() {
  const { state, actions, t } = useStore();
  const [text, setText] = useState('');
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const endRef = useRef<HTMLLIElement | null>(null);

  const job = state.jobs.find((j) => j.id === state.ui.jobId);
  const as = state.ui.chatAs ?? 'customer';
  const artisan = state.artisans.find((a) => a.id === job?.artisanId);
  const messages = state.chats.filter((m) => m.jobId === job?.id);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'nearest' }); }, [messages.length]);

  const back = as === 'customer' ? 'tracking' : 'artisanInbox';
  if (!job || !artisan) return <Screen title={t('chat.title')} instruction={t('tracking.none')} back="home"><span /></Screen>;
  // The artisan side needs the artisan's own login, like every other artisan screen.
  if (as === 'artisan' && state.ui.actingArtisanId !== artisan.id) return <ArtisanLogin next="chat" />;

  const open = isChatOpen(job);
  const priceLabel: Key = job.status !== 'REQUESTED' ? 'chat.priceAgreed' : job.priceSource === 'chat' ? 'chat.priceProposed' : 'chat.priceEstimate';
  const customerName = state.requests.find((r) => r.id === job.requestId)?.customerName ?? '';

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    const r = actions.sendChat(job.id, as, text);
    if (!r.ok) { setFeedback({ tone: 'bad', key: r.error }); return; }
    setText('');
    const map: Record<PriceStatus, Feedback | null> = {
      applied: { tone: 'good', key: 'chat.priceSet', params: { price: money(r.amount ?? 0, state.lang) } },
      bare_number: { tone: 'warn', key: 'chat.noCurrency' },
      out_of_range: { tone: 'bad', key: 'chat.outOfRange', params: { min: money(MIN_PRICE, state.lang), max: money(MAX_PRICE, state.lang) } },
      locked: { tone: 'warn', key: 'chat.locked' },
      not_customer: { tone: 'warn', key: 'chat.notCustomer' },
      none: null,
    };
    setFeedback(map[r.price]);
  };

  return (
    <Screen title={t('chat.title')} instruction={t('chat.instruction')} back={back}>
      <p><strong>{t('chat.with', { artisan: artisan.name })}</strong> · {tradeLabel(t, artisan.trade)}</p>
      <p className="muted small">👤 {as === 'customer' ? t('chat.asCustomer') : t('chat.asArtisan', { name: artisan.name })}</p>

      <Card>
        <p><Badge icon={job.status === 'REQUESTED' ? '💬' : '🤝'} text={t(priceLabel)} tone={job.status === 'REQUESTED' ? 'warn' : 'good'} /></p>
        <PriceBreakdown price={job.price} rate={job.commissionRate} />
      </Card>

      <Card>
        <ol className="chat" aria-live="polite" aria-relevant="additions" aria-label={t('chat.title')}>
          {messages.length === 0 && <li className="muted">{t('chat.empty')}</li>}
          {messages.map((m) => {
            const mine = m.from === as;
            const who = m.from === 'system' ? t('chat.who.system') : m.from === 'customer' ? t('chat.who.customer') : artisan.name;
            const body = m.from === 'system' ? t(m.key as Key, renderParams(m.params ?? {}, t, state.lang)) : m.text;
            return (
              <li key={m.id} className={`bubble bubble-${m.from}${mine ? ' mine' : ''}`}>
                <span className="bubble-who">{m.from === 'system' ? '🔔 ' : ''}{who}</span>
                <span className="bubble-text">{body}</span>
                {m.price !== undefined && <span className="bubble-price">✅ {money(m.price, state.lang)} {t('common.currency')}</span>}
              </li>
            );
          })}
          <li ref={endRef} aria-hidden="true" />
        </ol>
      </Card>

      {open ? (
        <form className="stack" onSubmit={send}>
          <label>{t('chat.field')}
            <textarea rows={2} value={text} maxLength={MAX_BODY} placeholder={t('chat.placeholder')}
              onChange={(e) => { setText(e.target.value); setFeedback(null); }} />
          </label>
          <p className="muted small">{as === 'customer' ? t('chat.hintCustomer') : t('chat.hintArtisan')}</p>
          <p className="muted small">🔒 {t('chat.masked')}</p>
          <div role="alert" className={`feedback feedback-${feedback?.tone ?? 'good'}`} hidden={!feedback}>{feedback && t(feedback.key, feedback.params)}</div>
          <Button type="submit" big icon="📤" label={t('chat.send')} />
        </form>
      ) : <p className="notice">{t('chat.errClosed')}</p>}

      {as === 'artisan' && job.status === 'REQUESTED' && (
        <Card>
          <p>{t('chat.yes')}</p>
          <div className="row-2">
            <Button big icon="👍" label={t('common.yes')} onClick={() => actions.answer(job.id, true)} />
            <Button big variant="danger" icon="👎" label={t('common.no')} onClick={() => actions.answer(job.id, false)} />
          </div>
        </Card>
      )}
      {as === 'customer' && <p className="muted small">{t('inbox.from', { customer: customerName })}</p>}
    </Screen>
  );
}
