import { expect, test, type Page } from '@playwright/test';

const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7ZQb4AAAAASUVORK5CYII=';

type Item = { id: string; revision: number; name: string; category: string;
  color: string; formality: string; status: string; seasons: string[]; photo: string | null;
  visual_profile?: Record<string, any> | null; back_photo?: string | null; has_back?: boolean;
  front_showcase?: string | null; back_showcase?: string | null;
  created_at: string; updated_at: string };

async function mockAccount(page: Page, mode: 'recognized' | 'uncertain' | 'outage' | 'stylist_invalid' = 'recognized') {
  const items: Item[] = [];
  const feedback = new Map<string, 'like' | 'dislike'>();
  const statistics = { analyzed: 0, saved: 0, photos: 0, backPhotos: 0,
    appearanceScans: 0, appearanceConfirmations: 0, feedbackWrites: 0,
    studioPreviews: 0, studioApprovals: 0, studioRemovals: 0,
    lastStyleNote: '', usedAI: false };
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
    } else if (path === '/api/wardrobe/showcase/availability') {
      json = { enabled: true };
    } else if (path.endsWith('/showcase/preview') && req.method() === 'POST') {
      statistics.studioPreviews++;
      const params = new URL(req.url()).searchParams;
      json = {
        view: params.get('view') || 'front',
        revision: Number(params.get('revision')),
        source_sha256: 'a'.repeat(64),
        preview: 'data:image/png;base64,' + png,
        stored: false,
        message: 'Anteprima pronta: verifica il ritaglio.',
      };
    } else if (path.endsWith('/showcase') && req.method() === 'PUT') {
      statistics.studioApprovals++;
      const body = req.postDataJSON();
      const item = items.find(i => i.id === path.split('/').at(-2));
      if (item) {
        item.revision++;
        item[body.view === 'front' ? 'front_showcase' : 'back_showcase'] =
          'data:image/png;base64,' + body.png_b64;
      }
      json = { item };
    } else if (path.endsWith('/showcase') && req.method() === 'DELETE') {
      statistics.studioRemovals++;
      const body = req.postDataJSON();
      const item = items.find(i => i.id === path.split('/').at(-2));
      if (item) {
        item.revision++;
        item[body.view === 'front' ? 'front_showcase' : 'back_showcase'] = null;
      }
      json = { item };
    } else if (path === '/api/wardrobe/items' && req.method() === 'PUT') {
      statistics.saved++;
      const input = req.postDataJSON();
      const existing = items.findIndex(i => i.id === input.id);
      const item: Item = { ...input, revision: input.revision + 1,
        photo: existing >= 0 ? items[existing].photo : null,
        back_photo: existing >= 0 ? items[existing].back_photo : null,
        front_showcase: existing >= 0 ? items[existing].front_showcase : null,
        back_showcase: existing >= 0 ? items[existing].back_showcase : null,
        visual_profile: existing >= 0 ? items[existing].visual_profile : null,
        created_at: '2026-10-18T13:00:00Z', updated_at: '2026-10-18T13:00:00Z' };
      if (existing >= 0) items[existing] = item;
      else items.push(item);
      json = { item };
    } else if (path.startsWith('/api/wardrobe/items/') &&
               path.endsWith('/photo/back') && req.method() === 'POST') {
      statistics.backPhotos++;
      const id = path.split('/').at(-3);
      const item = items.find(i => i.id === id);
      if (!item?.photo) {
        await route.fulfill({ status: 409, headers,
          json: { detail: 'Carica prima la fotografia del fronte.' } });
        return;
      }
      item.revision += 1;
      item.back_photo = 'data:image/png;base64,' + png;
      item.back_showcase = null;
      item.has_back = true;
      item.visual_profile = null;
      json = { item };
    } else if (path.startsWith('/api/wardrobe/items/') &&
               path.endsWith('/photo/back') && req.method() === 'DELETE') {
      const id = path.split('/').at(-3);
      const item = items.find(i => i.id === id);
      if (item) {
        item.revision += 1;
        item.back_photo = null;
        item.back_showcase = null;
        item.has_back = false;
        item.visual_profile = null;
      }
      json = { item };
    } else if (path.startsWith('/api/wardrobe/items/') && path.endsWith('/photo') && req.method() === 'POST') {
      statistics.photos++;
      const id = path.split('/').at(-2);
      const item = items.find(i => i.id === id);
      if (item) {
        item.revision += 1;
        item.photo = 'data:image/png;base64,' + png;
        item.front_showcase = null;
        item.visual_profile = null;
      }
      json = { item };
    } else if (path.endsWith('/appearance/analyze') && req.method() === 'POST') {
      statistics.appearanceScans++;
      const id = path.split('/').at(-3);
      const item = items.find(i => i.id === id);
      if (!item?.photo) {
        await route.fulfill({ status: 409, headers, json: { detail: 'Fotografia non disponibile.' } });
        return;
      }
      json = mode === 'uncertain'
        ? { recognized: false, stored: false, draft: null,
            revision: item.revision, message: 'Non distinguo con certezza il capo.' }
        : { recognized: true, stored: false, revision: item.revision,
            views_analyzed: item.back_photo ? 2 : 1,
            photo_sha256: 'a'.repeat(64), message: 'Proposta visiva: conferma o correggi.',
            draft: { pattern: 'striped', shape: 'tailored', surface: 'smooth',
              tone: 'cool', confidence: 'medium',
              back_graphic: item.back_photo ? 'large' : 'uncertain',
              back_style: item.back_photo ? 'streetwear' : 'uncertain' } };
    } else if (path.endsWith('/appearance') && req.method() === 'PUT') {
      statistics.appearanceConfirmations++;
      const id = path.split('/').at(-2);
      const item = items.find(i => i.id === id);
      if (item) {
        const input = req.postDataJSON();
        const { revision, photo_sha256, ...details } = input;
        item.revision++;
        item.visual_profile = { ...details, reviewed_at: '2026-10-20T12:00:00Z' };
      }
      json = { item };
    } else if (path.endsWith('/appearance') && req.method() === 'DELETE') {
      const id = path.split('/').at(-2);
      const item = items.find(i => i.id === id);
      if (item) { item.visual_profile = null; item.revision++; }
      json = { item };
    } else if (path === '/api/wardrobe/outfits/feedback') {
      statistics.feedbackWrites++;
      const body = req.postDataJSON();
      const signature = [body.occasion, ...[...body.item_ids].sort()].join(':');
      feedback.set(signature, body.reaction);
      json = { stored: true, reaction: body.reaction };
    } else if (path === '/api/wardrobe/items') {
      json = { items };
    } else if (path.startsWith('/api/wardrobe/items/') && req.method() === 'DELETE') {
      const id = path.split('/').pop();
      const found = items.findIndex(i => i.id === id);
      if (found >= 0) items.splice(found, 1);
      json = { deleted: true };
    } else if (path === '/api/wardrobe/outfits') {
      const outfitBody = req.postDataJSON();
      const occasion = outfitBody.occasion;
      statistics.lastStyleNote = outfitBody.style_note || '';
      statistics.usedAI = outfitBody.use_ai === true;
      const allow = ['chic_evening', 'wedding'].includes(occasion) ? ['smart', 'formal'] : ['casual', 'smart'];
      const eligible = items.filter(i => i.status === 'available' && allow.includes(i.formality));
      const roles = ['top', 'bottom', 'shoes'];
      const separates = roles.map(role => eligible.find(i => i.category === role));
      const dress = eligible.find(i => i.category === 'one_piece');
      const footwear = eligible.find(i => i.category === 'shoes');
      const chosenShoes = eligible.filter(i => i.category === 'shoes');
      const remaining = chosenShoes.find(shoe => {
        const group = (dress ? [dress, shoe] : [separates[0], separates[1], shoe])
          .filter(Boolean) as Item[];
        const signature = [occasion, ...group.map(i => i.id).sort()].join(':');
        return feedback.get(signature) !== 'dislike';
      });
      const selected = dress && remaining ? [dress, remaining]
        : separates.map(i => i?.category === 'shoes' ? remaining : i);
      const missing = dress ? (!footwear ? ['shoes'] : []) :
        roles.filter((_, i) => !separates[i]);
      const allDisliked = !missing.length && !remaining;
      const signature = [occasion, ...selected.filter(Boolean).map(i => i!.id).sort()].join(':');
      const blackShoesBrownTrousers = selected.some(i => i?.category === 'shoes' && i.color.includes('nero'))
        && selected.some(i => i?.category === 'bottom' && i.color.includes('marrone'));
      const cautions = blackShoesBrownTrousers
        ? ['Scarpe nere e pantaloni marroni creano uno stacco da valutare dal vivo.',
           'È l\'unica combinazione completa valutabile con i capi registrati.'] : [];
      json = { engine: allDisliked ? 'preference-v1'
        : !missing.length && statistics.usedAI && mode !== 'stylist_invalid' ? 'ai-stylist-v1' : 'rules-v1',
        ai_status: missing.length ? 'insufficient_wardrobe'
          : allDisliked ? 'not_preferred'
          : mode === 'stylist_invalid' ? 'invalid_response'
          : statistics.usedAI ? 'ok' : 'not_requested',
        candidate_count: missing.length || allDisliked ? 0 : 1,
        occasion, missing,
        message: allDisliked ? 'Hai già scartato tutti i look completi.'
          : missing.length ? 'Servono altri capi'
          : mode === 'stylist_invalid' ? 'Il modello AI ha risposto, ma non ha restituito una valutazione utilizzabile in sicurezza.'
          : 'Valutazione indicativa dalle schede',
        outfits: missing.length || allDisliked ? [] : [{
          item_ids: selected.map(i => i!.id),
          title: cautions.length ? 'Look possibile, con riserve' : 'Look plausibile',
          why: 'La palette e la formalità devono essere valutate insieme.',
          verdict: cautions.length ? 'acceptable' : 'good', cautions,
          feedback: feedback.get(signature) || null,
          visual_coverage: { reviewed: selected.filter(i => i?.visual_profile?.reviewed_at).length,
            total: selected.length },
          styling_tip: selected.some(i => i?.category === 'top' && i.name.includes('Camicia')) ?
            'Valuta la camicia dentro i pantaloni, se la vestibilità lo consente.' : '' }] };
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


test('AI stylist reads user note, shows verified status and only stored garments', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page);
  await page.goto('/guardaroba');
  await add(page, 'Camicia azzurra', 'Maglia / camicia', 'azzurro');
  await add(page, 'Pantaloni blu', 'Pantaloni / gonna', 'blu');
  await add(page, 'Mocassini marroni', 'Scarpe', 'marrone');
  await page.getByRole('button', { name: 'Serata chic' }).click();
  await page.getByTestId('wardrobe-style-note').fill('Cena elegante ma non troppo formale');
  await page.getByRole('button', { name: 'Proponi gli abbinamenti con AI' }).click();
  await expect(page.getByTestId('wardrobe-ai-status')).toContainText('Stylist AI');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Camicia azzurra');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Mocassini marroni');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Consiglio sul capo:');
  expect(stats.usedAI).toBe(true);
  expect(stats.lastStyleNote).toBe('Cena elegante ma non troppo formale');
  await page.getByTestId('wardrobe-style-note').fill('Serata elegante classica');
  await expect(page.getByTestId('wardrobe-suggestions')).toHaveCount(0);
});


