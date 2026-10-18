import { expect, test, type Page } from '@playwright/test';

const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7ZQb4AAAAASUVORK5CYII=';

type Item = { id: string; revision: number; name: string; category: string;
  color: string; formality: string; status: string; seasons: string[]; photo: string | null;
  created_at: string; updated_at: string };

async function mockAccount(page: Page, mode: 'recognized' | 'uncertain' | 'outage' = 'recognized') {
  const items: Item[] = [];
  const statistics = { analyzed: 0, saved: 0, photos: 0 };
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
    } else if (path === '/api/wardrobe/analyze') {
      statistics.analyzed++;
      expect(req.method()).toBe('POST');
      expect(req.headers()['content-type']).toBe('image/png');
      if (mode === 'outage') {
        await route.fulfill({ status: 503, headers,
          json: { detail: 'Riconoscimento AI non configurato. Puoi compilare i campi manualmente.' } });
        return;
      }
      json = mode === 'uncertain'
        ? { recognized: false, confidence: 'low', suggestion: null,
            saved: false, engine: 'vision-ai-draft', message: 'Non riconosco il capo con certezza.' }
        : { recognized: true, confidence: 'high', saved: false,
            engine: 'vision-ai-draft', message: 'Proposta AI da verificare.',
            suggestion: { name: 'Camicia blu', category: 'top', color: 'blu', formality: 'smart' } };
    } else if (path === '/api/wardrobe/items' && req.method() === 'PUT') {
      statistics.saved++;
      const input = req.postDataJSON();
      const existing = items.findIndex(i => i.id === input.id);
      const item: Item = { ...input, revision: input.revision + 1, photo: null,
        created_at: '2026-10-18T13:00:00Z', updated_at: '2026-10-18T13:00:00Z' };
      if (existing >= 0) items[existing] = item;
      else items.push(item);
      json = { item };
    } else if (path.startsWith('/api/wardrobe/items/') && path.endsWith('/photo') && req.method() === 'POST') {
      statistics.photos++;
      const id = path.split('/').at(-2);
      const item = items.find(i => i.id === id);
      if (item) {
        item.revision += 1;
        item.photo = 'data:image/png;base64,' + png;
      }
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
      const allow = ['chic_evening', 'wedding'].includes(occasion) ? ['smart', 'formal'] : ['casual', 'smart'];
      const eligible = items.filter(i => i.status === 'available' && allow.includes(i.formality));
      const roles = ['top', 'bottom', 'shoes'];
      const separates = roles.map(role => eligible.find(i => i.category === role));
      const dress = eligible.find(i => i.category === 'one_piece');
      const footwear = eligible.find(i => i.category === 'shoes');
      const selected = dress && footwear ? [dress, footwear] : separates;
      const missing = dress ? (footwear ? [] : ['shoes']) :
        roles.filter((_, i) => !separates[i]);
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
  return statistics;
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


async function choosePhoto(page: Page) {
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Scegli una foto del capo' }).click();
  await (await chooser).setFiles({ name: 'synthetic-clothing.png',
    mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
}

test('explicit AI photo preview prefills an editable draft but never auto-saves', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page);
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await choosePhoto(page);
  await expect(page.getByRole('button', { name: 'Riconosci con AI' })).toBeVisible();
  expect(stats.saved).toBe(0);
  expect(stats.analyzed).toBe(0); // Selecting alone does not invoke a provider.
  await page.getByRole('button', { name: 'Riconosci con AI' }).click();
  await expect(page.getByTestId('wardrobe-analysis-note')).toContainText('verificare');
  await expect(page.getByPlaceholder('Es. Camicia azzurra')).toHaveValue('Camicia blu');
  await expect(page.getByPlaceholder('Es. Blu, bianco, beige')).toHaveValue('blu');
  expect(stats.analyzed).toBe(1);
  expect(stats.saved).toBe(0); // An AI suggestion is not a stored clothing item.
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Camicia blu preferita');
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');
  expect(stats.saved).toBe(1);
  expect(stats.photos).toBe(1);
  await expect(page.getByText('Camicia blu preferita')).toBeVisible();
});

test('uncertain AI returns no details; manual input stays functional', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page, 'uncertain');
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await choosePhoto(page);
  await page.getByRole('button', { name: 'Riconosci con AI' }).click();
  await expect(page.getByTestId('wardrobe-analysis-note')).toContainText('Non riconosco');
  await expect(page.getByPlaceholder('Es. Camicia azzurra')).toHaveValue('');
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Felpa grigia');
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill('grigio');
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');
  expect(stats.saved).toBe(1);
});

test('provider outage explains manual fallback; no invented AI result', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page, 'outage');
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await choosePhoto(page);
  await page.getByRole('button', { name: 'Riconosci con AI' }).click();
  await expect(page.getByTestId('wardrobe-analysis-note')).toContainText('manualmente');
  await expect(page.getByPlaceholder('Es. Camicia azzurra')).toHaveValue('');
  expect(stats.analyzed).toBe(1);
  expect(stats.saved).toBe(0);
});


test('a one-piece dress plus shoes is a complete wedding look', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAccount(page);
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Abito verde');
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill('verde');
  await page.getByRole('button', { name: 'Abito intero / tuta' }).click();
  await page.getByRole('button', { name: 'Elegante', exact: true }).click();
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');

  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Scarpe nere');
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill('nero');
  await page.getByRole('button', { name: 'Scarpe', exact: true }).click();
  await page.getByRole('button', { name: 'Elegante', exact: true }).click();
  await page.getByRole('button', { name: 'Salva capo' }).click();

  await page.getByRole('button', { name: 'Matrimonio' }).click();
  await page.getByRole('button', { name: 'Proponi gli abbinamenti' }).click();
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Abito verde');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Scarpe nere');
  await expect(page.getByTestId('wardrobe-suggestions')).not.toContainText('Mancano');
});
