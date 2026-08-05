/**
 * Intent Classification → Action Engine regression (Expo web + Playwright).
 * Priority "devo studiare l'esame di psicologia" must open STUDY flow,
 * never EVENT ticket question.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'test-results', 'intent-psychology');

async function apiRegister() {
  const email = `e2e_ie_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const name = 'E2E IntentPsych';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string };
}

async function seedPsychologyPriority(token: string) {
  // Intentionally omit category / use wrong event — Intent Engine must fix routing
  const res = await fetch(`${API}/api/decisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      title: "devo studiare l'esame di psicologia",
      description: 'Priorità creata da testo libero',
      category: 'event',
      urgency: 8,
      importance: 9,
      deadline: new Date(Date.now() + 14 * 86400_000).toISOString(),
      time_required_min: 90,
    }),
  });
  if (!res.ok) throw new Error(`seed failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function loginUI(page: Page, email: string, password: string) {
  await page.goto('/login');
  await expect(page.getByTestId('login-title')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(email);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-button').click();
  await page.waitForURL(/tabs|\/$|\(tabs\)/, { timeout: 30_000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const p = path.join(EVIDENCE_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  return p;
}

test.describe('Intent Engine psychology exam', () => {
  test('study phrase opens study flow — NOT ticket/event', async ({ page }) => {
    const creds = await apiRegister();
    const decision = await seedPsychologyPriority(creds.token);
    expect(decision.intent || decision.category).toBeTruthy();
    // Create path should have classified as study despite category:event input
    if (decision.intent) {
      expect(decision.intent).toBe('study');
      expect(decision.intent_subtype).toBe('exam_preparation');
    }

    const openRes = await fetch(`${API}/api/action-engine/open`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${creds.token}` },
      body: JSON.stringify({
        title: "devo studiare l'esame di psicologia",
        item_type: 'event',
        source_type: 'decision',
        source_id: decision.id,
        force_new: true,
      }),
    });
    expect(openRes.ok, `open status ${openRes.status} body=${await openRes.clone().text()}`).toBeTruthy();
    const opened = await openRes.json();
    expect(opened.session.flow).toBe('study');
    expect(opened.intent?.intent).toBe('study');
    const apiQ = (opened.session.current_turn?.question || '').toLowerCase();
    expect(apiQ).not.toContain('biglietto');
    expect(apiQ).toMatch(/esame|quando|material/);

    await loginUI(page, creds.email, creds.password);
    await page.goto('/');
    await page.waitForTimeout(2000);
    await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/psicologia/i).first()).toBeVisible({ timeout: 20_000 });
    await shot(page, '01-home-psychology');

    const guideBtn = page
      .getByTestId(/home-action-(guide|organize|organize_bill|open_event|open_travel|open_visit|open_source)/)
      .or(page.getByRole('button', { name: /Inizia|Organizza|Apri/i }))
      .first();

    if (await guideBtn.isVisible().catch(() => false)) {
      await guideBtn.click();
    } else {
      await page.getByTestId('adesso-card').click();
    }

    await expect(page.getByTestId('action-session').or(page.getByTestId('action-open-bridge')).first()).toBeVisible({
      timeout: 25_000,
    });
    await expect(page.getByTestId('action-question')).toBeVisible({ timeout: 25_000 });
    const q1 = (await page.getByTestId('action-question').innerText()).trim();
    expect(q1.toLowerCase()).not.toContain('biglietto');
    expect(q1.toLowerCase()).toMatch(/esame|quando|materiale|documento/);
    await shot(page, '02-study-first-question');

    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'psychology-log.json'),
      JSON.stringify(
        {
          ok: true,
          decisionId: decision.id,
          decisionIntent: decision.intent,
          apiFlow: opened.session.flow,
          apiQuestion: opened.session.current_turn?.question,
          uiQuestion: q1,
        },
        null,
        2,
      ),
    );
  });
});