test('black shoes and brown trousers show candid warning without imaginary accessories', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAccount(page);
  await page.goto('/guardaroba');
  await add(page, 'Camicia azzurra a maniche lunghe', 'Maglia / camicia', 'azzurro');
  await add(page, 'Pantaloni classici marroni', 'Pantaloni / gonna', 'marrone');
  await add(page, 'Scarpe stringate nere', 'Scarpe', 'nero');
  await page.getByRole('button', { name: 'Serata chic' }).click();
  await page.getByTestId('wardrobe-style-note').fill('Elegante ma senza essere troppo formale');
  await page.getByRole('button', { name: 'Proponi gli abbinamenti con AI' }).click();
  await expect(page.getByTestId('wardrobe-ai-status')).toContainText('Valutazione delle schede');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Look possibile, con riserve');
  await expect(page.getByTestId('wardrobe-cautions')).toContainText('Scarpe nere e pantaloni marroni');
  await expect(page.getByTestId('wardrobe-suggestions')).not.toContainText('cintura');
  await expect(page.locator('[data-testid="wardrobe-suggestions"] img')).toHaveCount(0);
  // The UI must still make its registered garments legible, not 40px icon labels.
  await expect(page.locator('[data-testid="wardrobe-suggestions"]')).toContainText('Camicia azzurra');
  await expect(page.locator('[data-testid="wardrobe-suggestions"]')).toContainText('Scarpe stringate nere');
});


