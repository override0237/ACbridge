import { initialState, type State } from './reducer';

const KEY = 'acbridge.demo.v1';

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
