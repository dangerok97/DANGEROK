import { test, expect } from '@playwright/test';

// UI contract test: synthetic profile and intercepted API only. No real user data.
test('selection, continuation and complete areas keep distinct states', async ({ page }) => {
  await page.setViewportSize({ width: 1672, height: 941 });
  let selected = 'famiglia';
  let active = false;
  const areas = [
    ['casa', 'Casa', 92], ['lavoro', 'Lavoro', 100], ['studio', 'Studio', 67],
    ['mobilita', 'Mobilità', 86], ['famiglia', 'Famiglia e relazioni', 100],
    ['patrimonio', 'Patrimonio', 100], ['finanze', 'Finanze', 73],
    ['assicurazioni', 'Assicurazioni', 100], ['servizi', 'Utenze e servizi', 100],
    ['salute', 'Salute e benessere', 52],
  ] as const;
  const snapshot = () => ({
    ok: true, percent: 88, finished: true, current_area_id: selected,
    areas: areas.map(([area_id, title, percent], index) => ({
      area_id, title, percent, order: index + 1, icon_key: 'home', sensitivity: 'normal',
      description: 'Profilo di prova', purpose: 'Per aiutarti ogni giorno.',
      state: percent >= 65 ? 'known_enough' : 'started',
      state_label: percent >= 65 ? 'Conosciuta' : 'Buon punto di partenza',
      selected: selected === area_id, current: selected === area_id,
      in_progress: active && selected === area_id,
      known_count: percent === 100 ? 5 : 3, applicable_count: 5, known: [],
      open_objectives: percent === 100 || area_id === 'salute' ? [] : [
        { ref: `${area_id}.documento`, label: 'Vuoi aggiungere il documento?' },
      ],
    })),
    objective: ['famiglia', 'lavoro', 'salute'].includes(selected) ? null : {
      id: `${selected}.documento`, area_id: selected, question: 'Vuoi aggiungere il documento?',
      hint: 'Puoi farlo più tardi.', control: 'document_upload', options: [],
      allow_skip: true, allow_decline: true, step: 1, of: 1,
    },
    recommended: { area_id: 'casa', title: 'Casa', percent: 92,
      reason_code: 'quasi_completa', reason: 'Casa è quasi completa: manca solo una cosa.' },
  });
  await page.addInitScript(() => localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-ui-test')));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let result: unknown = {};
    if (path === '/api/auth/me') result = { user_id: 'synthetic-vita-test', name: 'Profilo di prova', email: 'qa@example.test' };
    else if (path === '/api/life-profile/setup/go-to-area') {
      const body = route.request().postDataJSON();
      selected = body.area_id;
      active = body.start_question === true || !!body.ref;
      result = snapshot();
    } else if (path === '/api/life-profile/setup') result = snapshot();
    else if (path.includes('life-map')) result = { situations: [], areas: [] };
    else if (path.includes('life-setup/status')) result = { enabled: true, session: { status: 'completed' } };
    await route.fulfill({ json: result });
  });
  await page.goto('/vita');
  await expect(page.getByTestId('guided-current-state')).toHaveText('Conosciuta');
  await expect(page.getByTestId('guided-area-complete')).toBeVisible();
  await expect(page.getByTestId('guided-continue-area')).toHaveCount(0);
  await expect(page.getByTestId('guided-later')).toHaveCount(0);
  await expect(page.getByTestId('guided-next-area-reason')).toContainText('Casa è quasi completa');

  await page.getByTestId('guided-rail-lavoro').click();
  await expect(page.getByTestId('guided-current-area')).toContainText('Lavoro');
  await expect(page.getByTestId('guided-current-state')).toHaveText('Conosciuta');
  await expect(page.getByTestId('guided-later')).toHaveCount(0);

  await page.getByTestId('guided-rail-mobilita').click();
  await expect(page.getByTestId('guided-current-state')).toHaveText('Conosciuta');
  await expect(page.getByTestId('guided-continue-area')).toBeVisible();
  await page.getByTestId('guided-continue-area').click();
  await expect(page.getByTestId('guided-current-state')).toHaveText('In corso');
  await expect(page.getByText('Carica documento', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('guided-current-state')).toHaveText('In corso');
  await expect(page.getByText('Carica documento', { exact: true })).toBeVisible();

  await page.getByTestId('guided-rail-mobilita').click();
  await expect(page.getByTestId('guided-current-state')).toHaveText('Conosciuta');
  await expect(page.getByTestId('guided-continue-area')).toBeVisible();
  await page.getByTestId('guided-rail-salute').click();
  await expect(page.getByTestId('guided-area-nothing-to-ask')).toBeVisible();
  await expect(page.getByTestId('guided-area-complete')).toHaveCount(0);
  await expect(page.getByTestId('guided-later')).toHaveCount(0);
});
