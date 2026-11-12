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

describe('Connect flexibly: bargaining in the chat fixes the price and the commission', () => {
  it('customer and artisan talk, the customer writes 9 000 FCFA, the artisan says YES, the customer pays, the job completes with 5% = 450', async () => {
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

    // customer opens the chat and bargains
    await u.click(btn(/Échanger/));
    expect(screen.getByText(/Prix estimé \(pas encore convenu\)/)).toBeTruthy();
    await u.type(screen.getByLabelText('Votre message'), "Bonjour, c'est trop cher pour moi");
    await u.click(btn(/Envoyer/));
    expect(chatText()).toContain("c'est trop cher pour moi");

    // a number without the currency fixes nothing and reminds the customer
    await u.type(screen.getByLabelText('Votre message'), 'ok pour 9000');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('Ajoutez la monnaie à la fin');
    expect(screen.getByText(/Prix estimé \(pas encore convenu\)/)).toBeTruthy();

    // the final amount with the currency at the end is read from the chat
    await u.type(screen.getByLabelText('Votre message'), "C'est mon dernier prix : 9 000 FCFA");
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('Prix fixé : 9');
    expect(screen.getByText(/Prix fixé par le client, en attente de l'artisan/)).toBeTruthy();
    expect(chatText()).toContain('Commission 5% = 450');
    expect(sms()).toContain('Répondez OUI pour accepter'); // the artisan is told by SMS

    // the artisan (logged in as Joel) answers in the same chat; his own amount changes nothing
    await u.click(btn(/Retour/));
    await u.click(btn(/Ouvrir en artisan/));
    await u.click(btn(/Discuter/));
    expect(chatText()).toContain('9 000 FCFA');
    await u.type(screen.getByLabelText('Votre message'), 'Je préfère 12 000 FCFA');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('Seul le client peut fixer le prix');

    // YES agrees to the customer's price: it is now locked, but there is no job code until the customer pays
    await u.click(btn(/OUI/));
    expect(chatText()).toContain('Joel a accepté');
    expect(screen.getByText(/Prix convenu par les deux parties/)).toBeTruthy();
    expect(sms()).not.toMatch(/code de travail est/);

    // the customer pays the agreed 9 000 FCFA through the Payments tab (sandbox approves after 5 s)
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
    expect(sms()).toMatch(/Commission 5% = 450 FCFA/);                  // 5% of the AGREED 9 000, booked at payment
    const code = /code de travail est (\d{6})/.exec(sms())?.[1]!;

    // the chat is still open after payment but the price stays locked
    await u.click(btn(/Retour/));
    await u.click(btn(/Échanger/));
    await u.type(screen.getByLabelText('Votre message'), 'Pour moi 3 000 FCFA');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('prix est fixé');

    // finish the job with the code: the payout is the agreed price minus 5%
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
