import { test, expect, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';

// Real exported ORA components; ALL API data is a deterministic offline fixture.
// No real account, calendar, notification, weather query or provider write occurs.
const sid = 'ces_mobile_qa_v93';
const warning = 'ATTENZIONE: questo avviso di prova verifica che il testo importante sia rosso e leggibile.';
async function fixture(page: Page) {
  const posts: string[] = [];
  const user = { user_id: 'qa_mobile_v93', name: 'Esempio di test', first_name: 'Esempio', last_name: 'Test', email: 'mobile-qa@example.invalid', provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1 };
  const history: any[] = [
    { role: 'user', text: 'Ho steso i panni', message_id: 'qa-user-1' },
    { role: 'ora', text: `${warning}\n\nQuesta conversazione è un esempio per collaudare la nuova interfaccia mobile, non una previsione meteo.\n\nLa risposta deve potersi leggere e scorrere senza essere coperta dalla mappa. Anche una risposta lunga deve lasciare accessibile il campo di scrittura.\n\nLe fonti e i pulsanti in fondo devono essere raggiungibili scorrendo la conversazione. Nessun orario di asciugatura viene inventato in questo test.`, message_id: 'qa-ora-1', meta: { sources: Array.from({ length: 6 }, (_, i) => ({ title: `Documento di prova ${i + 1} — dati simulati`, url: `https://example.com/qa-${i + 1}` })) } },
  ];
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const requestOrigin = request.headers()['origin'] || 'http://127.0.0.1:8093';
    const headers = {
      'access-control-allow-origin': requestOrigin,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
      'vary': 'Origin',
    };
    if (method === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    let json: any = {};
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.includes('/auth/') && method === 'POST') json = { token: 'offline-qa-token-not-a-credential', user };
    else if (path.endsWith('/me') || path.endsWith('/auth/user')) json = user;
    else if (path.includes('knowledge-map')) json = {
      stars: [
        { id: 'star_qa_temp', area: 'memory', branch_id: null, title: 'Memoria temporanea', statement: 'Ho steso i panni — esempio di test', status: 'known', provenance: 'Dati simulati', temporary: true, situation_id: 'sit_qa_1', updated_at: new Date().toISOString() },
        { id: 'star_qa_home', area: 'home', branch_id: null, title: 'Casa', statement: 'Informazione di prova', status: 'known', provenance: 'Dati simulati' },
      ], count: 2, known_count: 2, temporary_count: 1, percent: 21, branches: [], revision: 'qa-v93',
    };
    else if (path.includes(sid) || /ai.?core|ai\/core/i.test(path)) {
      if (method === 'POST') {
        const body = request.postData() || '';
        posts.push(body);
        history.push({ role: 'user', text: 'Avvisami quando devo intervenire per questa situazione.', message_id: 'qa-user-2' });
        history.push({ role: 'ora', text: 'Risposta simulata: il pulsante ha inviato il messaggio nella stessa conversazione.', message_id: 'qa-ora-2' });
      }
      json = { ok: true, session_id: sid, history, ora_text: history[history.length - 1].text, sources: [], ui_actions: [] };
    }
    else if (path.includes('home')) json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {}, generated_at: new Date().toISOString() };
    else if (path === '/api/places') json = {
      places: [], candidates: [], routines: [], pending_candidates: false,
      permission: { preference: 'off', state: 'off' },
    };
    else if (path === '/api/financial/overview') json = {
      collegamento: { stato: 'non_collegato', in_parole: 'Nessuna banca collegata.' },
      conti: [], cosa_ho_capito: [], fonti_non_piu_collegate: [],
      collegato_alla_tua_vita: [], da_capire: [], movimenti_recenti: [],
      vale_la_pena_mostrarlo: false,
    };
    else if (path.includes('opportunit')) json = { opportunities: [] };
    else if (path.includes('location')) json = { preference: 'off', enabled: false, status: 'off' };
    else if (path.includes('call')) json = { calling: false };
    await route.fulfill({ status: 200, headers, json });
  });
  // Prevent a test fixture from ever making a real provider call.
  await page.route(url => !['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http'), route => route.abort());
  await page.goto(`/login?next=${encodeURIComponent('/ora/' + sid)}`);
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill('mobile-qa@example.invalid');
  await page.getByTestId('login-password-input').fill('OfflineFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('login-submit-button')).not.toBeVisible({ timeout: 30000 });
  await page.goto(`/ora/${sid}`);
  await expect(page.getByTestId('ora-mobile-conversation-panel')).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(warning, { exact: true })).toBeVisible();
  return posts;
}

