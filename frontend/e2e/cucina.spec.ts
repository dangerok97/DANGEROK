import { expect, test, type Page } from '@playwright/test';

type Recipe = {
  id: string; revision: number; title: string; source_url: string; source_text: string;
  ingredients: string[]; steps: string[]; tags: string[]; servings: number | null;
  favorite: boolean; status: 'to_try' | 'cooked'; created_at: string; updated_at: string;
};

async function mockAccount(page: Page) {
  const recipes: Recipe[] = [];
  const counts = { previews: 0, created: 0, updated: 0, deleted: 0 };
  await page.addInitScript(() => {
    localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-recipes-session'));
  });
  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const method = req.method();
    const headers = {
      'access-control-allow-origin': req.headers().origin || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
      'cache-control': 'no-store',
    };
    if (method === 'OPTIONS') {
      await route.fulfill({ status: 204, headers });
      return;
    }
    let json: any = {};
    if (path.endsWith('/auth/me')) {
      json = { user_id: 'synthetic-cucina-owner', name: 'Utente prova',
        email: 'cucina-qa@example.invalid', provider: 'password',
        identity_confirmed: true, knowledge_tutorial_version: 1 };
    } else if (path.endsWith('/life-profile/knowledge-map')) {
      json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0,
        percent: 20, revision: 'synthetic-cucina-v1' };
    } else if (path.endsWith('/life-profile/setup')) {
      json = { ok: true, finished: true, percent: 20, areas: [],
        current_area_id: null, objective: null };
    } else if (path.endsWith('/life-map')) {
      json = { ok: true, situations: [], areas: [] };
    } else if (path.endsWith('/places')) {
      json = { places: [], candidates: [], routines: [],
        permission: { preference: 'off', state: 'off' } };
    } else if (path.includes('/life-setup')) {
      json = { ok: true, enabled: false, completed: true };
    } else if (path === '/api/recipes/preview') {
      counts.previews++;
      const { source } = req.postDataJSON();
      const isLink = source.startsWith('https://');
      json = {
        quality: isLink ? 'link_only' : 'structured_text',
        warnings: isLink
          ? ['Link conservabile, ma video e ingredienti non sono stati analizzati.'] : [],
        draft: {
          title: isLink ? 'Ricetta da Instagram' : 'Pasta con zucchine',
          source_url: isLink ? source : '',
          source_text: isLink ? '' : source,
          ingredients: isLink ? [] : ['250 g pasta', '2 zucchine'],
          steps: isLink ? [] : ['Cuoci la pasta', 'Salta le zucchine'],
          tags: [], servings: null, favorite: false, status: 'to_try',
        },
      };
    } else if (path === '/api/recipes/items' && method === 'GET') {
      json = { items: recipes };
    } else if (path === '/api/recipes/items' && method === 'POST') {
      counts.created++;
      const data = req.postDataJSON();
      const existing = recipes.find(i => i.source_url
        ? i.source_url === data.source_url : i.source_text === data.source_text);
      if (existing) {
        json = { item: existing, created: false };
      } else {
        const item: Recipe = { ...data, id: (recipes.length + 1).toString(16).padStart(32, '0'),
          revision: 1, created_at: '2026-10-22T08:00:00Z',
          updated_at: '2026-10-22T08:00:00Z' };
        recipes.push(item);
        json = { item, created: true };
      }
    } else if (path.startsWith('/api/recipes/items/') && method === 'PUT') {
      counts.updated++;
      const id = path.split('/').at(-1);
      const idx = recipes.findIndex(i => i.id === id);
      const data = req.postDataJSON();
      if (idx === -1 || data.revision !== recipes[idx].revision) {
        await route.fulfill({ status: 409, headers,
          json: { detail: 'Questa ricetta è stata modificata altrove. Ricarica la lista.' } });
        return;
      }
      recipes[idx] = { ...recipes[idx], ...data, revision: data.revision + 1 };
      json = { item: recipes[idx] };
    } else if (path.startsWith('/api/recipes/items/') && method === 'DELETE') {
      counts.deleted++;
      const id = path.split('/').at(-1);
      const idx = recipes.findIndex(i => i.id === id);
      if (idx !== -1) recipes.splice(idx, 1);
      json = { deleted: true };
    }
    await route.fulfill({ status: 200, headers, json });
  });
  // No live calls to third-party sites or real accounts during UI QA.
  await page.route(url => url.protocol.startsWith('http')
    && !['localhost', '127.0.0.1'].includes(url.hostname)
    && !url.pathname.startsWith('/api/'), route => route.abort());
  return counts;
}

