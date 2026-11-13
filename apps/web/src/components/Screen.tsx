import type { ReactNode } from 'react';
import { useStore } from '../store';
import type { Screen as ScreenName } from '../store/reducer';
import { Button } from './Button';
import { SpeakButton } from './SpeakButton';

/** Common frame: title, spoken instruction (play button beside it), optional back button. */
export function Screen({ title, instruction, back, children }: {
  title: string; instruction: string; back?: ScreenName; children: ReactNode;
}) {
  const { actions, t } = useStore();
  return (
    <div className="screen">
      {back && <Button icon="←" label={t('common.back')} variant="ghost" onClick={() => actions.go(back)} />}
      <h1>{title}</h1>
      <div className="instruction">
        <p>{instruction}</p>
        <SpeakButton text={`${title}. ${instruction}`} />
      </div>
      {children}
    </div>
  );
}
