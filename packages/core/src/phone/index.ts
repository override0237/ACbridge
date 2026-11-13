/** Phone numbers: the identity of every user. Pure functions, no platform APIs. */

export const DEFAULT_COUNTRY_PREFIX = '+237';

/**
 * Normalises a typed number to E.164, exactly like the backend (backend/app/schemas.py normalize_phone):
 * local Cameroon mobiles (6XXXXXXXX) get +237, 237XXXXXXXXX gets '+'. Returns null when it is not a valid number.
 */
export function normalizePhone(raw: string, prefix: string = DEFAULT_COUNTRY_PREFIX): string | null {
  let cleaned = raw.replace(/[\s\-().]/g, '');
  if (/^6\d{8}$/.test(cleaned)) cleaned = `${prefix}${cleaned}`;
  else if (new RegExp('^' + prefix.slice(1) + '\\d{9}$').test(cleaned)) cleaned = `+${cleaned}`;
  return /^\+[1-9]\d{7,14}$/.test(cleaned) ? cleaned : null;
}

/** '+237670123456' -> '+237 6******56'. Used everywhere a number is shown to someone who does not own it. */
export function maskPhone(phone: string): string {
  const digits = phone.replace(/^\+/, '');
  if (digits.length < 8) return '***';
  const cc = digits.slice(0, 3);
  const rest = digits.slice(3);
  return `+${cc} ${rest[0]}${'*'.repeat(rest.length - 3)}${rest.slice(-2)}`;
}

/** Removes phone numbers (9+ digit runs and +CC numbers) from free text, e.g. before it reaches logs or error reports. */
export function stripPhones(text: string): string {
  return text.replace(/\+\d{1,3}[ .-]?\d(?:[ .-]?\d){7,}|\d{9,}/g, '[phone]');
}
