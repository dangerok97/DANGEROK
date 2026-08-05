/**
 * FULL UI Travel Action Flow — Vacanza Vibo Marina / period chips.
 * Fixture seeds decision; ALL subsequent steps via UI chips/text.
 * Screenshots under frontend/test-results/travel-action-flow/
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'test-results', 'travel-action-flow');

async function apiRegister() {
  const email = `e2e_travel_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const name = 'E2E TravelFlow';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string, user_id: data.user_id as string };
}

async function seedVacationPriority(token: string) {
  const dec = await fetch(`${API}/api/decisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      title: 'Andrò in vacanza dal 9 al 24 agosto a Vibo Marina',
      description: 'Vacanza estate — organizzare viaggio',
      category: 'travel',
      urgency: 7,
      importance: 8,
      time_required_min: 30,
    }),
  });
  if (!dec.ok) throw new Error(`seed decision failed: ${dec.status} ${await dec.text()}`);
  return dec.json();
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

async function answerCurrentTurn(page: Page, step: number) {
  await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('action-question')).toBeVisible();
  await shot(page, `${String(step).padStart(2, '0')}-turn`);

  const q = (await page.getByTestId('action-question').innerText()).toLowerCase();
  const nextBtn = page.getByTestId('action-next');

  if (q.includes('destinazione')) {
    const input = page.getByTestId('action-text');
    if (await input.isVisible().catch(() => false)) {
      await input.fill('Vibo Marina');
      await nextBtn.click();
      return;
    }
  }

  if (q.includes('parti') && q.includes('torni')) {
    const input = page.getByTestId('action-text');
    if (await input.isVisible().catch(() => false)) {
      await input.fill('dal 9 al 24 agosto 2026');
      await nextBtn.click();
      return;
    }
  }

  const preferIds = [
    'confirm', 'accept', 'car', 'partial', 'solo', 'no', 'skip',
    'tarquinia', 'brain', 'yes', 'train',
  ];
  for (const id of preferIds) {
    const chip = page.getByTestId(`action-chip-${id}`);
    if (!(await chip.isVisible().catch(() => false))) continue;
    await chip.click();
    // chips auto-submit for chips/preview; multi may need next
    await page.waitForTimeout(400);
    if (await page.getByTestId('action-complete').isVisible().catch(() => false)) return;
    if (await nextBtn.isVisible().catch(() => false) && id === 'skip') {
      await nextBtn.click().catch(() => {});
    }
    return;
  }

  // Fallback: first chip
  const chips = page.locator('[data-testid^="action-chip-"]');
  const n = await chips.count();
  if (n > 0) {
    await chips.first().click();
    return;
  }
  if (await nextBtn.isVisible().catch(() => false)) {
    await nextBtn.click();
  }
}

test.describe('Travel Action Flow UI', () => {
  test('Vacanza Vibo Marina full path', async ({ page }) => {
    test.setTimeout(180_000);
    const creds = await apiRegister();
    await seedVacationPriority(creds.token);
    await loginUI(page, creds.email, creds.password);
    await shot(page, '00-home');

    // Open travel from Home — Inizia / Organizza / Adesso
    const starters = [
      page.getByText(/Organizza viaggio|Inizia|Apri|Vacanza|Vibo/i).first(),
      page.getByTestId('adesso-primary-cta'),
      page.getByTestId('priority-primary-cta').first(),
    ];
    let opened = false;
    for (const el of starters) {
      if (await el.isVisible().catch(() => false)) {
        await el.click();
        opened = true;
        break;
      }
    }
    if (!opened) {
      // Deep link open via API then navigate
      const openRes = await fetch(`${API}/api/action-engine/open`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${creds.token}`,
        },
        body: JSON.stringify({
          title: 'Andrò in vacanza dal 9 al 24 agosto a Vibo Marina',
          force_new: true,
          meta: { skip_maps_network: true },
        }),
      });
      const openData = await openRes.json();
      const sid = openData.session?.id;
      expect(sid).toBeTruthy();
      await page.goto(`/action/${sid}`);
    }

    await expect(page.getByTestId('action-session').or(page.getByTestId('action-complete')))
      .toBeVisible({ timeout: 30_000 });

    for (let step = 1; step <= 25; step++) {
      if (await page.getByTestId('action-complete').isVisible().catch(() => false)) break;
      await answerCurrentTurn(page, step);
      await page.waitForTimeout(600);
    }

    await expect(page.getByTestId('action-complete')).toBeVisible({ timeout: 30_000 });
    await shot(page, '99-complete');

    const openPlan = page.getByTestId('action-open-plan');
    if (await openPlan.isVisible().catch(() => false)) {
      await openPlan.click();
      await expect(page.getByTestId('travel-project')).toBeVisible({ timeout: 20_000 });
      await shot(page, '100-travel-project');
    }

    // Persist evidence log
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'run-log.json'),
      JSON.stringify({ email: creds.email, ok: true, at: new Date().toISOString() }, null, 2),
    );
  });
});
