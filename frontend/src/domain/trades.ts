/**
 * Trades. A trade is either one of the catalogue keys below or free text typed by the user (stored normalised),
 * so a customer can ask for any kind of artisan. Matching is by normalised equality of the stored trade.
 */
import { en } from '../i18n/en';
import { fr } from '../i18n/fr';

export const TRADE_KEYS = ['plumbing', 'electrical', 'carpentry', 'masonry', 'mechanics', 'tailoring', 'hairdressing'] as const;
export type TradeKey = (typeof TRADE_KEYS)[number];

/** Names of the matching skills in the backend catalogue (backend/app/seed.py). */
export const BACKEND_SKILL: Record<TradeKey, string> = {
  plumbing: 'Plumbing', electrical: 'Electrical Repair', carpentry: 'Carpentry', masonry: 'Masonry',
  mechanics: 'Mechanics', tailoring: 'Tailoring', hairdressing: 'Hairdressing',
};

const ALIASES: Record<TradeKey, string[]> = {
  plumbing: ['plumbing', 'plumber', 'plomberie', 'plombier'],
  electrical: ['electrical', 'electrician', 'electricity', 'electrical repair', 'electricien', 'electricite'],
  carpentry: ['carpentry', 'carpenter', 'menuiserie', 'menuisier'],
  masonry: ['masonry', 'mason', 'maconnerie', 'macon'],
  mechanics: ['mechanics', 'mechanic', 'mecanique', 'mecanicien'],
  tailoring: ['tailoring', 'tailor', 'couture', 'couturier', 'couturiere'],
  hairdressing: ['hairdressing', 'hairdresser', 'coiffure', 'coiffeur', 'coiffeuse'],
};

export const normalizeText = (s: string): string =>
  s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

/** Turns what the user typed into a stored trade: a catalogue key, or the normalised free text. Null if too short. */
export function resolveTrade(input: string): string | null {
  const n = normalizeText(input);
  if (n.length < 2) return null;
  for (const key of TRADE_KEYS) {
    const names = [...ALIASES[key], normalizeText(en[`trade.${key}`]), normalizeText(fr[`trade.${key}`])];
    if (names.includes(n)) return key;
  }
  return n;
}

export const isCatalogueTrade = (trade: string): trade is TradeKey => (TRADE_KEYS as readonly string[]).includes(trade);

export const sameTrade = (a: string, b: string): boolean => normalizeText(a) === normalizeText(b);
