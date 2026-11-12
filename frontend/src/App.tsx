import type { ReactElement } from 'react';
import { LanguageToggle } from './components/LanguageToggle';
import { SmsLog } from './components/SmsLog';
import { API_MODE } from './config';
import { ArtisanComplete } from './screens/ArtisanComplete';
import { ArtisanInbox } from './screens/ArtisanInbox';
import { ArtisanProfile } from './screens/ArtisanProfile';
import { ArtisanSignup } from './screens/ArtisanSignup';
import { ArtisanStatus } from './screens/ArtisanStatus';
import { CustomerRequest } from './screens/CustomerRequest';
import { Home } from './screens/Home';
import { Matches } from './screens/Matches';
import { Operator } from './screens/Operator';
import { Rate } from './screens/Rate';
import { Tracking } from './screens/Tracking';
import { StoreProvider, useStore } from './store';
import type { Screen } from './store/reducer';

const SCREENS: Record<Screen, () => ReactElement> = {
  home: Home,
  artisanSignup: ArtisanSignup,
  artisanStatus: ArtisanStatus,
  artisanInbox: ArtisanInbox,
  artisanComplete: ArtisanComplete,
  customerRequest: CustomerRequest,
  matches: Matches,
  tracking: Tracking,
  rate: Rate,
  operator: Operator,
  profile: ArtisanProfile,
};

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
        <button type="button" className="link" onClick={() => actions.go('operator')}>{t('footer.operator')}</button>
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
