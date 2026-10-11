import { test, expect, type Locator, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import type { MissionPreparation } from '../src/api/client';

// Real exported screen; every API response and contact below is synthetic.
// No call is prepared or placed, and external network requests are blocked.
const contactName = 'Alessandra Contatto Esempio';
const contactNumber = '+390000000000';
const numberNote = 'Userò questo numero: l’hai confermato tu.';
const preparationId = 'prep_responsive_synthetic';

function preparation(confirmed = false): MissionPreparation {
  return {
    preparation_id: preparationId,
    you_asked: 'Chiedi al contatto sintetico di spostare la partita di prova.',
    goal: 'Spostare una partita di prova', counterparty: contactName,
    status_label: confirmed ? 'Numero confermato' : 'Confermi questo numero?',
    says: 'Verifica il contatto sintetico prima di proseguire.',
    contact: {
      name: contactName, number: contactNumber, source_label: 'Rubrica sintetica',
      source_detail: 'Dati simulati per verificare la leggibilità', why: 'Contatto di prova',
    },
    candidates: [], other_candidates: [], number_confirmed: confirmed,
    number_rejected: false, number_note: confirmed ? numberNote : '',
    number_conflict: false, what_ora_knows: [], question: null,
    ready: confirmed, can_call: confirmed,
    summary: confirmed ? 'Chiamata di prova pronta; il test non la avvia.' : '',
    you_can_answer: confirmed ? ['change_number', 'call'] : ['confirm_number'],
    created_at: '2026-01-01T10:00:00Z', updated_at: '2026-01-01T10:00:00Z',
  };
}

async function openPreparation(page: Page) {
  const confirmations: unknown[] = [];
  const callRequests: string[] = [];
  const user = {
    user_id: 'qa_preparation_responsive', name: 'Persona di prova',
    first_name: 'Persona', last_name: 'Prova', email: 'preparation-qa@example.invalid',
    provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1,
  };
  await page.route(url => !['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http'), route => route.abort());
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const headers = {
      'access-control-allow-origin': request.headers()['origin'] || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
      vary: 'Origin',
    };
    if (method === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    let json: unknown = {};
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.includes('/auth/') && method === 'POST') json = { token: 'offline-preparation-fixture-not-a-credential', user };
    else if (path.endsWith('/me') || path.endsWith('/auth/user')) json = user;
    else if (path === '/api/preparation/start') json = { ok: true, preparation: preparation() };
    else if (path === `/api/preparation/${preparationId}/confirm-number`) {
      confirmations.push(request.postDataJSON());
      json = { ok: true, preparation: preparation(true) };
    } else if (method !== 'GET' && (
      /^\/api\/telephone(?:\/|$)/.test(path)
      || /\/calls?(?:\/|$)/.test(path)
      || path.endsWith('/prepare-call')
    )) {
      callRequests.push(path);
      await route.fulfill({ status: 409, headers, json: { detail: 'Calls are not part of this offline layout test.' } });
      return;
    } else if (path.includes('home')) json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {} };
    else if (path.includes('knowledge-map')) json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0, percent: 0, revision: 'synthetic' };
    else if (path === '/api/places') json = { places: [], candidates: [], routines: [], pending_candidates: false, permission: { preference: 'off', state: 'off' } };
    else if (path === '/api/financial/overview') json = { collegamento: { stato: 'non_collegato', in_parole: 'Nessuna banca collegata.' }, conti: [], cosa_ho_capito: [], fonti_non_piu_collegate: [], collegato_alla_tua_vita: [], da_capire: [], movimenti_recenti: [], vale_la_pena_mostrarlo: false };
    else if (path.includes('opportunit')) json = { opportunities: [] };
    else if (path.includes('location')) json = { preference: 'off', enabled: false, status: 'off' };
    else if (path.includes('call')) json = { calling: false };
    await route.fulfill({ status: 200, headers, json });
  });
  await page.goto('/login?next=%2Fprepara-chiamata');
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(user.email);
  await page.getByTestId('login-password-input').fill('OfflineFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('login-submit-button')).not.toBeVisible({ timeout: 30000 });
  await page.goto('/prepara-chiamata');
  await page.getByTestId('prep-request').fill('Chiedi al contatto sintetico di spostare la partita di prova.');
  await page.getByTestId('prep-who').fill(contactName);
  await page.getByTestId('prep-start').click();
  await expect(page.getByTestId('prep-contact')).toBeVisible();
  return { confirmations, callRequests };
}

