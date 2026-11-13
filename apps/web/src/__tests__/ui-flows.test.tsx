// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { STORAGE_KEY } from '../store/persistence';

const user = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
const btn = (name: RegExp | string) => screen.getByRole('button', { name });
const lastBtn = (name: string) => { const l = screen.getAllByRole('button', { name }); return l[l.length - 1]; };
const smsText = () => screen.getByRole('complementary', { name: /SMS/i }).textContent ?? '';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k), clear: () => store.clear(),
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

type U = ReturnType<typeof user>;

/** Home -> new artisan -> sign-up form -> registered. */
export async function signUp(u: U, name: string, phone: string, trade: string, username: string, password = 'secret-pass-1') {
  await u.click(btn(/Je suis artisan/));
  await u.click(btn(/Je suis nouveau/));
  await u.type(screen.getByLabelText('Votre nom'), name);
  await u.type(screen.getByLabelText('Numéro de téléphone'), phone);
  await u.type(screen.getByLabelText('Votre métier'), trade);
  await u.type(screen.getByLabelText("Nom d'utilisateur"), username);
  await u.type(screen.getByLabelText('Mot de passe'), password);
  await u.type(screen.getByLabelText('Répétez le mot de passe'), password);
  await u.click(btn(/S'inscrire/));
}

/** Customer: tracking -> Payments -> Pay now -> MTN + number -> wait for the sandbox provider (5 s) -> success. */
export async function payNow(u: U, phone = '670123456') {
  await u.click(btn(/Paiements/));
  await u.click(btn(/^Payer$/));
  await u.click(screen.getByRole('radio', { name: /MTN/ }));
  await u.type(screen.getByLabelText('Votre numéro mobile money'), phone);
  await u.click(btn(/^Payer$/));
}

describe('full UI journey in the rendered app (French default)', () => {
  it('registers, gets vouched, is matched, agrees, is PAID, completes with the job code, gets the payout, is rated, and shows in the operator log', async () => {
    const u = user();
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Bienvenue' })).toBeTruthy();

    // 1-2. artisan registers (with credentials); vouch request SMS go to both seed artisans
    await signUp(u, 'Joel', '670111222', 'Plombier', 'joel');
    expect(screen.getByText(/0 sur 2 garanties/)).toBeTruthy();
    expect(smsText()).toContain('est plombier');
    expect(smsText()).toContain('+237690000015');
    expect(smsText()).toContain('+237690000011');

    // one vouch is not enough, the second verifies
    await u.click(btn(/Simuler garantie 1/));
    expect(screen.getByText(/1 sur 2 garanties/)).toBeTruthy();
    expect(screen.queryByText(/Vous êtes vérifié\. Les clients peuvent vous choisir\./)).toBeNull();
    await u.click(btn(/Simuler garantie 2/));
    expect(screen.getByText(/2 sur 2 garanties/)).toBeTruthy();
    expect(smsText()).toContain('vous êtes maintenant vérifié');
    expect(smsText()).toMatch(/Sceau VS-[0-9A-F]{8}/); // every vouch is sealed

    // 3-4. customer request and match list (only the asked trade, best match first)
    await u.click(btn('Accueil'));
    await u.click(btn(/J'ai besoin d'un service/));
    await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'Plombier');
    await u.click(screen.getByRole('radio', { name: /Aujourd/ }));
    await u.click(btn(/Chercher/));
    const cards = screen.getAllByRole('article');
    expect(cards.length).toBe(3); // Grace, Blaise and Joel are the only verified plumbers
    expect(within(cards[0]).getByText('Meilleur choix')).toBeTruthy();
    expect(cards.some((c) => /Paul|Rose|Daniel/.test(c.textContent ?? ''))).toBe(false);
    expect(screen.getByText(/Commission de la plateforme : 5%/)).toBeTruthy();
    const joel = cards.find((c) => within(c).queryByRole('heading', { name: /Joel/ }))!;
    expect(joel).toBeTruthy();

    // 5. choose (breakdown shown), then the artisan says YES: the price is agreed but NO job code exists yet
    await u.click(within(joel).getByRole('button', { name: /Choisir/ }));
    expect(within(joel).getByText(/Commission de la plateforme \(5%\)/)).toBeTruthy();
    await u.click(within(joel).getByRole('button', { name: /Confirmer/ }));
    expect(smsText()).toContain('+237670111222');
    await u.click(btn(/Ouvrir en artisan/)); // already logged in as Joel -> straight to his inbox
    expect(screen.getByText(/Commission de la plateforme \(5%\)/)).toBeTruthy();
    await u.click(btn(/OUI/));
    expect(smsText()).not.toMatch(/code de travail est/);
    expect(screen.getByText(/En attente du paiement du client/)).toBeTruthy(); // the artisan cannot finish yet

    // 6. the customer pays through the Payments tab: wrong phone is refused, then the sandbox approves after 5 s
    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Mon travail/));
    expect(screen.getByText(/Caché jusqu'au paiement/)).toBeTruthy();       // artisan phone is hidden before paying
    await u.click(btn(/Paiements/));
    expect(screen.getAllByText(/Vous payez le prix convenu une seule fois/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Payez via ACbridge pour protéger votre travail/)).toBeTruthy();
    expect(screen.queryByText(/Commission de la plateforme/)).toBeNull();    // no commission breakdown for the customer
    await u.click(btn(/^Payer$/));
    await u.click(screen.getByRole('radio', { name: /MTN/ }));
    await u.type(screen.getByLabelText('Votre numéro mobile money'), '12');
    await u.click(btn(/^Payer$/));
    expect(screen.getByRole('alert').textContent).toContain('numéro valide');
    await u.clear(screen.getByLabelText('Votre numéro mobile money'));
    await u.type(screen.getByLabelText('Votre numéro mobile money'), '670123456');
    await u.click(btn(/^Payer$/));
    expect(screen.getAllByText(/Confirmez le paiement sur votre téléphone/).length).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(5200); });
    expect(screen.getByText('Paiement reçu')).toBeTruthy();
    expect(screen.getAllByText('Votre artisan a été prévenu.').length).toBeGreaterThan(0);
    const receipt = screen.getByLabelText('Reçu');
    expect(receipt.textContent).toContain('SIM-');
    expect(receipt.textContent).toContain('Joel');
    expect(receipt.textContent).not.toMatch(/ommission/);                    // the receipt has no commission breakdown

    const code = /code de travail est (\d{6})/.exec(smsText())?.[1];
    expect(code).toMatch(/^\d{6}$/);
    expect(smsText()).toContain('+237690000030');                            // the code goes to the customer, not the artisan
    expect(smsText()).toMatch(/Commission 5% = 275 FCFA/);                   // the artisan is told the cut at payment time

    // 7. the artisan finishes with the code: wrong code refused, right code pays out
    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/Boîte travaux/));
    await u.click(btn(/Finir travail/));
    const wrong = code === '123456' ? '654321' : '123456';
    await u.type(screen.getByLabelText('Code du travail'), wrong);
    await u.click(lastBtn('Valider'));
    expect(screen.getByRole('alert', { name: '' }).textContent).toContain("Ce code n'est pas bon");
    expect(screen.queryByText(/Travail terminé/)).toBeNull();
    await u.type(screen.getByLabelText('Code du travail'), code!);
    await u.click(lastBtn('Valider'));
    expect(screen.getByText(/Travail terminé\. Le client peut maintenant le noter\./)).toBeTruthy();
    expect(smsText()).toMatch(/FCFA vous ont été versés/);                   // the payout was paid

    // 8. customer rates once
    await u.click(btn(/Vue client/));
    await u.click(btn(/Noter/));
    await u.click(screen.getByRole('radio', { name: '5 étoiles' }));
    await u.type(screen.getByLabelText(/Commentaire/), 'Très bon travail');
    await u.click(btn(/Envoyer/));
    expect(screen.getAllByText(/Merci\. Votre note est enregistrée\./).length).toBeGreaterThan(0);
    await u.click(btn(/Retour/));
    await u.click(btn(/Profil/));
    expect(screen.getByTestId('trust').textContent).toBe('5.0');            // 5 + 2 vouches * 0.2, capped
    expect(screen.getByText(/Très bon travail/)).toBeTruthy();
    await u.click(btn(/Retour/));

    // operator: PIN gate, ledger, payouts, reconciliation, audit log
    await u.click(btn('Accueil'));
    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '0000');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByRole('alert').textContent).toContain('PIN incorrect');
    expect(screen.queryByText("Journal d'audit")).toBeNull();
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByText("Journal d'audit")).toBeTruthy();
    expect(screen.getByText(/Note 5\/5 pour Joel/)).toBeTruthy();
    expect(screen.getByText(/Commission 5% = 275 FCFA enregistrée/)).toBeTruthy();
    expect(screen.getByText(/Chaîne intacte/)).toBeTruthy();
    expect(screen.getByText(/275 FCFA sur 1 travaux terminés/)).toBeTruthy();
    const ledger = screen.getByTestId('ledger').textContent ?? '';
    expect(ledger).toMatch(/Revenus de la plateforme.*275/);                 // 5% of 5 500
    expect(ledger).toMatch(/Artisan payé.*5.225/);
    expect(screen.getByText(/Grand livre équilibré/)).toBeTruthy();
    expect(screen.getByText(/OK : le prestataire et le grand livre concordent/)).toBeTruthy();
    await u.click(btn(/Simuler un écart/));
    expect(screen.getByRole('alert', { name: '' }).textContent).toContain('Écart');   // Mismatch warning
    await u.click(btn(/Effacer/));
    expect(screen.getByText(/OK : le prestataire/)).toBeTruthy();

    // language switch keeps state and translates SMS labels
    await u.click(screen.getByRole('button', { name: 'EN' }));
    expect(screen.getByText('Audit log')).toBeTruthy();
    expect(smsText()).toContain('To: +237');
    expect(smsText()).toContain('you are now verified');
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).ratings).toHaveLength(1);
  });

  it('a declined payment shows the failure screen and can be retried; nothing is booked', async () => {
    const u = user();
    render(<App />);
    await signUp(u, 'Joel', '670111222', 'Plombier', 'joel');
    await u.click(btn(/Simuler garantie 1/));
    await u.click(btn(/Simuler garantie 2/));
    await u.click(btn('Accueil'));
    await u.click(btn(/J'ai besoin d'un service/));
    await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'Plombier');
    await u.click(btn(/Chercher/));
    const joel = screen.getAllByRole('article').find((c) => /Joel/.test(c.textContent ?? ''))!;
    await u.click(joel.querySelector('button')!);
    await u.click(Array.from(joel.querySelectorAll('button')).find((b) => /Confirmer/.test(b.textContent ?? ''))!);
    await u.click(btn(/Ouvrir en artisan/));
    await u.click(btn(/OUI/));
    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Mon travail/));
    await payNow(u, '600000000'); // the sandbox always declines this number
    await act(async () => { await vi.advanceTimersByTimeAsync(5200); });
    expect(screen.getByText('Paiement échoué')).toBeTruthy();
    expect(smsText()).not.toMatch(/code de travail est/);
    await u.click(btn(/Réessayer/));
    await u.click(screen.getByRole('radio', { name: /Orange/ }));
    await u.type(screen.getByLabelText('Votre numéro mobile money'), '670123456');
    await u.click(btn(/^Payer$/));
    await act(async () => { await vi.advanceTimersByTimeAsync(5200); });
    expect(screen.getByText('Paiement reçu')).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).payments.map((p: { status: string }) => p.status)).toEqual(['failed', 'succeeded']);
  });

  it('the operator can hold a pending payout with a reason, completion does not pay it, and release pays it', async () => {
    const u = user();
    render(<App />);
    await signUp(u, 'Joel', '670111222', 'Plombier', 'joel');
    await u.click(btn(/Simuler garantie 1/));
    await u.click(btn(/Simuler garantie 2/));
    await u.click(btn('Accueil'));
    await u.click(btn(/J'ai besoin d'un service/));
    await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'Plombier');
    await u.click(btn(/Chercher/));
    const joel = screen.getAllByRole('article').find((c) => /Joel/.test(c.textContent ?? ''))!;
    await u.click(joel.querySelector('button')!);
    await u.click(Array.from(joel.querySelectorAll('button')).find((b) => /Confirmer/.test(b.textContent ?? ''))!);
    await u.click(btn(/Ouvrir en artisan/));
    await u.click(btn(/OUI/));
    await u.click(btn(/Retour/));
    await u.click(btn('Accueil'));
    await u.click(btn(/Mon travail/));
    await payNow(u);
    await act(async () => { await vi.advanceTimersByTimeAsync(5200); });
    const code = /code de travail est (\d{6})/.exec(smsText())![1];

    // operator holds the payout
    await u.click(btn(/Retour/));
    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    await u.click(screen.getByRole('button', { name: /Bloquer/ }));
    expect(screen.getByText(/au moins 5 caractères/)).toBeTruthy();         // a reason is required
    await u.type(screen.getByLabelText('Motif (obligatoire)'), 'le client a signalé un problème');
    await u.click(screen.getByRole('button', { name: /Bloquer/ }));
    expect(screen.getAllByText('Bloqué').length).toBeGreaterThan(0);
    expect(screen.getByText(/Versement bloqué/)).toBeTruthy();               // audit entry

    // the artisan finishes with the right code: the held payout is NOT paid
    await u.click(btn(/Retour/));
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/Boîte travaux/));
    await u.click(btn(/Finir travail/));
    await u.type(screen.getByLabelText('Code du travail'), code);
    await u.click(lastBtn('Valider'));
    expect(screen.getByText(/Travail terminé/)).toBeTruthy();
    expect(smsText()).not.toMatch(/FCFA vous ont été versés/);

    // the operator releases it (reason required) and the ledger moves
    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByTestId('ledger').textContent).toMatch(/Artisan en attente.*5.225/);
    await u.type(screen.getByLabelText('Motif (obligatoire)'), 'problème résolu, travail confirmé');
    await u.click(screen.getByRole('button', { name: /Libérer/ }));
    expect(smsText()).toMatch(/FCFA vous ont été versés/);
    expect(screen.getByTestId('ledger').textContent).toMatch(/Artisan payé.*5.225/);
    expect(screen.getByText(/Grand livre équilibré/)).toBeTruthy();
  });

  it('survives a refresh (localStorage) and Reset demo clears it', async () => {
    const u = user();
    const first = render(<App />);
    await signUp(u, 'Ana', '670333444', 'Couturier', 'ana');
    first.unmount();
    render(<App />);
    expect(screen.getByText(/0 sur 2 garanties/)).toBeTruthy(); // still logged in as Ana after the refresh
    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByText('Ana')).toBeTruthy(); // pending verification listed
    await u.click(btn(/Réinitialiser/));
    await u.click(btn(/Oui, effacer/));
    expect(screen.getByRole('heading', { name: 'Bienvenue' })).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{"artisans":[]}').artisans.length).toBeLessThanOrEqual(9);
  });

  it('lets a customer ask for any artisan: a free-text trade matches, and an unserved trade says so', async () => {
    const u = user();
    render(<App />);
    await signUp(u, 'Wendy', '670555666', 'Soudeur', 'wendy');
    await u.click(btn(/Simuler garantie 1/));
    await u.click(btn(/Simuler garantie 2/));
    await u.click(btn('Accueil'));
    await u.click(btn(/J'ai besoin d'un service/));
    await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'soudeur');
    await u.click(btn(/Chercher/));
    const cards = screen.getAllByRole('article');
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain('Wendy');
    await u.click(btn(/Retour/));
    await u.clear(screen.getByLabelText('Quel artisan vous faut-il ?'));
    await u.type(screen.getByLabelText('Quel artisan vous faut-il ?'), 'Maçon');
    await u.click(btn(/Chercher/));
    expect(screen.queryAllByRole('article')).toHaveLength(0);
    expect(screen.getByText(/Aucun artisan vérifié/)).toBeTruthy();
  });
});

