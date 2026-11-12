import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { useStore } from '../store';

/** First screen for artisans: new account or existing account. */
export function ArtisanEntry() {
  const { actions, t } = useStore();
  return (
    <Screen title={t('entry.title')} instruction={t('entry.instruction')} back="home">
      <div className="stack">
        <Button big icon="📝" label={t('entry.new')} onClick={() => actions.go('artisanSignup')} />
        <p className="muted small center">{t('entry.newHint')}</p>
        <Button big variant="secondary" icon="🔑" label={t('entry.existing')} onClick={() => actions.go('artisanLogin')} />
        <p className="muted small center">{t('entry.existingHint')}</p>
      </div>
    </Screen>
  );
}
