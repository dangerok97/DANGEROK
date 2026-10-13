import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

// Real exported UI; synthetic API, identities and barcode. No real account.
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASkAAABkCAIAAABVSlHTAAAABmJLR0QA/wD/AP+gvaeTAAABaElEQVR4nO3TMQ6DMBAAwTj//7PTUcQSAidom5kSfD4ktGPO+XrGGOPrybHreLVuX6fW8Vsr9sb/dWZv/NY9t8b3ptZXq5N/up7ZW7r3PVd27a340fuhe4Fz2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qChPWhoDxrag4b2oKE9aGgPGtqDhvagoT1oaA8a2oOG9qDxAWKxRcVqtwaBAAAAAElFTkSuQmCC';

async function fixture(page: Page) {
  let cards: Record<string, any>[] = [];
  await page.addInitScript(() => localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-wallet-session')));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const headers = { 'access-control-allow-origin': request.headers().origin || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS', 'cache-control': 'no-store' };
    if (request.method() === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    let result: unknown = {};
    if (path.endsWith('/auth/me')) result = { user_id: 'synthetic-wallet-owner', name: 'Persona di prova',
      email: 'wallet-qa@example.invalid', provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1 };
    else if (path.includes('life-setup')) result = { enabled: false, completed: true };
    else if (path === '/api/wallet/cards' && request.method() === 'PUT') {
      const input = request.postDataJSON();
      expect(input.code).toBe('00012345');
      expect(input.static_confirmed).toBe(true);
      const card = { ...input, revision: input.revision + 1, image, acceptance: 'not_verified_at_checkout',
        created_at: '2026-10-13T12:00:00Z', updated_at: '2026-10-13T12:00:00Z' };
      cards = [...cards.filter(c => c.id !== card.id), card];
      result = { card };
    } else if (path === '/api/wallet/cards') result = { cards };
    else if (path.startsWith('/api/wallet/cards/') && request.method() === 'DELETE') {
      cards = cards.filter(c => c.id !== path.split('/').pop()); result = { deleted: true };
    }
    await route.fulfill({ status: 200, headers, json: result });
  });
  await page.route(url => url.protocol.startsWith('http') && !['localhost', '127.0.0.1'].includes(url.hostname)
    && !url.pathname.startsWith('/api/'), route => route.abort());
}

test('phone wallet creates, displays without another API call, edits and deletes a static card', async ({ page, context }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto('/portafoglio');
  await expect(page.getByTestId('wallet-empty')).toBeVisible();
  await page.getByTestId('wallet-add').click();
  await page.getByTestId('wallet-name').fill('Supermercato prova');
  await page.getByTestId('wallet-code').fill('00012345');
  await expect(page.getByTestId('wallet-save')).toBeDisabled();
  await page.getByTestId('wallet-static').click();
  await page.getByTestId('wallet-save').click();
  await expect(page.getByTestId('wallet-card-detail')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await context.setOffline(true);
  await page.getByTestId('wallet-checkout').click();
  await expect(page.getByTestId('wallet-close-checkout')).toBeVisible();
  await expect(page.getByText('00012345', { exact: true }).last()).toBeVisible();
  fs.mkdirSync('mobile-qa', { recursive: true });
  await page.screenshot({ path: `mobile-qa/wallet-checkout-${info.project.name}.png`, fullPage: true });
  await page.getByTestId('wallet-close-checkout').click();
  await context.setOffline(false);
  await page.getByRole('button', { name: 'Modifica', exact: true }).click();
  await page.getByTestId('wallet-name').fill('Tessera aggiornata');
  await page.getByTestId('wallet-save').click();
  await expect(page.getByTestId('wallet-card-detail')).toContainText('Tessera aggiornata');
  await page.getByRole('button', { name: 'Tutte le tessere', exact: true }).click();
  await page.getByTestId('wallet-search').fill('non esiste');
  await expect(page.getByText('Nessuna tessera corrisponde alla ricerca.')).toBeVisible();
  await page.getByTestId('wallet-search').fill('aggiornata');
  await page.getByRole('button', { name: 'Apri Tessera aggiornata', exact: true }).click();
  await page.getByTestId('wallet-delete').click();
  await page.getByTestId('wallet-confirm-delete').click();
  await expect(page.getByTestId('wallet-empty')).toBeVisible();
});

test('desktop wallet keeps a single left menu and readable empty state', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await fixture(page);
  await page.goto('/portafoglio');
  const rail = page.getByTestId('ambient-rail');
  await expect(rail).toBeVisible();
  await expect(rail).toHaveCount(1);
  await expect(page.getByTestId('wallet-empty')).toBeVisible();
  const railBox = await rail.boundingBox();
  const walletBox = await page.getByTestId('wallet-screen').boundingBox();
  expect(walletBox!.x).toBeGreaterThanOrEqual(railBox!.x + railBox!.width - 3);
  fs.mkdirSync('mobile-qa', { recursive: true });
  await page.screenshot({ path: `mobile-qa/wallet-desktop-${info.project.name}.png`, fullPage: true });
});
