import type { ComponentType } from 'react';
import { LanguageToggle } from './components/LanguageToggle';
import { SmsLog } from './components/SmsLog';
import { API_MODE } from './config';
import { translate } from './i18n';
import { ArtisanComplete } from './screens/ArtisanComplete';
import { ArtisanEntry } from './screens/ArtisanEntry';
import { ArtisanLogin } from './screens/ArtisanLogin';
import { ArtisanInbox } from './screens/ArtisanInbox';
import { ArtisanProfile } from './screens/ArtisanProfile';
import { ArtisanSignup } from './screens/ArtisanSignup';
import { ArtisanStatus } from './screens/ArtisanStatus';
import { CustomerRequest } from './screens/CustomerRequest';
import { Chat } from './screens/Chat';
import { Home } from './screens/Home';
import { Matches } from './screens/Matches';
import { Operator } from './screens/Operator';
import { Payments } from './screens/Payments';
import { Rate } from './screens/Rate';
import { Tracking } from './screens/Tracking';
import { StoreProvider, useStore } from './store';
import { STORAGE_KEY } from './store/persistence';
import type { Screen } from './store/reducer';

const SCREENS: Record<Screen, ComponentType> = {
  home: Home,
  artisanEntry: ArtisanEntry,
  artisanLogin: ArtisanLogin,
  artisanSignup: ArtisanSignup,
  artisanStatus: ArtisanStatus,
  artisanInbox: ArtisanInbox,
  artisanComplete: ArtisanComplete,
  customerRequest: CustomerRequest,
  matches: Matches,
  tracking: Tracking,
  chat: Chat,
  payments: Payments,
  rate: Rate,
  operator: Operator,
  profile: ArtisanProfile,
};

function toggleBackend(): void {
  const next = API_MODE === 'api' ? 'off' : window.prompt(translate(loadLang(), 'footer.connectAsk'), 'http://localhost:8000');
  if (!next) return;
  const url = new URL(window.location.href);
  url.searchParams.set('api', next);
  window.location.href = url.toString();
}
const loadLang = (): 'fr' | 'en' => { try { return (JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}').lang as 'fr' | 'en') ?? 'fr'; } catch { return 'fr'; } };

function Shell() {
  const { state, actions, t, notice, clearNotice } = useStore();
  const Current = SCREENS[state.ui.screen] ?? Home;
  return (
    <div className="app">
      <header className="top">
        <button type="button" className="brand" onClick={() => actions.go('home')} aria-label={t('common.home')}>
          <span aria-hidden="true">🌉</span> ACbridge
        </button>
        <LanguageToggle />
      </header>
      <p className="demo-banner">{t('app.demo')} · {API_MODE === 'api' ? t('mode.api') : t('mode.local')}</p>
      {notice && (
        <p className="error" role="alert">{notice} <button type="button" className="link" onClick={clearNotice}>{t('common.close')}</button></p>
      )}
      <div className="layout">
        <main className="main"><Current /></main>
        <SmsLog />
      </div>
      <footer className="foot">
        <span>{t('footer.note')}</span>
        <span>
          <button type="button" className="link" onClick={toggleBackend}>{API_MODE === 'api' ? t('footer.disconnect') : t('footer.connect')}</button>
          <button type="button" className="link" onClick={() => actions.go('operator')}>{t('footer.operator')}</button>
        </span>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <Shell />
    </StoreProvider>
  );
}
