/** Money is whole FCFA (XAF has no minor unit): integers only, never floats. */

export type MoneyLang = 'fr' | 'en';

export const CURRENCY = 'FCFA';

export function assertWholeFcfa(n: number): number {
  if (!Number.isInteger(n)) throw new RangeError(`FCFA amounts are whole numbers, got ${n}`);
  return n;
}

/** 9000 -> "9 000" (fr) or "9,000" (en). */
export function formatAmount(n: number, lang: MoneyLang): string {
  return assertWholeFcfa(n).toLocaleString(lang === 'fr' ? 'fr-FR' : 'en-US');
}

/** 9000 -> "9 000 FCFA". */
export const formatFcfa = (n: number, lang: MoneyLang): string => `${formatAmount(n, lang)} ${CURRENCY}`;

/** A price range, never a single number: "3 000 - 8 000 FCFA". */
export function formatRange(min: number, max: number, lang: MoneyLang): string {
  return `${formatAmount(min, lang)} – ${formatAmount(max, lang)} ${CURRENCY}`;
}
