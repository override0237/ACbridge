export const COMPLETION_FEE_FCFA = 500; // placeholder; shown to the customer only
export const OPERATOR_PIN = '1234'; // demo PIN
export const NEIGHBOURHOOD = 'Neighbourhood A';
export const TRADE = 'Plumbing';
export const CURRENCY = 'FCFA';
export const VOUCHES_REQUIRED = 2;
export const MAX_MATCHES = 5;
/** 'local' = fully offline (default). 'api' = mirror the journey to the FastAPI backend through the /api proxy. */
export const API_MODE: 'local' | 'api' = import.meta.env.VITE_API_MODE === 'api' ? 'api' : 'local';
export const DEMO_PASSWORD = 'Demo-Pass-123!'; // backend seed password (local demos only)
