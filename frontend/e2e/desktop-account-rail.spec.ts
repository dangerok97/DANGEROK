import { expect, test, type Page } from '@playwright/test';

// Desktop/account shell regression. Real exported components, synthetic API.
// No account, provider or external service is contacted by this fixture.
async function accountFixture(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-account-navigation'));
  });
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const origin = route.request().headers().origin || 'http://127.0.0.1:8093';
    const headers = {
      'access-control-allow-origin': origin,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    };
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers });
      return;
    }
    const user = {
      user_id: 'synthetic-account-owner', name: 'Persona di prova',
      email: 'qa-account@example.invalid', provider: 'password',
      identity_confirmed: true, knowledge_tutorial_version: 1,
    };
    let result: unknown = {};
    if (path.endsWith('/auth/me')) result = user;
    else if (path.includes('whatsapp') && path.includes('status'))
      result = { linked: false, configured: false };
    else if (path.includes('calendar') && (path.includes('instances') || path.includes('calendars')))
      result = { items: [] };
    else if (path.includes('gmail') && path.includes('instances'))
      result = { items: [] };
    else if (path.includes('connected-sources'))
      result = { sources: [] };
    else if (path.includes('life-setup'))
      result = { enabled: false, completed: true };
    await route.fulfill({ status: 200, headers, json: result });
  });
  await page.route(url => {
    if (!url.protocol.startsWith('http')) return false;
    return !['localhost', '127.0.0.1'].includes(url.hostname)
      && !new URL(url.toString()).pathname.startsWith('/api/');
  }, route => route.abort());
}

async function expectSeparatedRail(page: Page, contentTestID: string) {
  const rail = page.getByTestId('ambient-rail');
  const content = page.getByTestId(contentTestID);
  await expect(rail).toBeVisible();
  await expect(rail).toHaveCount(1);
  await expect(content).toBeVisible();
  const bounds = await rail.boundingBox();
  const pageBounds = await content.boundingBox();
  expect(bounds && pageBounds).toBeTruthy();
  expect(bounds!.x).toBeLessThanOrEqual(2);
  expect(pageBounds!.x).toBeGreaterThanOrEqual(bounds!.x + bounds!.width - 3);
}

test('desktop Settings and account subpages retain one fixed left menu on navigation and reload', async ({ page }) => {
  await page.setViewportSize({ width: 1512, height: 900 });
  await accountFixture(page);
  await page.goto('/settings');
  await expectSeparatedRail(page, 'settings');
  await expect(page.getByTestId('whatsapp-connection')).toBeVisible();
  await expect(page.getByTestId('rail-account')).toBeVisible();
  await page.reload();
  await expectSeparatedRail(page, 'settings');

  await page.goto('/account/privacy');
  await expectSeparatedRail(page, 'account-privacy');
  await page.goto('/manage-calendars?instance=synthetic-calendar');
  await expectSeparatedRail(page, 'manage-calendars');
  await expect(page.getByText('Gestisci calendari')).toBeVisible();
});

test('narrow Settings retains its readable mobile route without a desktop rail', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await accountFixture(page);
  await page.goto('/settings');
  await expect(page.getByTestId('settings')).toBeVisible();
  await expect(page.getByTestId('ambient-rail')).toHaveCount(0);
  await expect(page.getByTestId('subpage-back')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await page.goto('/manage-calendars?instance=synthetic-calendar');
  await expect(page.getByTestId('manage-calendars')).toBeVisible();
  await expect(page.getByTestId('ambient-rail')).toHaveCount(0);
});
