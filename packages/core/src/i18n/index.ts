import type { Lang } from '../types';
import { en, type Dict } from './en';
import { fr } from './fr';
import { local } from './local';

export type Key = keyof Dict;
export type Params = Record<string, string | number>;
export { en, fr, local };
export type { Dict };

export const dictionaries: Record<Lang | 'local', Dict> = {
  fr,
  en,
  local: { ...fr, ...local }, // local-language slot: falls back to French
};

/** Looks up `key` in the language (a missing key falls back to French, then to the key itself) and fills `{name}` placeholders. */
export function translate(lang: Lang | 'local', key: Key, params?: Params): string {
  let text: string = dictionaries[lang][key] ?? fr[key] ?? key;
  if (params) for (const [k, v] of Object.entries(params)) text = text.split(`{${k}}`).join(String(v));
  return text;
}

/** BCP 47 locale for speech synthesis and recognition. */
export const speechLocale: Record<Lang, string> = { fr: 'fr-FR', en: 'en-US' };
