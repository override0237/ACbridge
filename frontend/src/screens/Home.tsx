import { Button } from '../components/Button';
import { Screen } from '../components/Screen';
import { useStore } from '../store';

export function Home() {
  const { state, actions, t } = useStore();
  const hasArtisan = state.ui.actingArtisanId !== null;
  return (
    <Screen title={t('home.title')} instruction={t('home.instruction')}>
      <div className="stack">
        <Button big icon="🛠️" label={t('home.artisan')} onClick={() => actions.go(hasArtisan ? 'artisanStatus' : 'artisanEntry')} />
        <p className="muted small center">{t('home.artisanHint')}</p>
        <Button big variant="secondary" icon="🔧" label={t('home.customer')} onClick={() => actions.go('customerRequest')} />
        <p className="muted small center">{t('home.customerHint')}</p>
      </div>
    </Screen>
  );
}
