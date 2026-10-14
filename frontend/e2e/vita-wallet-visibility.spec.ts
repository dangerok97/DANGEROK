import { expect, test, type Page } from '@playwright/test';

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
    } else if (path.endsWith('/life-profile/knowledge-map')) {
      json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0, percent: 21, revision: 'synthetic-v1' };
    } else if (path.endsWith('/life-profile/setup')) {
      json = { ok: true, finished: true, percent: 21, areas: [], current_area_id: null, objective: null };
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

test('canonical /vita contains wallet after I tuoi luoghi and opens the protected wallet', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto('/vita');
  await expect(page.getByTestId('guided-setup')).toBeVisible();
  const wallet = page.getByTestId('vita-wallet-section');
  const entry = page.getByTestId('vita-wallet-entry');
  await expect(wallet).toBeVisible();
  await expect(entry).toHaveCount(1);
  await expect(wallet).toContainText('TESSERE FEDELTÀ');
  await expect(entry).toContainText('Portafoglio tessere');
  await entry.click();
  await expect(page).toHaveURL(/\/portafoglio$/);
  await expect(page.getByTestId('wallet-screen')).toBeVisible();
});

test('old /contesti bookmark converges on the same canonical /vita', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto('/contesti');
  await expect(page).toHaveURL(/\/vita$/);
  await expect(page.getByTestId('guided-setup')).toBeVisible();
  await expect(page.getByTestId('vita-wallet-entry')).toHaveCount(1);
});

test('wallet remains accessible on canonical VITA even if life map is unavailable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, 'error');
  await page.goto('/vita');
  await expect(page.getByTestId('guided-setup')).toBeVisible();
  await expect(page.getByTestId('vita-wallet-entry')).toBeVisible();
});
