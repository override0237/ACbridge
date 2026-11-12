// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const btn = (name: RegExp | string) => screen.getByRole('button', { name });
const lastBtn = (name: string) => { const l = screen.getAllByRole('button', { name }); return l[l.length - 1]; };
const sms = () => screen.getByRole('complementary', { name: /SMS/i }).textContent ?? '';
const chatText = () => screen.getByRole('list', { name: 'Échanger librement' }).textContent ?? '';

beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k), clear: () => store.clear(),
  });
});
afterEach(cleanup);

describe('Connect flexibly: bargaining in the chat fixes the price and the commission', () => {
  it('customer and artisan talk, the customer writes 9 000 FCFA, the artisan says YES, the job completes with 5% = 450', async () => {
    const u = userEvent.setup();
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
    expect(screen.queryByRole('alert', { hidden: false })?.textContent ?? '').not.toContain('Prix fixé'); // no price yet

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
    expect(screen.getAllByText(/Commission de la plateforme \(5%\)/).length).toBeGreaterThan(0);
    expect(sms()).toContain('Répondez OUI pour accepter'); // the artisan is told by SMS
    expect(sms()).toMatch(/fixé le prix à 9.000 FCFA|fixé le prix à 9 000 FCFA|fixé le prix à 9 000 FCFA/);

    // the artisan (already logged in as Joel) answers in the same chat; his own amount changes nothing
    await u.click(btn(/Retour/));
    await u.click(btn(/Ouvrir en artisan/));
    await u.click(btn(/Discuter/));
    expect(chatText()).toContain('9 000 FCFA');
    await u.type(screen.getByLabelText('Votre message'), 'Je préfère 12 000 FCFA');
    await u.click(btn(/Envoyer/));
    expect(screen.getByRole('alert').textContent).toContain('Seul le client peut fixer le prix');
    expect(screen.getByText(/Prix fixé par le client, en attente de l'artisan/)).toBeTruthy();

    // YES agrees to the customer's price: it is now locked
    await u.click(btn(/OUI/));
    expect(chatText()).toContain('Joel a accepté');
    expect(screen.getByText(/Prix convenu par les deux parties/)).toBeTruthy();
    await u.click(btn(/Retour/));
    await u.click(btn(/Discuter/));
    await u.type(screen.getByLabelText('Votre message'), 'Pour moi 8 000 FCFA');
    await u.click(btn(/Envoyer/)); // artisan amounts never count
    expect(screen.getByRole('alert').textContent).toContain('Seul le client');

    // finish the job with the code: the commission is 5% of the AGREED 9 000 FCFA
    const code = /code de travail est (\d{6})/.exec(sms())?.[1]!;
    await u.click(btn(/Retour/));
    await u.click(btn(/Finir travail/));
    await u.type(screen.getByLabelText('Code du travail'), code);
    await u.click(lastBtn('Valider'));
    expect(screen.getByText(/Travail terminé/)).toBeTruthy();
    expect(sms()).toMatch(/Commission 5% = 450 FCFA/);
    expect(sms()).toMatch(/Vous recevez 8.550 FCFA|Vous recevez 8 550 FCFA|Vous recevez 8 550 FCFA/);
  });
});
