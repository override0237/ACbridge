import { isCatalogueTrade } from '../domain/trades';
import type { Key } from './index';

/** Display name of a trade in the current language; free-text trades are shown as typed. */
export function tradeLabel(t: (key: Key) => string, trade: string): string {
  return isCatalogueTrade(trade) ? t(`trade.${trade}` as Key) : trade.charAt(0).toUpperCase() + trade.slice(1);
}
