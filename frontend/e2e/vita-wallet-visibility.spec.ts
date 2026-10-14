import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

/**
 * E2E against the real exported VITA and wallet routes.
 * Data is synthetic: no connected account, card or external provider is used.
 */
async function fixture(page: Page, scenario: 'known-life' | 'empty-life' | 'error' = 'known-life') {
  const origin = 'http://127.0.0.1:8093';
  await page.addInitScript(() => {
    localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-vita-wallet-token'));
  });
  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const headers = {
      'access-control-allow-origin': req.headers().origin || origin,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
      'cache-control': 'no-store',
    };
    if (req.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers });
      return;
    }
    if (scenario === 'error' && (
      path.endsWith('/life-map')
      || path.endsWith('/life-setup/profile')
      || path.endsWith('/study-plans')
      || path.endsWith('/travel-projects')
    )) {
      await route.fulfill({ status: 503, headers, json: { detail: 'Synthetic upstream unavailable' } });
      return;
    }
    let json: any = {};
    if (path.endsWith('/auth/me')) {
      json = {
        user_id: 'synthetic-vita-wallet-owner',
        name: 'Utente prova',
        email: 'wallet-visibility@example.invalid',
        provider: 'password',
        identity_confirmed: true,
        knowledge_tutorial_version: 1,
      };
    } else if (path.endsWith('/life-map')) {
      json = { ok: true, situations: [],
        areas: scenario === 'known-life'
          ? [{ id: 'house', domain: 'home', title: 'Casa', identity: 'Area della vita di prova' }]
          : [],
      };
    } else if (path.endsWith('/life-memory')) {
      json = { ok: true, memories: [], groups: [] };
    } else if (path.endsWith('/life-profile')) {
      json = { ok: true, percent: 21, areas: [], suggested_area_id: null };
    } else if (path.endsWith('/wallet/cards')) {
      json = { cards: [] };
    } else if (path.endsWith('/places')) {
      // PlacesSection expects a real response contract, not an empty object.
      // Without permission, the component throws before the wallet can render.
      json = {
        places: [], candidates: [], routines: [],
        permission: { preference: 'while_using', state: 'granted', freshness: 'current' },
      };
    } else if (path.includes('life-setup')) {
      json = { ok: true, enabled: false, completed: true, profile: null };
    } else if (path.endsWith('/study-plans') || path.endsWith('/travel-projects')) {
      json = { items: [] };
    }
    await route.fulfill({ status: 200, headers, json });
  });
  await page.route(url => url.protocol.startsWith('http')
    && !['localhost', '127.0.0.1'].includes(url.hostname)
    && !url.pathname.startsWith('/api/'), route => route.abort());
}

test('VITA shows the wallet after Places and before life areas on phone, and opens the real wallet route', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto('/contesti');
  const places = page.getByTestId('vita-places');
  const wallet = page.getByTestId('vita-wallet-section');
  const entry = page.getByTestId('vita-wallet-entry');
  const areas = page.getByTestId('vita-areas');
  await expect(places).toBeVisible();
  await expect(wallet).toBeVisible();
  await expect(entry).toBeVisible();
  await expect(entry).toHaveCount(1);
  await expect(areas).toBeVisible();
  await expect(wallet).toContainText('TESSERE FEDELTÀ');
  await expect(entry).toContainText('Portafoglio tessere');
  const ordered = await page.evaluate(() => {
    const a = document.querySelector('[data-testid="vita-places"]');
    const b = document.querySelector('[data-testid="vita-wallet-section"]');
    const c = document.querySelector('[data-testid="vita-areas"]');
    return !!(a && b && c
      && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
      && (b.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(ordered).toBe(true);
  await entry.scrollIntoViewIfNeeded();
  fs.mkdirSync('mobile-qa', { recursive: true });
  await page.screenshot({ path: `mobile-qa/vita-wallet-visible-${testInfo.project.name}.png`, animations: 'disabled' });
  await entry.click();
  await expect(page).toHaveURL(/\/portafoglio$/);
  await expect(page.getByTestId('wallet-screen')).toBeVisible();
  await expect(page.getByTestId('wallet-add')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
});

test('the VITA wallet is visible with no life-map content and zero saved cards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, 'empty-life');
  await page.goto('/contesti');
  await expect(page.getByTestId('vita-empty')).toBeVisible();
  await expect(page.getByTestId('vita-wallet-section')).toBeVisible();
  await expect(page.getByTestId('vita-wallet-entry')).toHaveCount(1);
  await page.getByTestId('vita-wallet-entry').click();
  await expect(page.getByTestId('wallet-empty')).toBeVisible();
});

test('the wallet entry stays usable if VITA life-map and fallback services are unavailable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, 'error');
  await page.goto('/contesti');
  await expect(page.getByTestId('vita-wallet-section')).toBeVisible();
  await expect(page.getByTestId('vita-wallet-entry')).toHaveCount(1);
  await page.getByTestId('vita-wallet-entry').click();
  await expect(page.getByTestId('wallet-screen')).toBeVisible();
});

test('persistent Tessere shortcut remains visible after scrolling through VITA', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto('/contesti');
  await expect(page.getByTestId('vita-wallet-floating')).toBeVisible();
  await page.getByTestId('vita-scroll').evaluate((el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll')); });
  await expect(page.getByTestId('vita-wallet-floating')).toBeInViewport();
  await page.getByTestId('vita-wallet-floating').click();
  await expect(page).toHaveURL(/\/portafoglio$/);
  await expect(page.getByTestId('wallet-screen')).toBeVisible();
});
