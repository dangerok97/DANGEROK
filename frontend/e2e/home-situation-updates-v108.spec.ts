import { test, expect, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';

// Production Home components; all data below is explicitly simulated and offline.
async function openHome(page: Page, work: Record<string, unknown>) {
  let homeReads = 0;
  const user = { user_id: 'qa-home-v108', name: 'Esempio Test', first_name: 'Esempio', last_name: 'Test', email: 'home-qa@example.invalid', provider: 'password', identity_confirmed: true };
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let json: any = {};
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.includes('/auth/') && request.method() === 'POST') json = { token: 'offline-test-not-a-credential', user };
    else if (path.endsWith('/me') || path.endsWith('/auth/user')) json = user;
    else if (path.includes('life-setup')) json = { enabled: false, session: { status: 'completed' } };
    else if (path.includes('home')) {
      homeReads += 1;
      json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {}, generated_at: new Date().toISOString(), ora_ti_consiglia: [], agent_work: [work], open_questions: [] };
    }
    else if (path.includes('knowledge-map')) json = { stars: [], branches: [], count: 0, percent: 0 };
    else if (path === '/api/places') json = { places: [], candidates: [], routines: [], pending_candidates: false, permission: { preference: 'off', state: 'off' } };
    else if (path === '/api/financial/overview') json = { collegamento: { stato: 'non_collegato', in_parole: 'Nessuna banca collegata.' }, conti: [], cosa_ho_capito: [], fonti_non_piu_collegate: [], collegato_alla_tua_vita: [], da_capire: [], movimenti_recenti: [], vale_la_pena_mostrarlo: false };
    else if (path.includes('location')) json = { preference: 'off', enabled: false, status: 'off' };
    const headers = { 'access-control-allow-origin': request.headers()['origin'] || 'http://127.0.0.1:8093', 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization, content-type', 'access-control-allow-methods': 'GET, POST, PUT, DELETE, OPTIONS', 'vary': 'Origin' };
    await route.fulfill({ status: request.method() === 'OPTIONS' ? 204 : 200, headers, ...(request.method() === 'OPTIONS' ? {} : { json }) });
  });
  await page.route(url => !['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http'), route => route.abort());
  await page.goto('/login');
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill('home-qa@example.invalid');
  await page.getByTestId('login-password-input').fill('OfflineFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('home-safe')).toBeVisible({ timeout: 30000 });
  await expect.poll(() => homeReads).toBeGreaterThan(0);
}

const base = { id: 'gol_qa_home', what: 'Panni stesi', outcome: 'Esito desiderato simulato', source: 'Una tua conversazione', source_kind: 'situation_followup', icon_key: 'shirt', autonomous: true };

test('scheduled-only Situation is not counted as a Home update or an item in the expanded list', async ({ page }) => {
  await openHome(page, { ...base, progress_kind: 'scheduled', show_in_updates: false, state: 'Controllo programmato.' });
  await expect(page.getByTestId('home-updates')).toHaveCount(0);
  await page.goto('/aggiornamenti');
  await expect(page.getByTestId('aggiornamenti-vuoto')).toBeVisible();
  await expect(page.getByTestId('aggiornamento-gol_qa_home')).toHaveCount(0);
});

test('a published result is readable without internal goal wording or a false execution badge', async ({ page }, info) => {
  await openHome(page, { ...base, progress_kind: 'update', show_in_updates: true, state: 'Esito simulato: è il momento di verificare i capi e raccoglierli.', outcome: 'Esito simulato disponibile.' });
  const row = page.getByTestId('home-agent-gol_qa_home');
  await row.scrollIntoViewIfNeeded();
  await expect(row).toContainText('Panni stesi');
  await expect(row).toContainText('Esito simulato:');
  await expect(row).toContainText('Una tua conversazione');
  await expect(row).not.toContainText('ORA si è mossa');
  await expect(row).not.toContainText('Non ho ancora cominciato');
  await expect(row).not.toContainText('originale non disponibile');
  await expect(row).not.toContainText('Capire quando la situazione');
  mkdirSync('mobile-qa', { recursive: true });
  await page.screenshot({ path: `mobile-qa/${info.project.name}-home-v108.png` });
});

test('a failed or missing control is visible even without executed work', async ({ page }) => {
  await openHome(page, { ...base, progress_kind: 'problem', show_in_updates: true, state: 'Il controllo programmato deve essere recuperato.' });
  const row = page.getByTestId('home-agent-gol_qa_home');
  await row.scrollIntoViewIfNeeded();
  await expect(row).toContainText('Controllo da verificare');
  await expect(row).toContainText('deve essere recuperato');
  await expect(row).not.toContainText('ORA si è mossa');
});
