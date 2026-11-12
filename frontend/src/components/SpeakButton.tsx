import { useState } from 'react';
import { speechLocale } from '../i18n';
import { useStore } from '../store';

const supported = (): boolean => typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

/** Reads `text` aloud in the selected language. Renders nothing when speech is unavailable. */
export function SpeakButton({ text }: { text: string }) {
  const { state, t } = useStore();
  const [speaking, setSpeaking] = useState(false);
  if (!supported()) return null;

  const toggle = () => {
    try {
      const synth = window.speechSynthesis;
      if (speaking) { synth.cancel(); setSpeaking(false); return; }
      synth.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = speechLocale[state.lang];
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      setSpeaking(true);
      synth.speak(u);
    } catch {
      setSpeaking(false); // never break the screen because of speech
    }
  };
  return (
    <button type="button" className="speak" onClick={toggle} aria-label={speaking ? t('speak.stop') : t('speak.play')}>
      <span aria-hidden="true">{speaking ? '⏹' : '🔊'}</span>
      <span>{speaking ? t('speak.stop') : t('speak.play')}</span>
    </button>
  );
}
