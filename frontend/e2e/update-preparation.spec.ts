import { test, expect } from '@playwright/test';

// Browser contract test with isolated API fixtures: no real account/provider writes.
for (const entry of ['question', 'update']) test(`open, prepare, reply and reload from ${entry} preserve the same session`, async ({ page }) => {
  let posts = 0, accepts = 0;
  let state: any = { status: 'not_started' };
  const suggestion: any = { id: 'psug_fixture', title: 'Due impegni si sovrappongono', status: 'active', source: 'calendar',
    action: { kind: 'prepare_change', label: 'Prepara lo spostamento' },
    meta: { delivery: entry === 'question' ? 'propose_action' : 'inform', preparation: { summary: 'Orari confrontati', question: 'Quale impegno puoi spostare?', options: [] } } };
  await page.addInitScript(() => { localStorage.setItem('ora_auth_token', JSON.stringify('fixture')); localStorage.setItem('ora.lifeSetupCompleted.fixture', '1'); });
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: any = {};
    if (path === '/api/auth/me') body = { user_id: 'fixture', name: 'Test', email: 'fixture@example.com' };
    else if (path === '/api/home') body = { ora_ti_consiglia: [suggestion], insights: [], opportunities: [], agent_work: [], priorities: [], agenda: [], today: [], upcoming: [], open_questions: [], current_situation: {}, counts: {}, connections: [] };
    else if (path.includes('life-setup')) body = { enabled: false };
    else if (path.endsWith('/accept')) { accepts++; body = { ok: true }; }
    else if (path === '/api/suggestions/psug_fixture') body = { suggestion };
    else if (path === '/api/suggestions/psug_fixture/work') {
      if (route.request().method() === 'POST') {
        posts++;
        state = { status: 'needs_user', session_id: 'same-session', result: { question: posts === 1 ? 'Puoi spostare la riunione?' : 'Confermi la proposta delle 12?', ora_text: 'Ho preparato una proposta. Nessun evento modificato.' } };
      }
      body = state;
    }
    await route.fulfill({ json: body });
  });
  await page.goto('/');
  await page.getByTestId(entry === 'question' ? 'home-question-answer-psug_fixture' : 'home-update-psug_fixture').click();
  await expect(page).toHaveURL(/aggiornamento\/psug_fixture/);
  expect(accepts).toBe(0);
  await page.getByRole('button', { name: 'Prepara lo spostamento', exact: true }).click();
  await expect(page.getByText('Puoi spostare la riunione?', { exact: true })).toBeVisible();
  expect(posts).toBe(1);
  suggestion.status = 'expired'; // the source can expire without deleting its work
  await page.reload();
  await expect(page.getByText('Puoi spostare la riunione?', { exact: true })).toBeVisible();
  await page.getByLabel('Risposta sul prossimo passo').fill('Posso spostare la riunione');
  await page.getByRole('button', { name: 'Invia risposta', exact: true }).click();
  await expect(page.getByText('Confermi la proposta delle 12?', { exact: true })).toBeVisible();
  expect(posts).toBe(2); expect(accepts).toBe(0);
  state = { status: 'failed', message: 'Verifica interrotta', session_id: 'same-session' };
  await page.reload();
  await expect(page.getByText('Verifica interrotta', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Ricontrolla lo stato' }).click();
  expect(posts).toBe(2); // checking failure must not execute a second action
  await expect(page).toHaveURL(/aggiornamento\/psug_fixture/);
});