async function readableText(locator: Locator, maxLines: number, minFontSize = 14) {
  const metrics = await locator.evaluate(element => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const rects = [...range.getClientRects()].filter(rect => rect.width > 0 && rect.height > 0);
    const bounds = element.getBoundingClientRect();
    return {
      lines: new Set(rects.map(rect => Math.round(rect.top))).size,
      fontSize: parseFloat(getComputedStyle(element).fontSize),
      leftOverflow: Math.max(0, bounds.left - Math.min(...rects.map(rect => rect.left))),
      rightOverflow: Math.max(0, Math.max(...rects.map(rect => rect.right)) - bounds.right),
      widthOverflow: element.scrollWidth - element.clientWidth,
    };
  });
  expect(metrics.lines, 'The complete text must render on readable lines.').toBeGreaterThan(0);
  expect(metrics.lines, 'Words and the phone number must not collapse into individual letters.').toBeLessThanOrEqual(maxLines);
  expect(metrics.fontSize, 'Keep the contact readable without shrinking its font.').toBeGreaterThanOrEqual(minFontSize);
  expect(metrics.leftOverflow, 'The text must not clip beyond its box.').toBeLessThanOrEqual(1);
  expect(metrics.rightOverflow, 'The text must not clip beyond its box.').toBeLessThanOrEqual(1);
  expect(metrics.widthOverflow, 'The text must not need horizontal scrolling.').toBeLessThanOrEqual(1);
}

async function contained(child: Locator, parent: Locator) {
  const [inner, outer] = await Promise.all([child.boundingBox(), parent.boundingBox()]);
  expect(inner).not.toBeNull();
  expect(outer).not.toBeNull();
  expect(inner!.width).toBeGreaterThan(0);
  expect(inner!.x).toBeGreaterThanOrEqual(outer!.x - 1);
  expect(inner!.x + inner!.width).toBeLessThanOrEqual(outer!.x + outer!.width + 1);
  expect(inner!.y).toBeGreaterThanOrEqual(outer!.y - 1);
  expect(inner!.y + inner!.height).toBeLessThanOrEqual(outer!.y + outer!.height + 1);
}

for (const size of [{ width: 320, height: 740 }, { width: 390, height: 844 }, { width: 740, height: 390 }, { width: 1024, height: 900 }, { width: 1440, height: 1000 }]) {
  test(`preparation contact stays readable before and after confirmation at ${size.width}x${size.height}`, async ({ page }, info) => {
    // Set the viewport before mounting the responsive screen, avoiding a
    // measurement of the previous React layout immediately after a resize.
    await page.setViewportSize(size);
    const controls = await openPreparation(page);
    const contact = page.getByTestId('prep-contact');
    const card = contact.locator('..');
    const name = contact.getByText(contactName, { exact: true });
    const number = contact.getByTestId('prep-number');

    for (const confirmed of [false, true]) {
      await expect(name).toHaveText(contactName);
      await expect(number).toHaveText(contactNumber);
      await readableText(name, contactName.split(' ').length, 18);
      await readableText(number, 1);
      await contained(contact, card);
      await contained(name, contact);
      await contained(number, contact);
      const status = card.getByText(confirmed ? 'Numero verificato' : 'Da confermare', { exact: true });
      await expect(status).toBeVisible();
      await contained(status.locator('..'), card);
      await readableText(status, 2, 12);
      if (confirmed) {
        const note = card.getByText(numberNote, { exact: true });
        await expect(note).toBeVisible();
        await contained(note, card);
        await readableText(note, 4, 12);
      }

      const actions = confirmed ? ['prep-change-number', 'prep-wrong-number'] : ['prep-confirm-yes', 'prep-confirm-no'];
      for (const id of actions) {
        const button = page.getByTestId(id);
        await contained(button, card);
        if (!confirmed) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
        await readableText(button.locator('div').last(), 2);
      }
      const box = await card.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(size.width + 1);
      await contact.scrollIntoViewIfNeeded();
      mkdirSync('mobile-qa', { recursive: true });
      await page.screenshot({ path: `mobile-qa/preparation-${info.project.name}-${size.width}-${confirmed ? 'confirmed' : 'unconfirmed'}.png` });

      if (!confirmed) {
        await page.getByTestId('prep-confirm-yes').click();
        await expect(page.getByTestId('prep-confirm-yes')).toHaveCount(0);
        await expect(page.getByTestId('prep-make-call')).toBeVisible();
      }
    }
    expect(controls.confirmations).toEqual([{ yes: true, operation: 'reschedule' }]);
    expect(controls.callRequests).toEqual([]);
  });
}
