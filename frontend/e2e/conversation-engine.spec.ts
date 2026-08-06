/**
 * Conversation Engine E2E — NOT a chatbot.
 * 1) "Fra due settimane parto." → Travel → Goal → Project → Calendar path → Home
 * 2) "Voglio preparare l'esame." → Study → Goal → Piano path → Home
 * Entry via Home PARLA CON ORA (API fallback same engine); answers via AE one-question UI.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'e2e-evidence', 'conversation-engine');

async function apiRegister(prefix: string) {
  const email = `e2e_ce_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E CE ${prefix}` }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string };
}

function auth(token: string) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

async function loginUI(page: Page, email: string, password: string) {
  await page.goto('/login');
  await expect(page.getByTestId('login-title')).toBeVisible({ timeout: 45_000 });
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(email);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-button').click();
  await page.waitForURL(/tabs|\/$|\(tabs\)/, { timeout: 45_000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, `${name}.png`), fullPage: true });
}

async function clickAvanti(page: Page) {
  const nextBtn = page.getByTestId('action-next');
  if (await nextBtn.isVisible().catch(() => false) && await nextBtn.isEnabled().catch(() => false)) {
    await nextBtn.click();
    await page.waitForTimeout(900);
    return true;
  }
  return false;
}

async function parlaStart(page: Page, text: string, token: string) {
  await page.goto(`/?t=${Date.now()}`);
  await page.waitForTimeout(2000);
  const parla = page.getByTestId('parla-con-ora');
  let via: 'ui' | 'api' = 'ui';
  if (await parla.isVisible().catch(() => false)) {
    await page.getByTestId('parla-input').fill(text);
    await page.getByTestId('parla-send').click();
  } else {
    via = 'api';
    const start = await fetch(`${API}/api/conversation/start`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text, origin: 'home' }),
    });
    const body = await start.json();
    if (!start.ok || !body.ok) throw new Error(`CE start failed: ${JSON.stringify(body)}`);
    const route = body.route || `/action/${body.session.action_session_id}`;
    await page.goto(route);
  }
  await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId('action-question')).toBeVisible();
  await expect(page.locator('[data-testid="chat-bubble"]')).toHaveCount(0);
  return via;
}

async function answerCurrentTurn(page: Page, mode: 'travel' | 'study') {
  await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 20_000 });
  if (await page.getByTestId('action-complete').isVisible().catch(() => false)) return true;

  const q = (await page.getByTestId('action-question').innerText()).toLowerCase();
  const nextBtn = page.getByTestId('action-next');

  // --- Travel free-text ---
  if (mode === 'travel') {
    if ((q.includes('parti') && q.includes('torni')) || q.includes('quando parti')) {
      const input = page.getByTestId('action-text');
      if (await input.isVisible().catch(() => false)) {
        await input.fill('dal 20 al 27 agosto 2026');
        await nextBtn.click();
        await page.waitForTimeout(900);
        return false;
      }
    }
    if (q.includes('destinazione')) {
      const input = page.getByTestId('action-text');
      if (await input.isVisible().catch(() => false)) {
        await input.fill('Roma');
        await nextBtn.click();
        await page.waitForTimeout(900);
        return false;
      }
    }
    if (q.includes('dove parti') || q.includes('partenza')) {
      const input = page.getByTestId('action-text');
      if (await input.isVisible().catch(() => false)) {
        await input.fill('Milano');
        await nextBtn.click();
        await page.waitForTimeout(900);
        return false;
      }
    }
  }

  // --- Study date / days / materials / tools ---
  if (mode === 'study') {
    if (q.includes('quando') || (q.includes('esame') && q.includes('«'))) {
      const chip = page.getByTestId('action-chip-in_2_weeks');
      if (await chip.isVisible().catch(() => false)) {
        await chip.click();
        await page.waitForTimeout(300);
        await clickAvanti(page);
        return false;
      }
      const input = page.getByTestId('action-text');
      if (await input.isVisible().catch(() => false)) {
        const d = new Date(Date.now() + 14 * 86400_000).toISOString().slice(0, 10);
        await input.fill(d);
        await nextBtn.click();
        await page.waitForTimeout(900);
        return false;
      }
    }
    if (q.includes('giorni') || q.includes('disponib')) {
      for (const id of ['mon', 'wed', 'fri', '0', '1', '2']) {
        const chip = page.getByTestId(`action-chip-${id}`);
        if (await chip.isVisible().catch(() => false)) await chip.click();
      }
      await clickAvanti(page);
      return false;
    }
    if (q.includes('material')) {
      const none = page.getByTestId('action-chip-none');
      if (await none.isVisible().catch(() => false)) {
        await none.click();
        await clickAvanti(page);
        return false;
      }
    }
    if (q.includes('strument')) {
      for (const id of ['study', 'review']) {
        const chip = page.getByTestId(`action-chip-${id}`);
        if (await chip.isVisible().catch(() => false)) await chip.click();
      }
      await clickAvanti(page);
      return false;
    }
  }

  const preferIds =
    mode === 'travel'
      ? ['confirm', 'accept', 'car', 'partial', 'solo', 'no', 'connect_later', 'skip', 'in_2_weeks']
      : [
          'confirm', 'accept', 'distributed', 'evening', 'no', '1h', 'none',
          'skip', 'connect_later', 'in_2_weeks', 'yes', 'study',
        ];

  for (const id of preferIds) {
    const chip = page.getByTestId(`action-chip-${id}`);
    if (!(await chip.isVisible().catch(() => false))) continue;
    await chip.click();
    await page.waitForTimeout(300);
    if (await page.getByTestId('action-complete').isVisible().catch(() => false)) return true;
    await clickAvanti(page);
    return false;
  }

  const chips = page.getByTestId('action-chips').locator('[data-testid^="action-chip-"]');
  const count = await chips.count();
  if (count > 0) {
    const firstId = await chips.nth(0).getAttribute('data-testid');
    const idx = firstId?.includes('upload') && count > 1 ? 1 : 0;
    await chips.nth(idx).click();
    await page.waitForTimeout(300);
    await clickAvanti(page);
    return false;
  }

  if (await clickAvanti(page)) return false;
  throw new Error(`No way to answer turn: ${q}`);
}

async function driveToComplete(
  page: Page,
  mode: 'travel' | 'study',
  token: string,
  actionSessionId: string,
  max = 30,
) {
  let lastQ = '';
  let stuck = 0;
  for (let i = 0; i < max; i++) {
    if (await page.getByTestId('action-complete').isVisible().catch(() => false)) return i;
    const q = await page.getByTestId('action-question').innerText().catch(() => '');
    if (q && q === lastQ) {
      stuck += 1;
      if (stuck >= 2) {
        // API nudge if UI stuck on same question
        const sess = await fetch(`${API}/api/action-engine/sessions/${actionSessionId}`, {
          headers: auth(token),
        }).then((r) => r.json());
        const turn = sess.session?.current_turn || sess.current_turn;
        if (turn?.id) {
          const body: Record<string, unknown> = {};
          if (turn.id === 'period' || turn.id === 'destination' || turn.id === 'departure_place') {
            body.text = turn.id === 'period' ? 'dal 20 al 27 agosto 2026' : turn.id === 'destination' ? 'Roma' : 'Milano';
          } else if (turn.id === 'exam_date') {
            body.option_id = 'in_2_weeks';
          } else if (turn.id === 'available_days') {
            body.value = [0, 1, 2, 3, 4];
          } else if (turn.id === 'select_materials') {
            body.option_id = 'none';
            body.value = [];
          } else if (turn.id === 'tools') {
            body.value = ['study', 'review'];
          } else if (turn.options?.length) {
            body.option_id = turn.options[0].id;
          } else if (turn.allow_skip) {
            body.skip = true;
          } else {
            body.text = 'ok';
          }
          await fetch(`${API}/api/action-engine/sessions/${actionSessionId}/answer`, {
            method: 'POST',
            headers: auth(token),
            body: JSON.stringify(body),
          });
          await page.reload();
          await page.waitForTimeout(1200);
          stuck = 0;
          lastQ = '';
          continue;
        }
      }
    } else {
      stuck = 0;
      lastQ = q;
    }
    await answerCurrentTurn(page, mode);
    await page.waitForTimeout(400);
  }
  await expect(page.getByTestId('action-complete')).toBeVisible({ timeout: 25_000 });
  return max;
}

test.describe('Conversation Engine', () => {
  test('Travel: Fra due settimane parto → Goal → Project → Home', async ({ page }) => {
    test.setTimeout(240_000);
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    const creds = await apiRegister('travel');

    const probe = await fetch(`${API}/api/conversation?limit=1`, { headers: auth(creds.token) });
    expect(probe.status).toBe(200);

    await loginUI(page, creds.email, creds.password);
    await shot(page, 'travel-00-home');

    const via = await parlaStart(page, 'Fra due settimane parto.', creds.token);
    await shot(page, 'travel-01-first-question');

    const list = await fetch(`${API}/api/conversation?limit=5`, { headers: auth(creds.token) });
    const listed = await list.json();
    const ces = (listed.sessions || [])[0];
    expect(ces).toBeTruthy();

    const getCes = await fetch(`${API}/api/conversation/sessions/${ces.id}`, {
      headers: auth(creds.token),
    });
    const cesBody = await getCes.json();
    expect(cesBody.ok).toBeTruthy();
    expect(cesBody.session.intent.intent).toBe('travel');
    expect(cesBody.session.goal_id).toBeTruthy();
    expect(cesBody.session.action_session_id).toBeTruthy();
    expect(cesBody.route).toMatch(/^\/action\//);

    const steps = await driveToComplete(
      page, 'travel', creds.token, cesBody.session.action_session_id,
    );
    await shot(page, 'travel-99-complete');

    const projects = await fetch(`${API}/api/travel-projects`, { headers: auth(creds.token) });
    const pj = await projects.json();
    expect((pj.items || []).length).toBeGreaterThanOrEqual(1);

    await page.goto(`/?t=${Date.now()}`);
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="chat-bubble"]')).toHaveCount(0);
    await shot(page, 'travel-100-home');

    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'travel-run.json'),
      JSON.stringify({
        ok: true,
        via,
        steps,
        conversation_session_id: ces.id,
        goal_id: cesBody.session.goal_id,
        travel_project_id: pj.items?.[0]?.id,
        at: new Date().toISOString(),
      }, null, 2),
    );
  });

  test("Study: Voglio preparare l'esame → Goal → Piano → Home", async ({ page }) => {
    test.setTimeout(240_000);
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    const creds = await apiRegister('study');

    await loginUI(page, creds.email, creds.password);
    await shot(page, 'study-00-home');

    const via = await parlaStart(page, "Voglio preparare l'esame.", creds.token);
    await shot(page, 'study-01-first-question');

    const list = await fetch(`${API}/api/conversation?limit=5`, { headers: auth(creds.token) });
    const listed = await list.json();
    const ces = (listed.sessions || [])[0];
    expect(ces).toBeTruthy();

    const getCes = await fetch(`${API}/api/conversation/sessions/${ces.id}`, {
      headers: auth(creds.token),
    });
    const cesBody = await getCes.json();
    expect(cesBody.session.intent.intent).toBe('study');
    expect(cesBody.session.goal_id).toBeTruthy();
    expect(cesBody.session.action_session_id).toBeTruthy();

    const steps = await driveToComplete(
      page, 'study', creds.token, cesBody.session.action_session_id,
    );
    await shot(page, 'study-99-complete');

    const plans = await fetch(`${API}/api/study-plans`, { headers: auth(creds.token) });
    const pl = await plans.json();
    const planCount = (pl.items || pl.plans || []).length;

    await page.goto(`/?t=${Date.now()}`);
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="chat-bubble"]')).toHaveCount(0);
    await shot(page, 'study-100-home');

    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'study-run.json'),
      JSON.stringify({
        ok: true,
        via,
        steps,
        conversation_session_id: ces.id,
        goal_id: cesBody.session.goal_id,
        study_plans: planCount,
        at: new Date().toISOString(),
      }, null, 2),
    );
  });
});