test('VITA opens Cucina; link-only import requires explicit save and stores no imaginary ingredients', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await mockAccount(page);
  await page.goto('/vita');
  await expect(page.getByTestId('vita-recipe-entry')).toBeVisible();
  await page.getByTestId('vita-recipe-entry').click();
  await expect(page).toHaveURL(/\/cucina$/);
  await expect(page.getByText('Il mio ricettario')).toBeVisible();
  await page.getByTestId('recipes-source').fill('https://www.instagram.com/reel/example/');
  await page.getByRole('button', { name: 'Leggi il contenuto' }).click();
  await expect(page.getByTestId('recipes-editor')).toBeVisible();
  await expect(page.getByText(/video e ingredienti non sono stati analizzati/)).toBeVisible();
  await expect(page.getByTestId('recipes-ingredients')).toHaveValue('');
  await expect(page.getByText('Ricette salvate (0)')).toBeVisible();
  expect(calls.created).toBe(0);
  await page.getByRole('button', { name: 'Salva nel ricettario' }).click();
  await expect(page.getByTestId('recipes-notice')).toContainText('Ricetta salvata');
  await expect(page.getByText('Ricette salvate (1)')).toBeVisible();
  await expect(page.getByTestId('recipes-item')).toContainText('Da completare');
  expect(calls.created).toBe(1);
  await page.reload();
  await expect(page.getByText('Ricette salvate (1)')).toBeVisible();
});

test('text recipe can be edited, searched, favorited and deleted after confirmation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const calls = await mockAccount(page);
  await page.goto('/cucina');
  await page.getByTestId('recipes-source').fill(
    'Pasta con zucchine\nIngredienti:\n- 250 g pasta\n- 2 zucchine\nProcedimento:\n1. Cuoci la pasta\n2. Salta le zucchine'
  );
  await page.getByRole('button', { name: 'Leggi il contenuto' }).click();
  await expect(page.getByTestId('recipes-ingredients')).toHaveValue('250 g pasta\n2 zucchine');
  await page.getByTestId('recipes-title').fill('Pasta alle zucchine');
  await page.getByRole('button', { name: 'Salva nel ricettario' }).click();
  await expect(page.getByText('Ricette salvate (1)')).toBeVisible();
  expect(calls.created).toBe(1);
  const item = page.getByTestId('recipes-item');
  await item.getByRole('button', { name: 'Aggiungi ai preferiti' }).click();
  await expect(item.getByRole('button', { name: 'Rimuovi dai preferiti' })).toBeVisible();
  await page.getByTestId('recipes-search').fill('zucchine');
  await expect(item).toBeVisible();
  await page.getByTestId('recipes-search').fill('pizza');
  await expect(page.getByText('Nessuna ricetta trovata.')).toBeVisible();
  await page.getByTestId('recipes-search').fill('');
  await item.getByRole('button', { name: 'Apri / modifica' }).click();
  await page.getByTestId('recipes-steps').fill('Cuoci la pasta\nUnisci le zucchine');
  await page.getByRole('button', { name: 'Salva nel ricettario' }).click();
  await expect(page.getByTestId('recipes-notice')).toContainText('Modifiche salvate');
  expect(calls.updated).toBeGreaterThanOrEqual(2);
  await item.getByRole('button', { name: 'Elimina', exact: true }).click();
  expect(calls.deleted).toBe(0);
  await item.getByRole('button', { name: 'Conferma elimina' }).click();
  await expect(page.getByText('Ricette salvate (0)')).toBeVisible();
  expect(calls.deleted).toBe(1);
});
