/**
 * Semantic Extraction + Gap Analyzer E2E
 * 1) Bug: "Fra due settimane parto." must NOT ask "Quando parti e quando torni?"
 * 2) Vibo full extraction → lodging first
 * Persist after refresh.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8001';
const EVIDENCE_DIR = path.join(__dirname, '..', 'e2e-evidence', 'semantic-extraction-gap');

async function apiRegister() {
  const email = `e2e_sem_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: 'E2E Semantic' }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string };
}

async function loginUI(page: Page, email: string, password: string) {
  await page.goto('/login');
  await expect(page.getByTestId('login-title')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(email);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-button').click();
  await page.waitForURL(/tabs|\/$|\(tabs\)/, { timeout: 30_000 }).catch(() => {});
  await page.waitForTimeout(1200);
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, `${name}.png`), fullPage: true });
}

test.describe('Semantic extraction gap analyzer', () => {
  test('Fra due settimane parto → Dove andrai? (never combo dates)', async ({ page }) => {
    const { email, password, token } = await apiRegister();

    // API proof first
    const pipe = await fetch(`${API}/api/semantic/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text: 'Fra due settimane parto.', use_gemini: false }),
    });
    expect(pipe.ok).toBeTruthy();
    const body = await pipe.json();
    const nextQ = String(
      body?.extraction?.meta?.next_question
      || body?.extraction?.meta?.next_slot
      || '',
    ).toLowerCase();
    // Also start conversation
    const start = await fetch(`${API}/api/conversation/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text: 'Fra due settimane parto.', origin: 'text' }),
    });
    expect(start.ok).toBeTruthy();
    const started = await start.json();
    const firstQ = String(
      started?.first_question
      || started?.action_session?.current_turn?.question
      || '',
    );
    expect(firstQ.toLowerCase()).not.toContain('quando parti e quando torni');
    expect(firstQ.toLowerCase()).toMatch(/dove/);

    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'fra-due-settimane.json'),
      JSON.stringify({ extraction: body, conversation: started, firstQ }, null, 2),
      'utf-8',
    );

    await loginUI(page, email, password);
    const actionId = started?.action_session?.id || started?.session?.action_session_id;
    expect(actionId).toBeTruthy();
    await page.goto(`/action/${actionId}`);
    await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 20_000 });
    const uiQ = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(uiQ).not.toContain('quando parti e quando torni');
    expect(uiQ).toMatch(/dove/);
    await shot(page, '01-fra-due-settimane-destination');

    // Answer destination → return only
    const input = page.getByTestId('action-text');
    if (await input.isVisible().catch(() => false)) {
      await input.fill('Vibo Marina');
      await page.getByTestId('action-next').click();
      await page.waitForTimeout(1000);
    }
    await expect(page.getByTestId('action-question')).toBeVisible();
    const q2 = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(q2).not.toContain('quando parti e quando torni');
    expect(q2).toMatch(/rientra|ritorno|torn/);
    await shot(page, '02-after-vibo-return-only');

    // Persist after refresh
    await page.reload();
    await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 20_000 });
    const q3 = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(q3).not.toContain('quando parti e quando torni');
    await shot(page, '03-after-refresh');
  });

  test('Vibo full extraction → lodging first', async ({ page }) => {
    const { email, password, token } = await apiRegister();
    const text = 'Dal 9 al 24 agosto vado a Vibo Marina in auto.';
    const start = await fetch(`${API}/api/conversation/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text, origin: 'text' }),
    });
    expect(start.ok).toBeTruthy();
    const started = await start.json();
    const firstQ = String(
      started?.first_question
      || started?.action_session?.current_turn?.question
      || '',
    ).toLowerCase();
    expect(firstQ).not.toContain('quando parti');
    expect(firstQ).toMatch(/alloggio|prenotaz/);

    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'vibo-full.json'),
      JSON.stringify(started, null, 2),
      'utf-8',
    );

    await loginUI(page, email, password);
    const actionId = started?.action_session?.id || started?.session?.action_session_id;
    await page.goto(`/action/${actionId}`);
    await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 20_000 });
    const uiQ = (await page.getByTestId('action-question').innerText()).toLowerCase();
    expect(uiQ).toMatch(/alloggio|prenotaz/);
    // Understood summary should show Partenza / Destinazione / Ritorno without technical keys
    const summary = page.getByTestId('understood-summary');
    if (await summary.isVisible().catch(() => false)) {
      const txt = await summary.innerText();
      expect(txt.toLowerCase()).not.toContain('departure_date');
      expect(txt).toMatch(/Partenza|Destinazione|Ritorno/);
    }
    await shot(page, '10-vibo-lodging-first');
  });
});
