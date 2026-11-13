/**
 * Platform commission, taken from the ARTISAN's payment when a job is completed (the customer pays the agreed price only).
 * Allowed range 3% to 7% inclusive. Chosen: 5%.
 *  - Typical jobs are 3,000 to 8,000 FCFA, so 5% is 150 to 400 FCFA: small enough that artisans keep about 95% and
 *    have no reason to take jobs off-platform (the main revenue risk), large enough to pay for SMS, verification and support.
 *  - Mobile-money cash-out costs the artisan roughly 1-2% on top, so going higher than 5% would push their total cost above 8%.
 *  - Going lower (3-4%) would leave almost nothing after payment-processing costs.
 */
export const COMMISSION_RATE = 0.05;
export const MIN_COMMISSION_RATE = 0.03;
export const MAX_COMMISSION_RATE = 0.07;
export const OPERATOR_PIN = '1234'; // demo PIN
export const NEIGHBOURHOOD = 'Neighbourhood A';
export const CURRENCY = 'FCFA';
export const VOUCHES_REQUIRED = 2;
export const MAX_MATCHES = 5;
/**
 * Backend address. Set with ?api=http://localhost:8000 in the page URL (remembered), or VITE_API_MODE=api for the dev proxy.
 * No address = fully offline demo.
 */
function readApiBase(): string | null {
  try {
    const q = new URLSearchParams(window.location.search).get('api');
    if (q === 'off') { localStorage.removeItem('acbridge.api'); return null; }
    if (q) { localStorage.setItem('acbridge.api', q.replace(/\/+$/, '')); }
    const stored = localStorage.getItem('acbridge.api');
    if (stored) return stored;
  } catch { /* storage blocked: fall through */ }
  return import.meta.env.VITE_API_MODE === 'api' ? '/api' : null;
}
export const API_BASE: string | null = readApiBase();
export const API_MODE: 'local' | 'api' = API_BASE ? 'api' : 'local';
export const DEMO_PASSWORD = 'Demo-Pass-123!'; // backend seed password; also every seeded artisan's demo password
