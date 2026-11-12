import { en, type Dict } from './en';
import { fr } from './fr';
import { local } from './local';
import type { Lang } from '../domain/types';

export type Key = keyof Dict;
export type Params = Record<string, string | number>;

export const dictionaries: Record<Lang | 'local', Dict> = {
  fr,
  en,
  local: { ...fr, ...local }, // local-language slot: falls back to French
};

export function translate(lang: Lang | 'local', key: Key, params?: Params): string {
  let text: string = dictionaries[lang][key] ?? fr[key] ?? key;
  if (params) for (const [k, v] of Object.entries(params)) text = text.split(`{${k}}`).join(String(v));
  return text;
}

export const speechLocale: Record<Lang, string> = { fr: 'fr-FR', en: 'en-US' };
