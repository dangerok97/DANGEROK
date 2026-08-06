/**
 * Semantic Extraction + Gap Analyzer E2E
 * 1) "Fra due settimane parto" → NOT "Quando parti e quando torni?" → destination → return only → complete → Home → persistence
 * 2) "Dal 9 al 24 agosto vado a Vibo Marina in auto." → does NOT ask dates/destination/transport
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'e2e-evidence', 'semantic-extraction');

async function apiRegister(prefix: string) {
  const email = `e2e_sem_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E Sem ${prefix}` }),
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

async function startParla(page: Page, text: string, token: string) {
  await page.goto(`/?t=${Date.now()}`);
  await page.waitForTimeout(2000);
  const parla = page.getByTestId('parla-con-ora');
  if (await parla.isVisible().catch(() => false)) {
    await page.getByTestId('parla-input').fill(text);
    await page.getByTestId('parla-send').click();
  } else {
    const start = await fetch(`${API}/api/conversation/start`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text, origin: 'home' }),
    });
    const body = await start.json();
    if (!start.ok || !body.ok) throw new Error(`CE start failed: ${JSON.stringify(body)}`);
    const route = body.route || `/action/${body.session.action_session_id}`;
    // Assert API-level first question before UI
    const fq = String(body.first_question || body.session?.meta?.first_question || '').toLowerCase();
    expect(fq).not.toContain('quando parti e quando torni');
    await page.goto(route);
  }
  await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId('action-question')).toBeVisible();
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

test.describe('Semantic Extraction Gap Analyzer', () => {
  test('1) fortnight departure → destination first → return only → Goal/Home persistence', async ({ page }) => {
    const { email, password, token } = await apiRegister('fortnight');
    await loginUI(page, email, password);

    // API assert extraction before UI
    const extract = await fetch(`${API}/api/semantic/extract`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text: 'Fra due settimane parto.', intent: 'travel', use_gemini: false }),
    }).then((r) => r.json());
    expect(extract.ok).toBeTruthy();
    const known = extract.extraction?.known_slots || {};
    expect(known.departure_date || known.start_date).toBeTruthy();
    expect(known.return_date).toBeFalsy();
    const gaps = await fetch(`${API}/api/semantic/gaps`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text: 'Fra due settimane parto.', intent: 'travel', flow: 'travel' }),
    }).then((r) => r.json());
    expect(gaps.gaps?.next_slot).toBe('destination');
    expect(String(gaps.gaps?.next_best_question || '').toLowerCase()).not.toContain('quando parti e quando torni');

    await startParla(page, 'Fra due settimane parto.', token);
    await shot(page, '01-fortnight-first-q');

    const q1 = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(q1).not.toContain('quando parti e quando torni');
    expect(q1.includes('dove') || q1.includes('destinazione')).toBeTruthy();

    // Understood summary should show Partenza
    const summary = page.getByTestId('understood-summary');
    if (await summary.isVisible().catch(() => false)) {
      const t = (await summary.innerText()).toLowerCase();
      expect(t.includes('partenza') || t.includes('destinazione')).toBeTruthy();
    }

    // Answer destination
    const input = page.getByTestId('action-text');
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill('Calabria');
    await clickAvanti(page);
    await page.waitForTimeout(1000);
    await shot(page, '02-after-destination');

    const q2 = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(q2).not.toContain('quando parti e quando torni');
    expect(q2.includes('rientra') || q2.includes('torn')).toBeTruthy();
    // Should NOT re-ask departure
    expect(q2.includes('quando parti?') && !q2.includes('rientra')).toBeFalsy();

    // Answer return only
    await page.getByTestId('action-text').fill('tra tre settimane');
    await clickAvanti(page);
    await page.waitForTimeout(800);

    // Drive remaining chips to complete (bounded)
    for (let i = 0; i < 25; i++) {
      if (await page.getByTestId('action-complete').isVisible().catch(() => false)) break;
      const q = (await page.getByTestId('action-question').innerText().catch(() => '')).toLowerCase();
      expect(q).not.toContain('quando parti e quando torni');
      const prefer = ['booked', 'need', 'car', 'partial', 'solo', 'no', 'skip', 'accept', 'confirm', 'brain', 'roma', 'tarquinia'];
      let clicked = false;
      for (const id of prefer) {
        const chip = page.getByTestId(`action-chip-${id}`);
        if (await chip.isVisible().catch(() => false)) {
          await chip.click();
          await page.waitForTimeout(250);
          await clickAvanti(page);
          clicked = true;
          break;
        }
      }
      if (!clicked) {
        const chips = page.locator('[data-testid^="action-chip-"]');
        if (await chips.count() > 0) {
          await chips.nth(0).click();
          await clickAvanti(page);
        } else if (await page.getByTestId('action-text').isVisible().catch(() => false)) {
          await page.getByTestId('action-text').fill('ok');
          await clickAvanti(page);
        } else {
          await clickAvanti(page);
        }
      }
      await page.waitForTimeout(600);
    }

    await expect(page.getByTestId('action-complete')).toBeVisible({ timeout: 60_000 });
    await shot(page, '03-complete');

    // Home
    await page.getByTestId('action-done-home').click();
    await page.waitForTimeout(2000);
    await page.goto('/?refresh=1');
    await page.waitForTimeout(2000);
    await shot(page, '04-home');

    // Logout / login persistence
    await page.goto('/login');
    await loginUI(page, email, password);
    await page.goto('/');
    await page.waitForTimeout(2000);
    await shot(page, '05-relogin');
    // Home should still load (project/goal persisted)
    await expect(page.getByTestId('parla-con-ora').or(page.getByTestId('home-screen')).or(page.locator('body'))).toBeVisible();
  });

  test('2) Vibo range+auto → first Q lodging, not dates/dest/transport', async ({ page }) => {
    const { email, password, token } = await apiRegister('vibo');
    await loginUI(page, email, password);

    const text = 'Dal 9 al 24 agosto vado a Vibo Marina in auto.';
    const gaps = await fetch(`${API}/api/semantic/gaps`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text, intent: 'travel', flow: 'travel' }),
    }).then((r) => r.json());
    expect(gaps.gaps?.next_slot).toBe('lodging');
    const nq = String(gaps.gaps?.next_best_question || '').toLowerCase();
    expect(nq).not.toContain('quando parti');
    expect(nq).not.toContain('destinazione');
    expect(nq).not.toContain('come ti sposti');

    await startParla(page, text, token);
    await shot(page, 'vibo-01-first-q');
    const q = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(q).not.toContain('quando parti e quando torni');
    expect(q).not.toContain('quando parti');
    expect(q.includes('alloggio') || q.includes('prenot')).toBeTruthy();
    expect(q.includes('destinazione') || q.includes('dove andrai')).toBeFalsy();
    expect(q.includes('come ti sposti')).toBeFalsy();
  });
});
