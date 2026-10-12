import { test, expect, type Page } from '@playwright/test';

const goalId = 'gol_synthetic_prepared_review_v162';
const draft = 'Confronto sintetico sulle condizioni annotate, con i limiti della fonte.';
const partialReview = {
  outcome: 'partial',
  what_is_missing: 'Il confronto non esplicita il periodo considerato.',
  reasoning: 'Una premessa necessaria resta implicita.',
  reviewed_at: '2026-10-12T03:00:00+00:00',
};

// The real detail screen reads only synthetic API responses. No provider,
// real account, push or work mutation is reached by opening a prepared result.
async function openPrepared(page: Page, initial: Record<string, unknown>) {
  let overrides = initial;
  const mutations: string[] = [];
  const user = {
    user_id: 'qa_prepared_review_v162', name: 'Persona di prova',
    email: 'prepared-review@example.invalid', provider: 'password',
    identity_confirmed: true, knowledge_tutorial_version: 1,
  };
  const goal = () => ({
    id: goalId, what: 'Confrontare la nota sintetica', source: 'Nota sintetica per QA',
    outcome: 'Un confronto con premesse esplicite', state: 'Il lavoro è in corso',
    needs_you: '', created_at: '2026-01-01T10:00:00Z',
    prepared_text: draft, prepared_review: null,
    ...overrides,
  });
  await page.route(url => !['127.0.0.1', 'localhost'].includes(url.hostname) && url.protocol.startsWith('http'), route => route.abort());
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const headers = {
      'access-control-allow-origin': request.headers().origin || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    };
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers }); return;
    }
    if (path.startsWith('/api/agent/') && request.method() !== 'GET') mutations.push(`${request.method()} ${path}`);
    let json: unknown = {};
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.includes('/auth/') && request.method() === 'POST') json = { token: 'synthetic-prepared-review-not-a-credential', user };
    else if (path.endsWith('/auth/me')) json = user;
    else if (path === `/api/agent/${goalId}`) json = goal();
    else if (path.includes('home')) json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], agent_work: [goal()], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {} };
    else if (path.includes('life-setup')) json = { enabled: false };
    else if (path.includes('knowledge-map')) json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0, percent: 0, revision: 'synthetic' };
    else if (path.includes('location')) json = { preference: 'off', enabled: false, status: 'off' };
    await route.fulfill({ status: 200, headers, json });
  });
  const monthRead = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/calendar/events/home/month');
  await page.goto('/login');
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(user.email);
  await page.getByTestId('login-password-input').fill('SyntheticFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('login-submit-button')).not.toBeVisible({ timeout: 30000 });
  await monthRead;
  // Login briefly renders Home. Let its actual calendar callback settle so
  // a fast local navigation cannot hide malformed-data errors seen in CI.
  await expect(page.getByTestId('home-context-rail')).toHaveAttribute('aria-busy', 'false');
  await page.goto(`/aggiornamento/${goalId}`);
  await expect(page.getByTestId('dettaglio-cosa')).toBeVisible();
  return { mutations, update: (next: Record<string, unknown>) => { overrides = next; } };
}

for (const example of [
  { name: 'partial', review: partialReview, title: 'Bozza da rivedere', detail: partialReview.what_is_missing },
  { name: 'uncertain', review: { ...partialReview, outcome: 'uncertain', what_is_missing: '' },
    title: 'Verifica ancora incerta', detail: partialReview.reasoning },
]) test(`${example.name} review is qualified and displayed above its prepared text`, async ({ page }, testInfo) => {
  const state = await openPrepared(page, { prepared_review: example.review });
  const review = page.getByTestId('dettaglio-revisione-preparazione');
  const result = page.getByTestId('dettaglio-risultato');
  await expect(review.getByText(example.title, { exact: true })).toBeVisible();
  await expect(review.getByText('Giudizio della verifica', { exact: true })).toBeVisible();
  await expect(review.getByText(example.detail, { exact: true })).toBeVisible();
  await expect(result.getByText(draft, { exact: true })).toBeVisible();
  await expect(page.getByTestId('dettaglio-stato')).toContainText('Il lavoro è in corso');
  await expect(page.getByTestId('riprova-lavoro')).not.toBeVisible();
  await review.scrollIntoViewIfNeeded();
  const reviewBox = await review.boundingBox();
  const resultBox = await result.boundingBox();
  expect(reviewBox).not.toBeNull();
  expect(resultBox).not.toBeNull();
  expect(reviewBox!.y + reviewBox!.height).toBeLessThanOrEqual(resultBox!.y);
  await page.screenshot({ path: testInfo.outputPath(`prepared-${example.name}.png`), fullPage: true });
  expect(state.mutations).toEqual([]);
});

test('a saved draft for approval remains visible without a negative review', async ({ page }) => {
  const state = await openPrepared(page, {
    state: 'È tutto pronto, mi serve il tuo via libera.', needs_you: 'Serve il tuo via libera.',
    action: { label: 'Rivedi e conferma', route: '/ora', params: { goalId } },
  });
  await expect(page.getByTestId('dettaglio-risultato').getByText(draft, { exact: true })).toBeVisible();
  await expect(page.getByTestId('dettaglio-revisione-preparazione')).not.toBeVisible();
  await expect(page.getByTestId('dettaglio-serve')).toContainText('Serve il tuo via libera.');
  await expect(page.getByRole('button', { name: 'Rivedi e conferma', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('dettaglio-risultato').getByText(draft, { exact: true })).toBeVisible();
  await expect(page.getByTestId('dettaglio-revisione-preparazione')).not.toBeVisible();
  expect(state.mutations).toEqual([]);
});

test('malformed review or draft data does not crash the detail or invent a judgement', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = await openPrepared(page, {
    prepared_review: { ...partialReview, what_is_missing: { unsupported: 'not display text' } },
  });
  await expect(page.getByTestId('dettaglio-risultato').getByText(draft, { exact: true })).toBeVisible();
  await expect(page.getByTestId('dettaglio-revisione-preparazione')).not.toBeVisible();
  state.update({ prepared_text: { text: draft }, prepared_review: partialReview });
  await page.reload();
  await expect(page.getByTestId('dettaglio-cosa')).toBeVisible();
  await expect(page.getByTestId('dettaglio-risultato')).not.toBeVisible();
  await expect(page.getByTestId('dettaglio-revisione-preparazione')).not.toBeVisible();
  expect(errors).toEqual([]);
  expect(state.mutations).toEqual([]);
});
