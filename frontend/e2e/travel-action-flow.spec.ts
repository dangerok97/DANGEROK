/**
 * FULL UI Travel Action Flow — Vacanza Vibo Marina.
 * Fixture seeds decision; subsequent steps via UI chips/text (API open only as fallback).
 * Screenshots under frontend/test-results/travel-action-flow/
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8001';
// Keep outside Playwright's default test-results wipe directory
const EVIDENCE_DIR = path.join(__dirname, '..', 'e2e-evidence', 'travel-action-flow');

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

  // Period free text
  if ((q.includes('parti') && q.includes('torni')) || q.includes('quando parti')) {
    const input = page.getByTestId('action-text');
    if (await input.isVisible().catch(() => false)) {
      await input.fill('dal 9 al 24 agosto 2026');
      await nextBtn.click();
      await page.waitForTimeout(900);
      return;
    }
  }

  // Destination free text
  if (q.includes('destinazione')) {
    const input = page.getByTestId('action-text');
    if (await input.isVisible().catch(() => false)) {
      await input.fill('Vibo Marina');
      await nextBtn.click();
      await page.waitForTimeout(900);
      return;
    }
  }

  // Prep multi — skip
  if (q.includes('preparazione') || q.includes('suggerimenti')) {
    const skip = page.getByTestId('action-chip-skip');
    if (await skip.isVisible().catch(() => false)) {
      await skip.click();
      await page.waitForTimeout(300);
      if (await nextBtn.isVisible().catch(() => false) && await nextBtn.isEnabled().catch(() => false)) {
        await nextBtn.click();
      }
      await page.waitForTimeout(900);
      return;
    }
  }

  // Prefer explicit chip ids (calendar: no for browser e2e; confirm last)
  const preferIds = [
    'confirm', 'accept', 'car', 'partial', 'solo', 'no',
    'tarquinia', 'brain', 'roma', 'train',
  ];
  for (const id of preferIds) {
    const chip = page.getByTestId(`action-chip-${id}`);
    if (!(await chip.isVisible().catch(() => false))) continue;
    await chip.click();
    await page.waitForTimeout(300);
    if (await page.getByTestId('action-complete').isVisible().catch(() => false)) return;
    if (await nextBtn.isVisible().catch(() => false) && await nextBtn.isEnabled().catch(() => false)) {
      // chips_or_text needs Avanti when only selected without auto-submit
      const kindHint = q;
      if (kindHint.includes('dove parti') || kindHint.includes('destinazione')) {
        await nextBtn.click().catch(() => {});
      }
    }
    await page.waitForTimeout(900);
    return;
  }

  // Fallback first chip
  const chips = page.getByTestId('action-chips').locator('[data-testid^="action-chip-"]');
  const count = await chips.count();
  if (count > 0) {
    await chips.first().click();
    await page.waitForTimeout(300);
    if (await nextBtn.isVisible().catch(() => false) && await nextBtn.isEnabled().catch(() => false)) {
      await nextBtn.click().catch(() => {});
    }
    await page.waitForTimeout(900);
    return;
  }

  if (await nextBtn.isVisible().catch(() => false)) {
    await nextBtn.click();
    await page.waitForTimeout(900);
    return;
  }

  throw new Error(`No way to answer travel turn: ${q}`);
}

test.describe('Travel Action Flow UI', () => {
  test('Vacanza Vibo Marina full path', async ({ page }) => {
    test.setTimeout(180_000);
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

    const creds = await apiRegister();
    await seedVacationPriority(creds.token);

    // Probe travel API on this backend
    const probe = await fetch(`${API}/api/travel-projects`, {
      headers: { Authorization: `Bearer ${creds.token}` },
    });
    expect(probe.status).toBe(200);

    await loginUI(page, creds.email, creds.password);
    await page.goto('/');
    await page.waitForTimeout(2000);
    await shot(page, '00-home');

    // Prefer UI open; fallback API open + navigate (still answers via UI)
    const guideBtn = page
      .getByTestId(/home-action-(guide|organize|open_source|open_travel)/)
      .or(page.getByRole('button', { name: /Inizia|Organizza|Apri/i }))
      .first();
    let openedViaUi = false;
    if (await guideBtn.isVisible().catch(() => false)) {
      await guideBtn.click();
      openedViaUi = true;
    } else if (await page.getByTestId('adesso-card').isVisible().catch(() => false)) {
      await page.getByTestId('adesso-card').click();
      openedViaUi = true;
    }

    if (!openedViaUi || !(await page.getByTestId('action-session').isVisible().catch(() => false))) {
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
      expect(openRes.ok).toBeTruthy();
      expect(openData.session?.flow).toBe('travel');
      const sid = openData.session?.id;
      expect(sid).toBeTruthy();
      await page.goto(`/action/${sid}`);
    }

    await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 30_000 });
    await shot(page, '01-first-question');

    let steps = 0;
    while (steps < 25) {
      if (await page.getByTestId('action-complete').isVisible().catch(() => false)) break;
      await answerCurrentTurn(page, steps + 2);
      steps += 1;
      await page.waitForTimeout(400);
    }

    await expect(page.getByTestId('action-complete')).toBeVisible({ timeout: 30_000 });
    await shot(page, '99-complete');

    const openPlan = page.getByTestId('action-open-plan');
    expect(await openPlan.isVisible()).toBeTruthy();
    await openPlan.click();
    await expect(page.getByTestId('travel-project')).toBeVisible({ timeout: 20_000 });
    await shot(page, '100-travel-project');

    // API: project exists for user
    const list = await fetch(`${API}/api/travel-projects`, {
      headers: { Authorization: `Bearer ${creds.token}` },
    });
    const listed = await list.json();
    const active = (listed.items || []).filter((p: any) => p.status === 'active');
    expect(active.length).toBeGreaterThanOrEqual(1);

    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'run-log.json'),
      JSON.stringify({
        email: creds.email,
        api: API,
        steps_answered_via_ui: steps,
        opened_via_ui: openedViaUi,
        travel_project_id: active[0]?.id,
        destination: active[0]?.destination,
        ok: true,
        at: new Date().toISOString(),
        evidence_dir: EVIDENCE_DIR,
      }, null, 2),
    );
  });
});
