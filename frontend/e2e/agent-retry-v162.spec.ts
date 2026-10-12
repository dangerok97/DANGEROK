import { test, expect, type Page } from '@playwright/test';

// Real screen, synthetic account and API. Never reaches a provider or sends a push.
async function openGoal(page: Page, canRetry = true) {
  let retries = 0;
  let failNext = true;
  let queued = false;
  const goalId = 'gol_synthetic_retry_v162';
  const user = {
    user_id: 'qa_retry_v162', name: 'Persona di prova',
    email: 'retry-qa@example.invalid', provider: 'password',
    identity_confirmed: true, knowledge_tutorial_version: 1,
  };
  const goal = () => ({
    id: goalId, what: 'Preparare il riepilogo della nota sintetica',
    outcome: 'Un riepilogo verificabile', source: 'Nota sintetica',
    state: queued ? 'Ripresa programmata' : canRetry ? 'Il lavoro è sospeso' : 'Il lavoro è in corso',
    planning_unavailable: canRetry && !queued,
    retry_available: canRetry && !queued,
    needs_you: '', created_at: '2026-01-01T10:00:00Z',
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
    let json: unknown = {};
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.includes('/auth/') && request.method() === 'POST') json = { token: 'synthetic-retry-not-a-credential', user };
    else if (path.endsWith('/auth/me')) json = user;
    else if (path === `/api/agent/${goalId}`) json = goal();
    else if (path === `/api/agent/${goalId}/retry` && request.method() === 'POST') {
      retries++;
      if (failNext) {
        failNext = false;
        await route.fulfill({ status: 503, headers, json: { detail: 'Ripresa temporaneamente non disponibile.' } });
        return;
      }
      queued = true;
      json = { ok: true, state: 'scheduled', goal_id: goalId };
    } else if (path.includes('home')) json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], agent_work: [goal()], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {} };
    else if (path.includes('life-setup')) json = { enabled: false };
    else if (path.includes('knowledge-map')) json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0, percent: 0, revision: 'synthetic' };
    else if (path.includes('location')) json = { preference: 'off', enabled: false, status: 'off' };
    await route.fulfill({ status: 200, headers, json });
  });
  await page.goto('/login');
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(user.email);
  await page.getByTestId('login-password-input').fill('SyntheticFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('login-submit-button')).not.toBeVisible({ timeout: 30000 });
  await page.goto(`/aggiornamento/${goalId}`);
  await expect(page.getByTestId('dettaglio-cosa')).toBeVisible();
  return { attempts: () => retries };
}

test('suspended work can recover a failed retry and preserves the scheduled result on reload', async ({ page }) => {
  const state = await openGoal(page);
  const retry = page.getByTestId('riprova-lavoro');
  await expect(retry).toBeVisible();
  await retry.click();
  await expect(page.getByTestId('dettaglio-ripresa').getByRole('alert')).toBeVisible();
  await expect(retry).toBeEnabled();
  expect(state.attempts()).toBe(1);
  await retry.click();
  await expect(page.getByTestId('dettaglio-stato')).toContainText('Ripresa programmata');
  await expect(retry).not.toBeVisible();
  expect(state.attempts()).toBe(2);
  await page.reload();
  await expect(page.getByTestId('dettaglio-stato')).toContainText('Ripresa programmata');
  await expect(retry).not.toBeVisible();
  expect(state.attempts()).toBe(2);
});

test('a normal active goal offers no retry and opening it starts no work', async ({ page }) => {
  const state = await openGoal(page, false);
  await expect(page.getByTestId('dettaglio-stato')).toContainText('Il lavoro è in corso');
  await expect(page.getByTestId('riprova-lavoro')).not.toBeVisible();
  expect(state.attempts()).toBe(0);
});
