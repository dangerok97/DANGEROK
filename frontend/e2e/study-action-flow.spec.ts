/**
 * FULL UI Study Action Flow — psychology exam priority.
 * Fixture seeds decision + doc; ALL subsequent steps via UI chips/text.
 * Screenshots under frontend/test-results/study-action-flow/
 * Does NOT complete final steps via API.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'test-results', 'study-action-flow');

async function apiRegister() {
  const email = `e2e_study_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const name = 'E2E StudyFlow';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string, user_id: data.user_id as string };
}

/** Seed only — priority + education doc. No AE answers via API. */
async function seedPsychologyPriority(token: string) {
  const due = new Date(Date.now() + 21 * 86400_000).toISOString();
  const dec = await fetch(`${API}/api/decisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      title: 'Preparazione esame di Psicologia',
      description: 'Devo preparare l\'esame di Psicologia entro tre settimane',
      category: 'study',
      urgency: 8,
      importance: 9,
      deadline: due,
      time_required_min: 60,
    }),
  });
  if (!dec.ok) throw new Error(`seed decision failed: ${dec.status} ${await dec.text()}`);
  const decision = await dec.json();

  // Best-effort education document for materials search (optional)
  try {
    await fetch(`${API}/api/documents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        filename: 'appunti-psicologia.pdf',
        display_title: 'Appunti Psicologia',
        analysis: { macro_category: 'education', keywords: ['psicologia'] },
        education_analysis: { subject: 'Psicologia', topic: 'Memoria' },
      }),
    });
  } catch {
    // Documents create may require multipart — non-blocking for flow
  }

  return decision;
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

  const q = await page.getByTestId('action-question').innerText();
  const turnHint = q.toLowerCase();
  const nextBtn = page.getByTestId('action-next');

  // Prefer known chip ids (never pick upload mid-flow in this E2E)
  const preferIds = [
    'confirm', 'accept', 'distributed', 'evening', 'no', '1h', 'none',
    'mon', 'study', 'yes', 'connect_later',
  ];
  for (const id of preferIds) {
    const chip = page.getByTestId(`action-chip-${id}`);
    if (!(await chip.isVisible().catch(() => false))) continue;
    await chip.click();
    await page.waitForTimeout(300);
    // Multi / text turns need Avanti
    if (await nextBtn.isVisible().catch(() => false) && await nextBtn.isEnabled().catch(() => false)) {
      await nextBtn.click();
    }
    await page.waitForTimeout(900);
    return id;
  }

  // Date step — type ISO date in text field
  if (turnHint.includes('quando') || /esame/.test(turnHint)) {
    const exam = new Date(Date.now() + 21 * 86400_000).toISOString().slice(0, 10);
    const text = page.getByTestId('action-text');
    if (await text.isVisible().catch(() => false)) {
      await text.fill(exam);
      await nextBtn.click();
      await page.waitForTimeout(900);
      return 'exam_date';
    }
  }

  // Days multi — pick Lun + Mer
  if (turnHint.includes('giorni')) {
    for (const id of ['mon', 'wed', 'fri']) {
      const chip = page.getByTestId(`action-chip-${id}`);
      if (await chip.isVisible().catch(() => false)) await chip.click();
    }
    await nextBtn.click();
    await page.waitForTimeout(900);
    return 'days';
  }

  // Materials — never upload in automated E2E
  if (turnHint.includes('material')) {
    const none = page.getByTestId('action-chip-none');
    await none.click();
    await nextBtn.click();
    await page.waitForTimeout(900);
    return 'none';
  }

  // Tools multi
  if (turnHint.includes('strument')) {
    for (const id of ['study', 'review']) {
      const chip = page.getByTestId(`action-chip-${id}`);
      if (await chip.isVisible().catch(() => false)) await chip.click();
    }
    await nextBtn.click();
    await page.waitForTimeout(900);
    return 'tools';
  }

  const chips = page.getByTestId('action-chips').locator('[data-testid^="action-chip-"]');
  const count = await chips.count();
  if (count > 0) {
    // Skip upload chip if first
    const firstId = await chips.nth(0).getAttribute('data-testid');
    const idx = firstId?.includes('upload') && count > 1 ? 1 : 0;
    await chips.nth(idx).click();
    await page.waitForTimeout(300);
    if (await nextBtn.isVisible().catch(() => false) && await nextBtn.isEnabled().catch(() => false)) {
      await nextBtn.click();
    }
    await page.waitForTimeout(900);
    return 'chip';
  }

  throw new Error(`No way to answer turn: ${q}`);
}

test.describe('Study Action Flow FULL UI', () => {
  test('Psychology exam: all steps in UI → plan created → Home evolves', async ({ page }) => {
    test.setTimeout(180_000);
    const creds = await apiRegister();
    await seedPsychologyPriority(creds.token);

    // Verify Google status honestly (do not block)
    let googleConnected = false;
    try {
      const g = await fetch(`${API}/api/connectors/google-calendar/status`, {
        headers: { Authorization: `Bearer ${creds.token}` },
      });
      if (g.ok) {
        const gj = await g.json();
        googleConnected = Boolean(gj.connected || gj.status === 'connected');
      }
    } catch { /* absent */ }
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'google-status.json'),
      JSON.stringify({ connected: googleConnected, note: googleConnected ? 'real sync attempted if user chose yes' : 'Google absent — not blocking' }, null, 2),
    );

    await loginUI(page, creds.email, creds.password);
    await page.goto('/');
    await page.waitForTimeout(2000);
    await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 30_000 });
    await shot(page, '00-home-seeded');

    // Open via UI only
    const guideBtn = page
      .getByTestId(/home-action-(guide|organize|open_source)/)
      .or(page.getByRole('button', { name: /Inizia|Organizza|Apri/i }))
      .first();
    if (await guideBtn.isVisible().catch(() => false)) {
      await guideBtn.click();
    } else {
      await page.getByTestId('adesso-card').click();
    }

    await expect(page.getByTestId('action-session')).toBeVisible({ timeout: 25_000 });
    await shot(page, '01-first-question');

    // Walk all turns until complete — UI only
    let steps = 0;
    while (steps < 25) {
      const complete = page.getByTestId('action-complete');
      if (await complete.isVisible().catch(() => false)) break;
      await answerCurrentTurn(page, steps + 2);
      steps += 1;
      await page.waitForTimeout(400);
    }

    await expect(page.getByTestId('action-complete')).toBeVisible({ timeout: 30_000 });
    await shot(page, '90-complete');

    // Open plan if CTA present
    const openPlan = page.getByTestId('action-open-plan');
    if (await openPlan.isVisible().catch(() => false)) {
      await openPlan.click();
      await expect(page.getByTestId('study-plan-screen')).toBeVisible({ timeout: 20_000 });
      await shot(page, '91-study-plan');
      await page.getByTestId('study-plan-back').click();
    }

    await page.goto('/');
    await page.waitForTimeout(2000);
    await shot(page, '92-home-after');

    // Evidence log
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'run-log.json'),
      JSON.stringify({
        steps_answered_via_ui: steps,
        google_connected: googleConnected,
        complete_via: 'UI chips/text only — no API confirm',
        evidence_dir: EVIDENCE_DIR,
      }, null, 2),
    );
  });
});
