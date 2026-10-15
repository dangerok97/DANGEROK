import { test, expect, type Locator, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';

// Real exported ORA components; ALL API data is a deterministic offline fixture.
// No real account, calendar, notification, weather query or provider write occurs.
const sid = 'ces_mobile_qa_v93';
const warning = 'ATTENZIONE: questo avviso di prova verifica che il testo importante sia rosso e leggibile.';
async function fixture(page: Page, controls: { followup?: any; removeFails?: boolean; dismissed?: string[] } = {}) {
  let removed = false;
  const posts: string[] = [];
  const user = { user_id: 'qa_mobile_v93', name: 'Esempio di test', first_name: 'Esempio', last_name: 'Test', email: 'mobile-qa@example.invalid', provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1 };
  const history: any[] = [
    { role: 'user', text: 'Ho steso i panni', message_id: 'qa-user-1' },
    { role: 'ora', text: `${warning}\n\nQuesta conversazione è un esempio per collaudare la nuova interfaccia mobile, non una previsione meteo.\n\nLa risposta deve potersi leggere e scorrere senza essere coperta dal cervello. Anche una risposta lunga deve lasciare accessibile il campo di scrittura.\n\nLe fonti e i pulsanti in fondo devono essere raggiungibili scorrendo la conversazione. Nessun orario di asciugatura viene inventato in questo test.`, message_id: 'qa-ora-1', meta: { sources: Array.from({ length: 6 }, (_, i) => ({ title: `Documento di prova ${i + 1} — dati simulati`, url: `https://example.com/qa-${i + 1}` })) } },
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
    else if (path.endsWith('/dismiss')) {
      controls.dismissed?.push(path);
      if (controls.removeFails) { await route.fulfill({ status: 503, headers, json: { detail: 'Errore di prova' } }); return; }
      removed = true;
      json = { ok: true, status: 'success' };
    }
    else if (path.includes('knowledge-map')) json = {
      stars: [
        ...(!removed ? [{ id: 'star_qa_temp', area: 'memory', branch_id: null, title: 'Memoria temporanea', semantic_kind: 'Panni stesi', icon_key: 'shirt', statement: 'Panni stesi — dati simulati per collaudo UI', status: 'known', provenance: 'Dati simulati', temporary: true, situation_id: 'sit_qa_1', follow_up: controls.followup, updated_at: new Date().toISOString() }] : []),
        { id: 'star_qa_home', area: 'home', branch_id: null, title: 'Casa', statement: 'Informazione di prova', status: 'known', provenance: 'Dati simulati' },
      ], count: removed ? 1 : 2, known_count: removed ? 1 : 2, temporary_count: removed ? 0 : 1, percent: 21, branches: [], revision: removed ? 'qa-v99-removed' : 'qa-v99',
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

async function resizeAndScrollSituation(page: Page, detail: Locator, scroll: Locator, size: { width: number; height: number }) {
  await page.setViewportSize(size);
  // WebKit can finish resizing the viewport before useWindowDimensions has
  // switched the detail panel from full mobile width to its 330px wide layout.
  // Scrolling the previous width leaves the newly wrapped content below view.
  await expect.poll(async () => Math.round((await detail.boundingBox())?.width || 0))
    .toBe(size.width < 650 ? size.width - 24 : 330);
  await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await expect.poll(() => scroll.evaluate(element =>
    Math.abs(element.scrollHeight - element.clientHeight - element.scrollTop)))
    .toBeLessThanOrEqual(1);
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
    await expect(page.getByRole('button', { name: 'Avvisami', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Va bene', exact: true })).toHaveCount(0);
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
  // Visual evidence for the exact full-screen ORA brain surface on both engines.
  await page.screenshot({ path: `mobile-qa/${info.project.name}-brain-expanded.png` });
  await page.getByTestId('ora-mobile-close-map').click();
  await expect(input).toHaveValue('Bozza da conservare');
  await input.fill('');
  await input.blur();
  await scrollToBottom(page);
  await expect(page.getByRole('button', { name: 'Avvisami', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Va bene', exact: true })).toHaveCount(0);
  expect(posts).toEqual([]);
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

// V99: production mobile map -> the SAME Situation card used on desktop.
// API fixtures test rendering/selection/refresh only, not AI or background execution.
test('mobile selected Situation exposes real follow-up fields, scrolls and removes only on success', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 740 });
  const controls = { followup: { status: 'scheduled', next_check_at: '2026-10-07T15:00:00Z', next_check_label: '7 ott 2026, 17:00', timezone: 'Europe/Rome', last_checked_at: '2026-10-08T13:00:00+02:00', completion_when: 'Il risultato utile è raggiunto — condizione simulata', notify_when: 'Una variazione utile rilevata — condizione simulata' }, removeFails: true, dismissed: [] as string[] };
  const posts = await fixture(page, controls);
  await page.getByTestId('ora-mobile-open-map').click();
  const modal = page.getByTestId('ora-mobile-expanded-map');
  const card = modal.getByTestId('ora-cockpit-temporary');
  const detail = modal.getByTestId('ora-map-detail');
  const scroll = modal.getByTestId('ora-map-detail-scroll');
  await expect(card).toBeVisible();
  await expect(card).toContainText('PANNI STESI');
  await expect(card.getByTestId('ora-cockpit-outcome')).toContainText('Stima non ancora disponibile');
  await expect(card.getByText('Prossimo controllo', { exact: true })).toHaveCount(0);
  await card.getByRole('button', { name: 'Dettagli del controllo', exact: true }).click();
  await expect(card).toContainText('Controllo programmato');
  await expect(card).toContainText('Prossimo controllo');
  await expect(card).toContainText('Ultimo controllo eseguito');
  // Backend local projection wins even when the browser's timezone differs.
  await expect(card).toContainText('7 ott 2026, 17:00');
  await expect(card).not.toContainText('7 ott 2026, 15:00');
  await expect(card).toContainText('Ti avviso quando');
  await expect(card).toContainText('Il risultato utile è raggiunto — condizione simulata');
  await expect(card).toContainText('Ti avviso prima se');
  await expect(modal.getByText('Un punto della tua vita', { exact: true })).toHaveCount(0);
  mkdirSync('mobile-qa', { recursive: true });
  await page.screenshot({ path: `mobile-qa/${info.project.name}-situation-v99.png` });
  for (const size of [{ width: 320, height: 568 }, { width: 390, height: 740 }, { width: 740, height: 390 }]) {
    await resizeAndScrollSituation(page, detail, scroll, size);
    await expect(card.getByTestId('ora-remove-temporary')).toBeInViewport();
    await expect(modal.getByRole('button', { name: 'Chiudi dettagli del cervello' })).toBeInViewport();
    await expect(modal.getByTestId('ora-mobile-close-map')).toBeInViewport();
    const box = await detail.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(size.width + 1);
    expect(box!.y + box!.height).toBeLessThanOrEqual(size.height + 1);
  }
  await resizeAndScrollSituation(page, detail, scroll, { width: 390, height: 740 });
  await card.getByTestId('ora-remove-temporary').click();
  await expect(card).toContainText('Non sono riuscita a rimuovere');
  await expect(card).toBeVisible();
  controls.removeFails = false;
  await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await card.getByTestId('ora-remove-temporary').click();
  await expect(card).toHaveCount(0);
  await expect(modal.getByTestId('knowledge-map-progress')).toContainText('1 nodi');
  expect(controls.dismissed).toEqual(Array(2).fill('/api/life-profile/knowledge-map/situations/sit_qa_1/dismiss'));
  expect(posts).toEqual([]);
});

test('mobile follow-up starts unconfirmed and refreshes without a chat message', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 740 });
  const controls = { followup: { status: 'not_scheduled' } as any };
  const posts = await fixture(page, controls);
  await page.getByTestId('ora-mobile-open-map').click();
  const modal = page.getByTestId('ora-mobile-expanded-map');
  const card = modal.getByTestId('ora-cockpit-temporary');
  await card.getByRole('button', { name: 'Dettagli del controllo', exact: true }).click();
  await expect(card).toContainText('Nessun controllo programmato');
  await expect(card.getByText('Prossimo controllo', { exact: true })).toHaveCount(0);
  controls.followup = {
    status: 'review_pending',
    assessment_at: '2099-01-20T14:30:00+01:00',
    assessment_label: '20 gen 2099, 14:30',
    next_check_at: null,
  };
  await expect(card).toContainText('Valutazione presa in carico: controllo non ancora programmato', { timeout: 25000 });
  await expect(card).not.toContainText('Stato del controllo non verificabile');
  await expect(card.getByText('Prossimo controllo', { exact: true })).toHaveCount(0);
  controls.followup = { status: 'scheduled', next_check_at: '2026-10-08T14:30:00+02:00', completion_when: 'Quando il risultato utile è raggiunto', notify_when: 'Se prima cambia qualcosa di importante' };
  await expect(card).toContainText('Controllo programmato', { timeout: 25000 });
  await expect(card).toContainText('Prossimo controllo');
  await modal.getByRole('button', { name: 'Chiudi dettagli del cervello' }).click();
  await expect(card).toHaveCount(0);
  await modal.getByTestId('ora-mobile-close-map').click();
  expect(posts).toEqual([]);
});

test('mobile Situation keeps useful estimates and actions first through risk and watch completion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 740 });
  const observedAt = new Date();
  const controls = { followup: {
    status: 'scheduled',
    desired_outcome: 'Sapere quando ritirare i panni — esempio simulato',
    next_check_at: '2099-01-20T10:30:00+01:00',
    next_check_label: '20 gen 2099, 10:30',
    outcome: {
      status: 'estimated',
      headline: 'Ritiro stimato tra le 15:00 e le 16:00 — esempio simulato',
      action_summary: 'La finestra è una stima basata sui dati simulati del collaudo.',
      window_start: '2099-01-20T15:00:00+01:00',
      window_end: '2099-01-20T16:00:00+01:00',
      window_label: '20 gen 2099, 15:00–16:00',
      assessed_at: observedAt.toISOString(),
      valid_until: new Date(observedAt.getTime() + 3600000).toISOString(),
      situation_revision: 1,
      evidence_ids: ['evidence_offline_ui_fixture'],
      basis: 'estimate', action_reason: null, timezone: 'Europe/Rome',
    },
  } as any };
  const posts = await fixture(page, controls);
  await page.getByTestId('ora-mobile-open-map').click();
  const modal = page.getByTestId('ora-mobile-expanded-map');
  const card = modal.getByTestId('ora-cockpit-temporary');
  const result = card.getByTestId('ora-cockpit-outcome');
  await expect(result).toContainText('Ritiro stimato tra le 15:00 e le 16:00');
  await expect(result.getByTestId('ora-cockpit-outcome-window')).toContainText('20 gen 2099, 15:00–16:00');
  await expect(result).toContainText('Valutazione stimata');
  await expect(result).not.toContainText('10:30');
  await expect(card.getByText('Prossimo controllo', { exact: true })).toHaveCount(0);
  const toggle = card.getByRole('button', { name: 'Dettagli del controllo', exact: true });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(card).toContainText('20 gen 2099, 10:30');
  await toggle.click();

  controls.followup.outcome = {
    ...controls.followup.outcome,
    status: 'action_now', action_reason: 'early_risk',
    headline: 'Ritira adesso: rischio pioggia — esempio simulato',
    action_summary: 'Il ritiro anticipato evita che i panni si bagnino; l’asciugatura resta stimata.',
  };
  await expect(result).toContainText('Ritira adesso: rischio pioggia', { timeout: 25000 });
  await expect(result.getByTestId('ora-cockpit-outcome-window')).toHaveCount(0);
  await expect(result).not.toContainText('Ritiro stimato tra le 15:00');
  await expect(result).not.toContainText('osservazione diretta');
  // A finished watch can be delivering the action it was asked to identify.
  // Stopping the watch must not swallow its still-current final result.
  controls.followup.status = 'stopped';
  controls.followup.outcome = {
    ...controls.followup.outcome,
    action_reason: 'outcome_ready',
    headline: 'Puoi ritirarli adesso secondo la stima aggiornata — esempio simulato',
    action_summary: 'La valutazione è conclusa; il ritiro fisico non è stato osservato.',
  };
  await expect(result).toContainText('Puoi ritirarli adesso secondo la stima aggiornata', { timeout: 25000 });
  await expect(result).not.toContainText('Non sono previsti altri controlli');
  await expect(result).toContainText('Valutazione stimata');
  expect(posts).toEqual([]);
});
