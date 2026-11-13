import { useStore } from '../store';

export function LanguageToggle() {
  const { state, actions, t } = useStore();
  return (
    <div className="lang" role="group" aria-label={t('lang.label')}>
      {(['fr', 'en'] as const).map((l) => (
        <button
          key={l} type="button" className={state.lang === l ? 'lang-btn active' : 'lang-btn'}
          aria-pressed={state.lang === l} onClick={() => actions.setLang(l)}
        >
          {t(l === 'fr' ? 'lang.fr' : 'lang.en')}
        </button>
      ))}
    </div>
  );
}