async function scrollToBottom(page: Page) {
  await page.getByTestId('ora-production-scroll').evaluate(element => { element.scrollTop = element.scrollHeight; });
}

test('mobile conversation is readable, scrollable, and preserves draft through map expansion', async ({ page }, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => {
    const message = String(error.message || '');
    // WebKit 26 may emit a spurious CORS pageerror for a Playwright-fulfilled
    // loopback fixture even though the request is intercepted and the UI
    // continues correctly. Ignore only this exact local-QA engine noise;
    // every other runtime error still fails the test.
    if (
      message.includes('due to access control checks') &&
      message.includes('127.0.0.1:8093/api/')
    ) return;
    errors.push(message);
  });
  await page.setViewportSize({ width: 390, height: 740 });
  const posts = await fixture(page);
  mkdirSync('mobile-qa', { recursive: true });
  for (const size of [{ width: 320, height: 568 }, { width: 390, height: 740 }, { width: 416, height: 707 }]) {
    await page.setViewportSize(size);
    const panel = await page.getByTestId('ora-mobile-conversation-panel').boundingBox();
    const composer = await page.getByTestId('ora-production-composer').boundingBox();
    expect(panel!.height).toBeGreaterThan(180);
    expect(composer!.y + composer!.height).toBeLessThanOrEqual(size.height + 2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width + 2);
    await scrollToBottom(page);
    await expect(page.getByRole('button', { name: 'Avvisami', exact: true })).toBeInViewport();
  }
  await page.setViewportSize({ width: 390, height: 740 });
  await page.getByTestId('ora-production-scroll').evaluate(element => { element.scrollTop = 0; });
  const red = await page.getByText(warning, { exact: true }).evaluate(element => getComputedStyle(element).color);
  const rgb = red.match(/[\d.]+/g)!.map(Number);
  expect(rgb[0]).toBeGreaterThan(rgb[1] * 1.15);
  await page.screenshot({ path: `mobile-qa/${info.project.name}-chat.png` });
  await scrollToBottom(page);
  await page.screenshot({ path: `mobile-qa/${info.project.name}-azioni.png` });
  const input = page.getByTestId('ora-production-composer-input');
  await input.fill('Bozza da conservare');
  await page.getByTestId('ora-mobile-open-map').click();
  await expect(page.getByTestId('ora-mobile-expanded-map')).toBeVisible();
  await page.getByTestId('ora-mobile-close-map').click();
  await expect(input).toHaveValue('Bozza da conservare');
  await input.fill('');
  await input.blur();
  await scrollToBottom(page);
  await page.getByRole('button', { name: 'Avvisami', exact: true }).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toContain('Avvisami');
  expect(posts[0]).toContain('client_message_id');
  expect(errors).toEqual([]);
});

test('keyboard visual viewport and landscape keep composer inside visible area', async ({ page }) => {
  await page.addInitScript(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let overriddenHeight: number | null = null;
    Object.defineProperty(vv, 'height', { configurable: true, get: () => overriddenHeight ?? window.innerHeight });
    (window as any).__qaViewportHeight = (height: number) => { overriddenHeight = height; vv.dispatchEvent(new Event('resize')); };
  });
  await page.setViewportSize({ width: 390, height: 740 });
  await fixture(page);
  await page.getByTestId('ora-production-composer-input').fill('Messaggio con tastiera aperta');
  await page.evaluate(() => (window as any).__qaViewportHeight(360));
  await expect.poll(async () => (await page.getByTestId('ora-presence').first().boundingBox())!.height).toBeLessThanOrEqual(360);
  await expect(page.getByTestId('ora-mobile-map-preview')).not.toBeVisible();
  const composer = await page.getByTestId('ora-production-composer').boundingBox();
  expect(composer!.y + composer!.height).toBeLessThanOrEqual(362);
  await page.getByTestId('ora-production-composer-input').blur();
  await page.evaluate(() => (window as any).__qaViewportHeight(390));
  await page.setViewportSize({ width: 740, height: 390 });
  await expect(page.getByTestId('ora-mobile-map-preview')).not.toBeVisible();
  await expect(page.getByTestId('ora-production-composer-input')).toBeInViewport();
});