test('visual AI details are opt-in, correctable, confirmed separately and revocable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page);
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  await choosePhoto(page);
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Camicia azzurra');
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill('azzurro');
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');
  expect(stats.appearanceScans).toBe(0);
  await page.getByRole('button', { name: 'Analizza stile con AI' }).click();
  await expect(page.getByTestId('wardrobe-appearance-editor')).toBeVisible();
  expect(stats.appearanceScans).toBe(1);
  expect(stats.appearanceConfirmations).toBe(0);
  await page.getByTestId('wardrobe-appearance-editor').getByRole('button', { name: 'Tinta unita' }).click();
  await page.getByRole('button', { name: 'Conferma dettagli visivi' }).click();
  await expect(page.getByTestId('wardrobe-visual-profile')).toContainText('Tinta unita');
  expect(stats.appearanceConfirmations).toBe(1);
  await page.getByRole('button', { name: 'Rimuovi analisi visiva' }).click();
  await expect(page.getByTestId('wardrobe-visual-profile')).toHaveCount(0);
});

test('disliked complete outfit is not repeated, feedback changes the next suggestion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page);
  await page.goto('/guardaroba');
  await add(page, 'Camicia blu', 'Maglia / camicia', 'blu');
  await add(page, 'Pantaloni beige', 'Pantaloni / gonna', 'beige');
  await add(page, 'Scarpe nere', 'Scarpe', 'nero');
  await page.getByRole('button', { name: 'Serata chic' }).click();
  await page.getByRole('button', { name: 'Proponi gli abbinamenti con AI' }).click();
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Scarpe nere');
  await page.getByTestId('wardrobe-outfit-feedback').getByRole('button', { name: 'Non mi piace' }).click();
  expect(stats.feedbackWrites).toBe(1);
  await page.getByRole('button', { name: 'Proponi gli abbinamenti con AI' }).click();
  await expect(page.getByTestId('wardrobe-no-preferred')).toContainText('Hai già scartato');
  await add(page, 'Scarpe marroni', 'Scarpe', 'marrone');
  await page.getByRole('button', { name: 'Proponi gli abbinamenti con AI' }).click();
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Scarpe marroni');
  await expect(page.getByTestId('wardrobe-suggestions')).not.toContainText('Scarpe nere');
  await page.getByTestId('wardrobe-outfit-feedback').getByRole('button', { name: 'Mi piace', exact: true }).click();
  expect(stats.feedbackWrites).toBe(2);
  await expect(page.getByTestId('wardrobe-outfit-feedback')).toContainText('✓ Mi piace');
});


