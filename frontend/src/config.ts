export const COMPLETION_FEE_FCFA = 500; // placeholder; shown to the customer only
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
export const DEMO_PASSWORD = 'Demo-Pass-123!'; // backend seed password (local demos only)
