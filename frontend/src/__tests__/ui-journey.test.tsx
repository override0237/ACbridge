// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const user = () => userEvent.setup();
const btn = (name: RegExp | string) => screen.getByRole('button', { name });
const lastBtn = (name: string) => { const l = screen.getAllByRole('button', { name }); return l[l.length - 1]; };
const smsText = () => screen.getByRole('complementary', { name: /SMS/i }).textContent ?? '';

beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k), clear: () => store.clear(),
  });
});
afterEach(cleanup);

describe('full UI journey in the rendered app (French default)', () => {
  it('registers, gets vouched, is matched, completes with the job code, is rated, and shows in the operator log', async () => {
    const u = user();
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Bienvenue' })).toBeTruthy();

    // 1-2. artisan registers; vouch request SMS go to both seed artisans
    await u.click(btn(/Je suis artisan/));
    await u.type(screen.getByLabelText('Votre nom'), 'Joel');
    await u.type(screen.getByLabelText('Numéro de téléphone'), '670111222');
    await u.click(btn(/S'inscrire/));
    expect(screen.getByText(/0 sur 2 garanties/)).toBeTruthy();
    expect(smsText()).toContain('+237690000015'); // Grace
    expect(smsText()).toContain('+237690000011'); // Paul

    // one vouch is not enough, the second verifies
    await u.click(btn(/Simuler garantie 1/));
    expect(screen.getByText(/1 sur 2 garanties/)).toBeTruthy();
    expect(screen.queryByText(/Vous êtes vérifié\. Les clients peuvent vous choisir\./)).toBeNull();
    await u.click(btn(/Simuler garantie 2/));
    expect(screen.getByText(/2 sur 2 garanties/)).toBeTruthy();
    expect(smsText()).toContain('vous êtes maintenant vérifié');

    // 3-4. customer request and match list (max 5, includes Joel, best match first)
    await u.click(btn('Accueil'));
    await u.click(btn(/J'ai besoin d'un service/));
    await u.click(screen.getByRole('radio', { name: /Aujourd/ }));
    await u.click(btn(/Chercher/));
    const cards = screen.getAllByRole('article');
    expect(cards.length).toBeLessThanOrEqual(5);
    expect(cards.length).toBe(5);
    expect(within(cards[0]).getByText('Meilleur choix')).toBeTruthy();
    expect(screen.queryByText('Samuel')).toBeNull(); // pending candidate never shown
    expect(screen.getAllByText(/FCFA/).length).toBeGreaterThan(5); // ranges + fee
    const joel = cards.find((c) => within(c).queryByRole('heading', { name: /Joel/ }))!;
    expect(joel).toBeTruthy();

    // 5. choose (fee confirm step), artisan receives SMS, taps YES, customer gets the code
    await u.click(within(joel).getByRole('button', { name: /Choisir/ }));
    expect(within(joel).getByText(/Frais de fin de travail/)).toBeTruthy();
    await u.click(within(joel).getByRole('button', { name: /Confirmer/ }));
    expect(screen.getByText(/En attente de la réponse de Joel/, { selector: 'p[role=status]' })).toBeTruthy();
    expect(smsText()).toContain('+237670111222');
    await u.click(btn(/Ouvrir en artisan/));
    await u.click(btn(/OUI/));
    const code = /code de travail est (\d{6})/.exec(smsText())?.[1];
    expect(code).toMatch(/^\d{6}$/);
    expect(smsText()).toContain('+237690000030'); // code goes to the customer, not the artisan

    // 6. wrong code is refused, correct code completes
    await u.click(btn(/Finir travail/));
    const input = screen.getByLabelText('Code du travail');
    const wrong = code === '123456' ? '654321' : '123456';
    await u.type(input, wrong);
    await u.click(lastBtn('Valider'));
    expect(screen.getByRole('alert', { name: '' }).textContent).toContain("Ce code n'est pas bon");
    expect(screen.queryByText(/Travail terminé/)).toBeNull();
    await u.type(screen.getByLabelText('Code du travail'), code!);
    await u.click(lastBtn('Valider'));
    expect(screen.getByText(/Travail terminé\. Le client peut maintenant le noter\./)).toBeTruthy();

    // 7. customer rates once; a second attempt is rejected
    await u.click(btn(/Vue client/));
    await u.click(btn(/Noter/));
    await u.click(screen.getByRole('radio', { name: '5 étoiles' }));
    await u.type(screen.getByLabelText(/Commentaire/), 'Très bon travail');
    await u.click(btn(/Envoyer/));
    expect(screen.getAllByText(/Merci\. Votre note est enregistrée\./).length).toBeGreaterThan(0);
    await u.click(btn(/Retour/));
    await u.click(btn(/Profil/));

    // 8. trust score and rating on the profile (5.0 = 5 + 2 vouches * 0.2, capped)
    expect(screen.getByTestId('trust').textContent).toBe('5.0');
    expect(screen.getByText(/Très bon travail/)).toBeTruthy();
    await u.click(btn(/Retour/));

    // operator PIN gate, audit log
    await u.click(btn('Accueil'));
    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '0000');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByRole('alert').textContent).toContain('PIN incorrect');
    expect(screen.queryByText('Journal d\'audit')).toBeNull();
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByText("Journal d'audit")).toBeTruthy();
    expect(screen.getByText(/Note 5\/5 pour Joel/)).toBeTruthy();
    expect(screen.getByText(/Score de confiance mis à jour : Joel a maintenant 5\.0/)).toBeTruthy();
    expect(screen.getByText(/Travail terminé par Joel/)).toBeTruthy();

    // language switch keeps state and translates SMS labels
    await u.click(screen.getByRole('button', { name: 'EN' }));
    expect(screen.getByText('Audit log')).toBeTruthy();
    expect(smsText()).toContain('To: +237');
    expect(smsText()).toContain('is now verified'.slice(0, 0) + 'you are now verified');
    expect(JSON.parse(localStorage.getItem('acbridge.demo.v1')!).ratings).toHaveLength(1);
  });

  it('survives a refresh (localStorage) and Reset demo clears it', async () => {
    const u = user();
    const first = render(<App />);
    await u.click(btn(/Je suis artisan/));
    await u.type(screen.getByLabelText('Votre nom'), 'Ana');
    await u.type(screen.getByLabelText('Numéro de téléphone'), '670333444');
    await u.click(btn(/S'inscrire/));
    first.unmount();
    render(<App />);
    expect(screen.getByText(/0 sur 2 garanties/)).toBeTruthy();
    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByText('Ana')).toBeTruthy(); // pending verification listed
    await u.click(btn(/Réinitialiser/));
    await u.click(btn(/Oui, effacer/));
    expect(screen.getByRole('heading', { name: 'Bienvenue' })).toBeTruthy();
    expect(JSON.parse(localStorage.getItem('acbridge.demo.v1') ?? '{"artisans":[]}').artisans.length).toBeLessThanOrEqual(5);
  });
});
