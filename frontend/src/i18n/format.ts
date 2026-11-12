import type { Lang } from '../domain/types';
import type { Key, Params } from './index';
import { tradeLabel } from './trade';

const MONEY_PARAMS = new Set(['price', 'commission', 'payout', 'amount']);

export const money = (n: number, lang: Lang): string => n.toLocaleString(lang === 'fr' ? 'fr-FR' : 'en-US');

/** Turns stored parameter values (trade keys, urgency keys, amounts) into display text in the current language. */
export function renderParams(params: Params, t: (key: Key) => string, lang: Lang): Params {
  const out: Params = { ...params };
  if (typeof out.urgency === 'string') out.urgency = t(`urgency.${out.urgency}` as Key);
  if (typeof out.trade === 'string') out.trade = tradeLabel(t, out.trade).toLowerCase();
  if (typeof out.method === 'string') out.method = t(`pay.${out.method}` as Key);
  for (const k of Object.keys(out)) if (MONEY_PARAMS.has(k) && typeof out[k] === 'number') out[k] = money(out[k] as number, lang);
  return out;
}
