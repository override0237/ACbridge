import { initialState, type State } from './reducer';

/** v2: artisans now carry credentials and vouches carry seals, so v1 data is not reused. */
export const STORAGE_KEY = 'acbridge.demo.v2';
const KEY = STORAGE_KEY;

export function loadState(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return initialState();
    const parsed = JSON.parse(raw) as State;
    if (parsed?.v !== 1 || !Array.isArray(parsed.artisans)) return initialState();
    return { ...initialState(), ...parsed };
  } catch {
    return initialState();
  }
}

export function saveState(state: State): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* storage full or blocked: the demo still works in memory */
  }
}

export function clearState(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
