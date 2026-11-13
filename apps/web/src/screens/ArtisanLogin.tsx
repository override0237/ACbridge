import { useState } from 'react';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { DEMO_PASSWORD } from '../config';
import type { Key } from '../i18n';
import { useStore } from '../store';
import type { Screen as ScreenName } from '../store/reducer';

/** Username + password login for existing artisans. Also rendered inline by artisan screens when nobody is logged in. */
export function ArtisanLogin({ next }: { next?: ScreenName }) {
  const { state, actions, t } = useStore();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<Key | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const r = actions.loginArtisan(username, password, next ?? state.ui.loginNext ?? undefined);
    if (!r.ok) { setError(r.error); setPassword(''); }
  };

  return (
    <Screen title={t('login.title')} instruction={t('login.instruction')} back="home">
      <form className="stack" onSubmit={submit}>
        <label>{t('login.username')}
          <input value={username} onChange={(e) => { setUsername(e.target.value); setError(null); }} autoComplete="username" autoCapitalize="none" required />
        </label>
        <label>{t('login.password')}
          <input type="password" value={password} onChange={(e) => { setPassword(e.target.value); setError(null); }} autoComplete="current-password" required />
        </label>
        <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
        <Button type="submit" big icon="🔑" label={t('login.submit')} />
      </form>
      <Button variant="secondary" icon="📝" label={t('login.create')} onClick={() => actions.go('artisanSignup')} />
      <p className="notice">{t('login.demo', { password: DEMO_PASSWORD })}</p>
    </Screen>
  );
}
