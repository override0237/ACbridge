import type { ReactNode } from 'react';
import { Motif } from './brand/Logo';
import { SCREEN_MOTIF, type ScreenName as MotifScreen } from '@acbridge/brand';
import { useStore } from '../store';
import type { Screen as ScreenName } from '../store/reducer';
import { Button } from './Button';
import { SpeakButton } from './SpeakButton';

/** Common frame: title, spoken instruction (play button beside it), optional back button. */
export function Screen({ title, instruction, back, children }: {
  title: string; instruction: string; back?: ScreenName; children: ReactNode;
}) {
  const { state, actions, t } = useStore();
  // Each screen is signed with a piece of the logo (post, arch, baseline, span or the whole mark).
  const screenName = state.ui.screen as MotifScreen;
  const motif = SCREEN_MOTIF[screenName];
  return (
    <div className="screen" data-screen={screenName}>
      {back && <Button icon="←" label={t('common.back')} variant="ghost" onClick={() => actions.go(back)} />}
      <div className="screen-head">
        <Motif kind={motif} size={motif === 'mark' ? 96 : 56} />
        <h1>{title}</h1>
      </div>
      <span className="gold-rule" aria-hidden="true" />
      <div className="instruction">
        <p>{instruction}</p>
        <SpeakButton text={`${title}. ${instruction}`} />
      </div>
      {children}
    </div>
  );
}
