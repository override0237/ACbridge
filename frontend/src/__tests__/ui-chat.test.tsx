// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const btn = (name: RegExp | string) => screen.getByRole('button', { name });
const lastBtn = (name: string) => { const l = screen.getAllByRole('button', { name }); return l[l.length - 1]; };
const sms = () => screen.getByRole('complementary', { name: /SMS/i }).textContent ?? '';
const chatText = () => screen.getByRole('list', { name: 'Échanger librement' }).textContent ?? '';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k), clear: () => store.clear(),
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('Connect flexibly: the customer bargains and the ARTISAN states the final price', () => {
  it('the customer bargains (amounts do not count), the artisan writes 9 000 FCFA, says YES, the customer pays, the job completes with 5% = 450', async () => {
    const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);

    // a verified plumber (Joel) exists and the customer chooses him
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
    await u.click(btn(/Chercher/));
    const joel = screen.getAllByRole('article').find((c) => /Joel/.test(c.textContent ?? ''))!;
    await u.click(joel.querySelector('button')!); // Choisir
    await u.click(Array.from(joel.querySelectorAll('button')).find((b) => /Confirmer/.test(b.textContent ?? ''))!);

    // customer opens the chat and bargains: his amount does NOT fix the price
    await u.click(btn(/Échanger/));
    expect(screen.getByText(/Prix estimé \(pas encore convenu\)/)).toBeTruthy();
    expect(screen.getByText(/Seul l'artisan indique le prix final/)).toBeTruthy();   // the customer is told how it works
    await u.type(screen.getByLabelText('Votre message'), "Bonjour, c'est trop cher pour moi");
    await u.click(btn(/Envoyer/));
    expect(chatText()).toContain("c'est trop cher pour moi");
    await u.type(screen.getByLabelText('Votre message'), 'Je propose 3 000 FCFA');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain("Seul l'artisan peut indiquer le prix final");
    expect(screen.getByText(/Prix estimé \(pas encore convenu\)/)).toBeTruthy();       // still just the estimate
    expect(chatText()).not.toContain('Commission 5%');

    // the artisan (logged in as Joel) answers in the same chat
    await u.click(btn(/Retour/));
    await u.click(btn(/Ouvrir en artisan/));
    await u.click(btn(/Discuter/));
    expect(chatText()).toContain('Je propose 3 000 FCFA');
    expect(screen.getByText(/Pour indiquer le prix final, terminez votre message/)).toBeTruthy();

    // a number without the currency fixes nothing and reminds the artisan
    await u.type(screen.getByLabelText('Votre message'), 'ok pour 9000');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('Ajoutez la monnaie à la fin');
    expect(screen.getByText(/Prix estimé \(pas encore convenu\)/)).toBeTruthy();

    // the artisan states the final price with the currency at the end: it is read from the chat
    await u.type(screen.getByLabelText('Votre message'), "D'accord, mon dernier prix : 9 000 FCFA");
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('Prix final fixé : 9');
    expect(screen.getByText(/Prix final indiqué par l'artisan/, { selector: '.badge' })).toBeTruthy();
    expect(chatText()).toContain('Commission 5% = 450');
    expect(sms()).toContain('a indiqué le prix final');                                // the CUSTOMER is told by SMS
    expect(sms()).not.toMatch(/code de travail est/);

    // YES accepts the job at that price: it is now locked, but there is no job code until the customer pays
    await u.click(btn(/OUI/));
    expect(chatText()).toContain('Joel a accepté');
    expect(screen.getByText(/Prix convenu par les deux parties/)).toBeTruthy();
    await u.type(screen.getByLabelText('Votre message'), 'Finalement 20 000 FCFA');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('prix est fixé');           // even the artisan cannot change it now

    // the customer sees the price and pays the agreed 9 000 FCFA (sandbox approves after 5 s)
    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Mon travail/));
    await u.click(btn(/Paiements/));
    await u.click(btn(/^Payer$/));
    await u.click(screen.getByRole('radio', { name: /Orange/ }));
    await u.type(screen.getByLabelText('Votre numéro mobile money'), '655123456');
    await u.click(btn(/^Payer$/));
    await act(async () => { await vi.advanceTimersByTimeAsync(5200); });
    expect(screen.getByText('Paiement reçu')).toBeTruthy();
    expect(sms()).toMatch(/Commission 5% = 450 FCFA/);                                  // 5% of the artisan's 9 000, booked at payment
    const code = /code de travail est (\d{6})/.exec(sms())?.[1]!;

    // finish the job with the code
    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/Boîte travaux/));
    await u.click(btn(/Finir travail/));
    await u.type(screen.getByLabelText('Code du travail'), code);
    await u.click(lastBtn('Valider'));
    expect(screen.getByText(/Travail terminé/)).toBeTruthy();
    expect(sms()).toMatch(/FCFA vous ont été versés/);
  });
});
