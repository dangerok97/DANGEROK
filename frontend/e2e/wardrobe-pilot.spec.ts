import { expect, test, type Page } from '@playwright/test';

type Item = { id: string; revision: number; name: string; category: string;
  color: string; formality: string; status: string; seasons: string[]; photo: string | null;
  created_at: string; updated_at: string };

async function mockAccount(page: Page) {
  const items: Item[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-wardrobe-session'));
  });
  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const headers = {
      'access-control-allow-origin': req.headers().origin || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
      'cache-control': 'no-store',
    };
    if (req.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers }); return;
    }
    let json: any = {};
    if (path.endsWith('/auth/me')) {
      json = { user_id: 'synthetic-wardrobe-owner', name: 'Utente prova',
        email: 'wardrobe-qa@example.invalid', provider: 'password',
        identity_confirmed: true, knowledge_tutorial_version: 1 };
    } else if (path.endsWith('/life-profile/knowledge-map')) {
      json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0,
        percent: 20, revision: 'synthetic-wardrobe-v1' };
    } else if (path.endsWith('/life-profile/setup')) {
      json = { ok: true, finished: true, percent: 20, areas: [],
        current_area_id: null, objective: null };
    } else if (path.endsWith('/life-map')) {
      json = { ok: true, situations: [], areas: [] };
    } else if (path.endsWith('/places')) {
      json = { places: [], candidates: [], routines: [],
        permission: { preference: 'while_using', state: 'granted', freshness: 'current' } };
    } else if (path.includes('/life-setup')) {
      json = { ok: true, enabled: false, completed: true };
    } else if (path === '/api/wardrobe/items' && req.method() === 'PUT') {
      const input = req.postDataJSON();
      const existing = items.findIndex(i => i.id === input.id);
      const item: Item = { ...input, revision: input.revision + 1, photo: null,
        created_at: '2026-10-18T13:00:00Z', updated_at: '2026-10-18T13:00:00Z' };
      if (existing >= 0) items[existing] = item;
      else items.push(item);
      json = { item };
    } else if (path === '/api/wardrobe/items') {
      json = { items };
    } else if (path.startsWith('/api/wardrobe/items/') && req.method() === 'DELETE') {
      const id = path.split('/').pop();
      const found = items.findIndex(i => i.id === id);
      if (found >= 0) items.splice(found, 1);
      json = { deleted: true };
    } else if (path === '/api/wardrobe/outfits') {
      const occasion = req.postDataJSON().occasion;
      const allow = occasion === 'chic_evening' ? ['smart', 'formal'] : ['casual', 'smart'];
      const eligible = items.filter(i => i.status === 'available' && allow.includes(i.formality));
      const roles = ['top', 'bottom', 'shoes'];
      const selected = roles.map(role => eligible.find(i => i.category === role));
      const missing = roles.filter((_, i) => !selected[i]);
      json = { engine: 'rules-v1', occasion, missing,
        message: missing.length ? 'Servono altri capi' : 'Abbinamento indicativo',
        outfits: missing.length ? [] : [{ item_ids: selected.map(i => i!.id),
          title: 'Look', why: 'Capi disponibili e compatibili.', score: 2 }] };
    }
    await route.fulfill({ status: 200, headers, json });
  });
  await page.route(url => url.protocol.startsWith('http')
    && !['localhost', '127.0.0.1'].includes(url.hostname)
    && !url.pathname.startsWith('/api/'), route => route.abort());
}

async function add(page: Page, name: string, category: string, color: string) {
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await expect(page.getByTestId('wardrobe-editor')).toBeVisible();
  await page.getByPlaceholder('Es. Camicia azzurra').fill(name);
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill(color);
  await page.getByRole('button', { name: category, exact: true }).click();
  await page.getByRole('button', { name: 'Curato', exact: true }).click();
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');
}

test('VITA opens private wardrobe; outfits only use owned available garments', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAccount(page);
  await page.goto('/vita');
  await expect(page.getByTestId('vita-wardrobe-entry')).toBeVisible();
  await page.getByTestId('vita-wardrobe-entry').click();
  await expect(page).toHaveURL(/\/guardaroba$/);
  await expect(page.getByTestId('wardrobe-screen')).toBeVisible();

  await add(page, 'Camicia blu', 'Maglia / camicia', 'blu');
  await add(page, 'Pantaloni beige', 'Pantaloni / gonna', 'beige');
  await page.getByRole('button', { name: 'Serata chic' }).click();
  await page.getByRole('button', { name: 'Proponi gli abbinamenti' }).click();
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Scarpe');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Non invento');

  await add(page, 'Scarpe marroni', 'Scarpe', 'marrone');
  await page.getByRole('button', { name: 'Proponi gli abbinamenti' }).click();
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Camicia blu');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Pantaloni beige');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Scarpe marroni');

  const shoeCard = page.getByText('Scarpe marroni', { exact: true }).locator('..');
  await shoeCard.getByRole('button', { name: 'Modifica' }).click();
  await page.getByRole('button', { name: 'Da lavare' }).click();
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await page.getByRole('button', { name: 'Proponi gli abbinamenti' }).click();
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Scarpe');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Non invento');
});