test('distinguish provider outage from an unusable model response in VITA', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAccount(page, 'stylist_invalid');
  await page.goto('/guardaroba');
  await add(page, 'Camicia azzurra', 'Maglia / camicia', 'azzurro');
  await add(page, 'Pantaloni marroni', 'Pantaloni / gonna', 'marrone');
  await add(page, 'Scarpe nere', 'Scarpe', 'nero');
  await page.getByRole('button', { name: 'Serata chic' }).click();
  await page.getByRole('button', { name: 'Proponi gli abbinamenti con AI' }).click();
  await expect(page.getByTestId('wardrobe-ai-status')).toContainText('Risposta AI non valida');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Il modello AI ha risposto');
  await expect(page.getByTestId('wardrobe-suggestions')).toContainText('Camicia azzurra');
});


test('front and optional back share one garment ID and are jointly analyzed', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page);
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  // Real file-picker calls, not an inert mock button.
  let chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Scegli una foto del capo' }).click();
  await (await chooser).setFiles({ name: 'front.png', mimeType: 'image/png',
    buffer: Buffer.from(png, 'base64') });
  chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Aggiungi foto retro (facoltativa)' }).click();
  await (await chooser).setFiles({ name: 'back.png', mimeType: 'image/png',
    buffer: Buffer.from(png, 'base64') });
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Maglia fronte neutro e retro grafico');
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill('bianco');
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');
  expect(stats.photos).toBe(1);
  expect(stats.backPhotos).toBe(1);
  // Exactly one garment card with two views, no duplicate wardrobe entry.
  await expect(page.getByTestId('wardrobe-item-views')).toHaveCount(1);
  await expect(page.getByTestId('wardrobe-item-views').getByText('Fronte')).toBeVisible();
  await expect(page.getByTestId('wardrobe-item-views').getByText('Retro')).toBeVisible();

  await page.getByRole('button', { name: 'Analizza stile con AI' }).click();
  await expect(page.getByTestId('wardrobe-appearance-message')).toContainText('Fronte e retro valutati insieme');
  await expect(page.getByTestId('wardrobe-appearance-editor')).toContainText('Stampa sul retro');
  await expect(page.getByTestId('wardrobe-appearance-editor')).toContainText('Grafica vistosa');
  await page.getByRole('button', { name: 'Conferma dettagli visivi' }).click();
  await expect(page.getByTestId('wardrobe-visual-profile')).toContainText('Retro con grafica vistosa');

  await page.getByRole('button', { name: 'Rimuovi retro' }).click();
  await expect(page.getByTestId('wardrobe-remove-back-confirm')).toContainText('Eliminare solo');
  await page.getByRole('button', { name: 'Conferma rimozione retro' }).click();
  await expect(page.getByTestId('wardrobe-item-views').getByText('Retro')).toHaveCount(0);
  await expect(page.getByTestId('wardrobe-item-views').getByText('Fronte')).toBeVisible();
});


