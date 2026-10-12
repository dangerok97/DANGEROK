import { test, expect, type Page } from '@playwright/test';

// Real authentication/gate UI. Every API is intercepted with synthetic data;
// no provider, notification, account or telephone request leaves the fixture.
async function authenticatedRoute(page: Page) {
  let meStatus = 200;
  let logins = 0;
  let logouts = 0;
  const user = {
    user_id: 'qa_auth_recovery_v162', name: 'Persona di prova',
    first_name: 'Persona', last_name: 'Prova', email: 'auth-qa@example.invalid',
    provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1,
  };
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
    let status = 200;
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.endsWith('/auth/logout')) {
      logouts++;
      status = meStatus === 401 ? 401 : 200;
      json = status === 401 ? { detail: 'Invalid synthetic session' } : { ok: true };
    } else if (path.includes('/auth/') && request.method() === 'POST') {
      logins++;
      json = { token: 'synthetic-auth-session-not-a-credential', user };
    } else if (path.endsWith('/auth/me')) {
      status = meStatus;
      json = status === 200 ? user : { detail: status === 503 ? 'Synthetic connection unavailable' : 'Invalid synthetic session' };
    } else if (path.includes('home')) json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {} };
    else if (path.includes('knowledge-map')) json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0, percent: 0, revision: 'synthetic' };
    else if (path.includes('life-setup')) json = { enabled: false };
    else if (path.includes('location')) json = { preference: 'off', enabled: false, status: 'off' };
    await route.fulfill({ status, headers, json });
  });
  await page.goto('/login?next=%2Fprepara-chiamata');
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(user.email);
  await page.getByTestId('login-password-input').fill('SyntheticFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('login-submit-button')).not.toBeVisible({ timeout: 30000 });
  await page.goto('/prepara-chiamata');
  await expect(page.getByTestId('prep-request')).toBeVisible();
  return {
    setMeStatus: (value: number) => { meStatus = value; },
    logins: () => logins, logouts: () => logouts,
  };
}

test('a temporary verification failure keeps the session and requested route; retry recovers without another login', async ({ page }) => {
  const state = await authenticatedRoute(page);
  state.setMeStatus(503);
  await page.reload();
  const recovery = page.getByTestId('auth-session-recovery');
  await expect(recovery).toBeVisible();
  await expect(page).toHaveURL(/\/prepara-chiamata$/);
  await expect(page.getByTestId('login-email-button')).not.toBeVisible();
  await expect(recovery).toContainText('Non riesco a verificare la sessione');
  const retry = page.getByTestId('auth-recovery-notice-retry');
  await expect(retry).toBeEnabled();
  expect((await retry.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(state.logouts()).toBe(0);
  state.setMeStatus(200);
  await retry.click();
  await expect(page.getByTestId('prep-request')).toBeVisible();
  await expect(recovery).not.toBeVisible();
  await expect(page).toHaveURL(/\/prepara-chiamata$/);
  expect(state.logins()).toBe(1);
  expect(state.logouts()).toBe(0);
});

test('an actually invalid session signs out and preserves the destination for a new login', async ({ page }) => {
  const state = await authenticatedRoute(page);
  state.setMeStatus(401);
  await page.reload();
  await expect(page.getByTestId('login-email-button')).toBeVisible();
  await expect(page).toHaveURL(/\/login\?next=%2Fprepara-chiamata$/);
  await expect(page.getByTestId('auth-session-recovery')).not.toBeVisible();
  await expect.poll(state.logouts).toBe(1);
  // A reload must not resurrect the invalid credential or repeat its exit.
  await page.reload();
  await expect(page.getByTestId('login-email-button')).toBeVisible();
  await expect(page).toHaveURL(/\/login\?next=%2Fprepara-chiamata$/);
  expect(state.logins()).toBe(1);
  expect(state.logouts()).toBe(1);
});
