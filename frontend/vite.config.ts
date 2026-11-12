/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In API mode (VITE_API_MODE=api) the browser calls /api/* and Vite proxies to the FastAPI backend,
// so the backend needs no CORS change.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: process.env.VITE_BACKEND_URL ?? 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') } } },
  test: { environment: 'node' },
});
