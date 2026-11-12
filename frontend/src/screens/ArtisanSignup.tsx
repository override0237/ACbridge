import { useRef, useState } from 'react';
import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { TradeField } from '../components/TradeField';
import type { Key } from '../i18n';
import { useStore } from '../store';
import { speechLocale } from '../i18n';

// Web Speech API recognition is optional and vendor-prefixed; typed loosely on purpose.
type Recognition = { lang: string; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; start(): void; stop(): void };
const getRecognition = (): (new () => Recognition) | null => {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

export function ArtisanSignup() {
  const { state, actions, t } = useStore();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [trade, setTrade] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<Key | null>(null);
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const Rec = getRecognition();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const r = actions.registerArtisan({ name, phone, trade, description, username, password, confirm });
    if (!r.ok) setError(r.error);
  };

  const mic = () => {
    if (!Rec) return;
    if (listening) { rec.current?.stop(); return; }
    try {
      const r = new Rec();
      r.lang = speechLocale[state.lang];
      r.onresult = (ev) => setDescription((d) => `${d} ${ev.results[0][0].transcript}`.trim());
      r.onend = () => setListening(false);
      rec.current = r;
      setListening(true);
      r.start();
    } catch { setListening(false); }
  };

  return (
    <Screen title={t('signup.title')} instruction={t('signup.instruction')} back="home">
      <form className="stack" onSubmit={submit} noValidate>
        <label>{t('signup.name')}
          <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" required />
        </label>
        <label>{t('signup.phone')}
          <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="numeric" autoComplete="tel" placeholder={t('signup.phoneHint')} required />
        </label>
        <label>{t('signup.username')}
          <input value={username} onChange={(e) => { setUsername(e.target.value); setError(null); }} autoComplete="username" autoCapitalize="none" placeholder={t('signup.usernameHint')} required />
        </label>
        <label>{t('signup.password')}
          <input type="password" value={password} onChange={(e) => { setPassword(e.target.value); setError(null); }} autoComplete="new-password" placeholder={t('signup.passwordHint')} required />
        </label>
        <label>{t('signup.confirm')}
          <input type="password" value={confirm} onChange={(e) => { setConfirm(e.target.value); setError(null); }} autoComplete="new-password" required />
        </label>
        <TradeField label={t('signup.trade')} value={trade} onChange={(v) => { setTrade(v); setError(null); }} />
        <label>{t('signup.neighbourhood')}<input value={t('common.neighbourhood')} readOnly /></label>
        <label>{t('signup.description')}
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder={t('signup.descriptionHint')} />
        </label>
        {Rec && <Button variant="secondary" icon={listening ? '🔴' : '🎤'} label={listening ? t('signup.micOn') : t('signup.mic')} onClick={mic} />}
        <div role="alert" className="error" hidden={!error}>{error && t(error)}</div>
        <Button type="submit" big icon="✅" label={t('signup.submit')} />
      </form>
    </Screen>
  );
}