test('studio showcase is opt-in, reviewed, accepted and original remains available', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const stats = await mockAccount(page);
  await page.goto('/guardaroba');
  await page.getByRole('button', { name: 'Aggiungi un capo' }).click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Scegli una foto del capo' }).click();
  await (await chooser).setFiles({ name: 'front.png', mimeType: 'image/png',
    buffer: Buffer.from(png, 'base64') });
  await page.getByPlaceholder('Es. Camicia azzurra').fill('Felpa blu');
  await page.getByPlaceholder('Es. Blu, bianco, beige').fill('blu');
  await page.getByRole('button', { name: 'Salva capo' }).click();
  await expect(page.getByTestId('wardrobe-notice')).toContainText('Capo salvato');

  await page.getByRole('button', { name: 'Crea foto vetrina fronte' }).click();
  await expect(page.getByTestId('wardrobe-studio-review')).toBeVisible();
  await expect(page.getByTestId('wardrobe-studio-review')).toContainText('Sfondo chiaro');
  await expect(page.getByTestId('wardrobe-studio-review')).toContainText('Sfondo scuro');
  expect(stats.studioApprovals).toBe(0);
  await page.getByRole('button', { name: 'Scarta anteprima' }).click();
  await expect(page.getByTestId('wardrobe-studio-review')).toHaveCount(0);
  expect(stats.studioPreviews).toBe(1);
  expect(stats.studioApprovals).toBe(0);

  await page.getByRole('button', { name: 'Crea foto vetrina fronte' }).click();
  await page.getByRole('button', { name: 'Accetta foto vetrina' }).click();
  await expect(page.getByRole('button', { name: 'Mostra foto originali' })).toBeVisible();
  expect(stats.studioApprovals).toBe(1);
  await page.getByRole('button', { name: 'Mostra foto originali' }).click();
  await expect(page.getByRole('button', { name: 'Mostra foto vetrina' })).toBeVisible();
  await page.getByRole('button', { name: 'Rimuovi vetrina fronte' }).click();
  expect(stats.studioRemovals).toBe(1);
  await expect(page.getByRole('button', { name: 'Mostra foto originali' })).toHaveCount(0);
  await expect(page.getByTestId('wardrobe-item-views')).toContainText('Fronte');
});