describe('artisan accounts and the Vouch Seal', () => {
  it('validates sign-up, then new vs existing artisan login uses username + password', async () => {
    const u = user();
    render(<App />);
    await signUp(u, 'Imposter', '670777888', 'Plombier', 'grace');
    expect(screen.getByRole('alert').textContent).toContain("nom d'utilisateur est déjà pris");
    await u.clear(screen.getByLabelText("Nom d'utilisateur"));
    await u.type(screen.getByLabelText("Nom d'utilisateur"), 'imposter');
    await u.clear(screen.getByLabelText('Mot de passe'));
    await u.clear(screen.getByLabelText('Répétez le mot de passe'));
    await u.type(screen.getByLabelText('Mot de passe'), 'short');
    await u.type(screen.getByLabelText('Répétez le mot de passe'), 'short');
    await u.click(btn(/S'inscrire/));
    expect(screen.getByRole('alert').textContent).toContain('au moins 8 caractères');
    await u.clear(screen.getByLabelText('Mot de passe'));
    await u.clear(screen.getByLabelText('Répétez le mot de passe'));
    await u.type(screen.getByLabelText('Mot de passe'), 'long-enough-1');
    await u.type(screen.getByLabelText('Répétez le mot de passe'), 'long-enough-1');
    await u.click(btn(/S'inscrire/));
    expect(screen.getByText(/0 sur 2 garanties/)).toBeTruthy();

    await u.click(btn(/Se déconnecter/));
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/J'ai un compte/));
    await u.type(screen.getByLabelText("Nom d'utilisateur"), 'imposter');
    await u.type(screen.getByLabelText('Mot de passe'), 'wrong-password');
    await u.click(btn(/Se connecter/));
    expect(screen.getByRole('alert').textContent).toContain("Nom d'utilisateur ou mot de passe incorrect");
    await u.type(screen.getByLabelText('Mot de passe'), 'long-enough-1');
    await u.click(btn(/Se connecter/));
    expect(screen.getByText(/Connecté en tant que Imposter/)).toBeTruthy();
    await u.click(btn(/Se déconnecter/));
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/J'ai un compte/));
    await u.type(screen.getByLabelText("Nom d'utilisateur"), 'nobody');
    await u.type(screen.getByLabelText('Mot de passe'), 'whatever-123');
    await u.click(btn(/Se connecter/));
    expect(screen.getByRole('alert').textContent).toContain("Nom d'utilisateur ou mot de passe incorrect");
  });

  it('an artisan can vouch for another only once: sealed, refused on a second try, logged and chained', async () => {
    const u = user();
    render(<App />);
    await signUp(u, 'Ana', '670333444', 'Couturier', 'ana');
    await u.click(btn(/Se déconnecter/));
    await u.click(btn(/Je suis artisan/));
    await u.click(btn(/J'ai un compte/));
    await u.type(screen.getByLabelText("Nom d'utilisateur"), 'grace');
    await u.type(screen.getByLabelText('Mot de passe'), 'Demo-Pass-123!');
    await u.click(btn(/Se connecter/));
    expect(screen.getByRole('heading', { name: /Sceau de garantie/ })).toBeTruthy();
    const row = () => screen.getByText('Ana', { selector: 'strong' }).closest('.candidate') as HTMLElement;
    await u.click(within(row()).getByRole('button', { name: /Garantir/ }));
    expect(screen.getByText(/C'est définitif/)).toBeTruthy();
    await u.click(btn(/Sceller/));
    expect(screen.getByText(/Cochez la case/)).toBeTruthy();
    await u.click(screen.getByRole('checkbox'));
    await u.click(btn(/Sceller/));
    expect(screen.getByRole('status').textContent).toMatch(/Garantie scellée : VS-[0-9A-F]{8}/);
    expect(within(row()).getByText(/Scellé/)).toBeTruthy();
    await u.click(within(row()).getByRole('button', { name: /Garantir/ }));
    expect(screen.getByText(/Garantie refusée/)).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).vouches).toHaveLength(1);

    await u.click(btn('Opérateur'));
    await u.type(screen.getByLabelText('PIN'), '1234');
    await u.click(btn(/Ouvrir/));
    expect(screen.getByText(/Chaîne intacte/)).toBeTruthy();
    expect(screen.getByText(/BLOQUÉ : Grace a essayé de garantir Ana une deuxième fois/)).toBeTruthy();
  });
});
