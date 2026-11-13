import { COMMISSION_RATE } from '../config';
import { computeCommission } from '../domain/money';
import { money } from '../i18n/format';
import { useStore } from '../store';

/**
 * Shows where the money goes for one transaction: agreed price, the platform commission cut from the artisan,
 * and what the artisan receives. Used wherever a price is about to be paid or has just been paid.
 */
export function PriceBreakdown({ price, rate = COMMISSION_RATE, done }: { price: number; rate?: number; done?: boolean }) {
  const { state, t } = useStore();
  const tx = computeCommission(price, rate);
  const cur = t('common.currency');
  return (
    <div className={done ? 'price price-done' : 'price'} role="group" aria-label={t('money.title')}>
      <div className="price-row"><span>{t('money.price')}</span><strong>{money(tx.price, state.lang)} {cur}</strong></div>
      <div className="price-row price-cut"><span>✂️ {t('money.commission', { rate: tx.ratePercent })}</span><strong>− {money(tx.commission, state.lang)} {cur}</strong></div>
      <div className="price-row price-net"><span>{done ? '✅ ' : ''}{t('money.payout')}</span><strong>{money(tx.payout, state.lang)} {cur}</strong></div>
      <p className="muted small">{t('money.note')}</p>
    </div>
  );
}
