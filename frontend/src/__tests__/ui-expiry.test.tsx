// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const btn = (name: RegExp | string) => screen.getByRole('button', { name });
const sms = () => screen.getByRole('complementary', { name: /SMS/i }).textContent ?? '';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k), clear: () => store.clear(),
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function offerToJoel(u: ReturnType<typeof userEvent.setup>, urgency: RegExp) {
  await u.click(btn(/Je suis artisan/));
  await u.click(btn(/Je suis nouveau/));
  await u.type(screen.getByLabelText('Votre nom'), 'Joel');
  await u.type(screen.getByLabelText('Numéro de téléphone'), '670111222');
  await u.type(screen.getByLabelText('Votre métier'), 'Plombier');
  await u.type(screen.getByLabelText("Nom d'utilisateur"), 'joel');
  await u.type(screen.getByLabelText('Mot de passe'), 'secret-pass-1');
  await u.type(screen.getByLabelText('Répétez le mot de passe'), 'secret-pass-1');
  await u.click(btn(/S'inscrire/));
  await u.click(btn(/Simuler garantie 1/));
  await u.click(btn(/Simuler garantie 2/));
  await u.click(btn('Accueil'));
  await u.click(btn(/J'ai besoin d'un service/));
  await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'Plombier');
  await u.click(screen.getByRole('radio', { name: urgency }));
  expect(screen.getByText(/dans l'heure \(Aujourd'hui\)/)).toBeTruthy();       // the windows are explained on the form
  await u.click(btn(/Chercher/));
  const joel = screen.getAllByRole('article').find((c) => /Joel/.test(c.textContent ?? ''))!;
  await u.click(joel.querySelector('button')!);
  await u.click(Array.from(joel.querySelectorAll('button')).find((b) => /Confirmer/.test(b.textContent ?? ''))!);
}

describe('offers the artisan does not accept in time are nullified', () => {
  it('an urgent offer lapses after one hour: the artisan sees it expired, the customer is told to choose another', async () => {
    const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);
    await offerToJoel(u, /Aujourd/);

    await u.click(btn(/Ouvrir en artisan/));
    expect(screen.getByRole('timer').textContent).toMatch(/Répondez avant .*il reste (59 min|1 h 0 min)/); // deadline + countdown
    expect(screen.getByRole('button', { name: /OUI/ })).toBeTruthy();

    await act(async () => { await vi.advanceTimersByTimeAsync(61 * 60 * 1000); });   // an hour and a minute pass
    expect(screen.queryByRole('button', { name: /OUI/ })).toBeNull();                // no way to accept any more
    expect(screen.getByText(/Offre expirée/)).toBeTruthy();
    expect(sms()).toContain("n'a pas accepté à temps, votre demande est annulée");      // customer SMS
    expect(sms()).toContain("vous n'avez pas accepté à temps");                         // artisan SMS

    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Mon travail/));
    expect(screen.getAllByText(/l'offre est annulée\. Choisissez un autre artisan/).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Choisir un autre/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Échanger/ })).toBeNull();            // the chat is closed too
    expect(screen.queryByRole('button', { name: /Paiements/ })).toBeNull();
  });

  it('a not-urgent offer is still open after two days', async () => {
    const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);
    // same flow, but the customer picks "Pas urgent" (5 days)
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/Je suis nouveau/));
    await u.type(screen.getByLabelText('Votre nom'), 'Joel');
    await u.type(screen.getByLabelText('Numéro de téléphone'), '670111222');
    await u.type(screen.getByLabelText('Votre métier'), 'Plombier');
    await u.type(screen.getByLabelText("Nom d'utilisateur"), 'joel');
    await u.type(screen.getByLabelText('Mot de passe'), 'secret-pass-1');
    await u.type(screen.getByLabelText('Répétez le mot de passe'), 'secret-pass-1');
    await u.click(btn(/S'inscrire/));
    await u.click(btn(/Simuler garantie 1/));
    await u.click(btn(/Simuler garantie 2/));
    await u.click(btn('Accueil'));
    await u.click(btn(/J'ai besoin d'un service/));
    await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'Plombier');
    await u.click(screen.getByRole('radio', { name: /Pas urgent/ }));
    await u.click(btn(/Chercher/));
    const joel = screen.getAllByRole('article').find((c) => /Joel/.test(c.textContent ?? ''))!;
    await u.click(joel.querySelector('button')!);
    await u.click(Array.from(joel.querySelectorAll('button')).find((b) => /Confirmer/.test(b.textContent ?? ''))!);

    await act(async () => { await vi.advanceTimersByTimeAsync(2 * 24 * 60 * 60 * 1000); });
    await u.click(btn(/Ouvrir en artisan/));
    expect(screen.getByRole('button', { name: /OUI/ })).toBeTruthy();
    expect(screen.queryByText(/Offre expirée/)).toBeNull();
    await u.click(btn(/OUI/));                                                            // still accepted in time
    expect(screen.getByText(/Accepté\. Vous pouvez commencer quand le client a payé/)).toBeTruthy();
  });
});
