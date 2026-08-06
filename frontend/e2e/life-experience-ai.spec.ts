/**
 * AI-first Life Experience E2E
 * Nuovo utente → conversazione → upload rogito → cambio piano → interrupt → resume
 * → Home benefici → Proactive — mai wizard.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'e2e-evidence', 'life-experience');

async function apiRegister(prefix: string) {
  const email = `e2e_le_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E LE ${prefix}` }),
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
  await page
    .waitForURL(/tabs|life-setup|\/$|\(tabs\)/, { timeout: 45_000 })
    .catch(() => {});
  await page.waitForTimeout(2000);
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, `${name}.png`), fullPage: true });
}

test.describe('Life Experience AI-first', () => {
  test('conversazione → rogito → piano → interrupt → resume → Home benefici → Proactive', async ({
    page,
  }) => {
    const { email, password, token } = await apiRegister('full');

    // 1) Start — natural conversation, not wizard
    const start = await fetch(`${API}/api/life-setup/start`, {
      method: 'POST',
      headers: auth(token),
      body: '{}',
    });
    const startBody = await start.json();
    expect(start.ok).toBeTruthy();
    expect(startBody.wizard).toBeFalsy();
    expect(startBody.turn?.ui?.wizard).toBeFalsy();
    expect(startBody.turn?.ui?.progress_bar).toBeFalsy();
    expect(String(startBody.turn?.text || '')).toMatch(/ORA|conversazione|questionario/i);

    // 2) Casa → plan prefers rogito
    const ans = await fetch(`${API}/api/life-setup/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text: 'Ho comprato casa.' }),
    });
    const ansBody = await ans.json();
    expect(ans.ok).toBeTruthy();
    const plan1 = ansBody.turn?.plan || {};
    const q1 = String(ansBody.turn?.question || ansBody.turn?.text || '');
    expect(
      plan1.prefer_document === true ||
        plan1.recommended_document?.doc_type === 'rogito' ||
        /rogito/i.test(q1),
    ).toBeTruthy();
    expect(ansBody.turn?.expected_benefit || plan1.expected_benefit).toBeTruthy();
    // One question only
    expect((q1.match(/\?/g) || []).length).toBeLessThanOrEqual(2);

    // 3) Upload rogito → plan changes
    const up = await fetch(`${API}/api/life-setup/upload-doc`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        doc_type: 'rogito',
        synthetic_text: 'ROGITO Atto di compravendita Via Roma 10 Milano 2026',
        filename: 'rogito-e2e.txt',
      }),
    });
    const upBody = await up.json();
    expect(up.ok).toBeTruthy();
    expect(upBody.wizard).toBeFalsy();
    expect(upBody.profile?.domains?.casa).toBeTruthy();
    const plan2 = upBody.turn?.plan || {};
    const q2 = String(upBody.turn?.question || upBody.turn?.text || '').toLowerCase();
    // After rogito, should NOT only re-ask rogito
    expect(q2.includes('rogito') && plan2?.meta?.gap_key === 'doc.rogito').toBeFalsy();
    expect(
      /mutuo|bolletta|polizza|utenze|assicur|altro|concludere|documento/i.test(q2) ||
        plan2?.meta?.gap_key !== 'doc.rogito',
    ).toBeTruthy();

    // 4) Interrupt
    const cancel = await fetch(`${API}/api/life-setup/cancel`, {
      method: 'POST',
      headers: auth(token),
      body: '{}',
    });
    const cancelBody = await cancel.json();
    expect(cancelBody.should_show).toBeFalsy();
    expect(cancelBody.module_visible).toBeFalsy();
    const resumeTitle = String(cancelBody.resume_suggestion?.title || '').toLowerCase();
    expect(resumeTitle).not.toContain('completa il profilo');
    expect(resumeTitle).not.toContain('life setup');

    // 5) Resume with force
    const resume = await fetch(`${API}/api/life-setup/start`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ force: true }),
    });
    const resumeBody = await resume.json();
    expect(resume.ok).toBeTruthy();
    expect(resumeBody.wizard).toBeFalsy();

    // Answer mutuo to activate benefit chain
    await fetch(`${API}/api/life-setup/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text: 'Sì, ho un mutuo da seguire.' }),
    });

    // Complete
    const done = await fetch(`${API}/api/life-setup/complete`, {
      method: 'POST',
      headers: auth(token),
      body: '{}',
    });
    const doneBody = await done.json();
    expect(doneBody.should_show).toBeFalsy();
    expect(doneBody.module_visible).toBeFalsy();

    // 6) Home — benefits Italian, no Life Setup section / wizard CTA
    const home = await fetch(`${API}/api/home`, { headers: auth(token) });
    const homeBody = await home.json().catch(() => ({}));
    const buckets: any[] = [];
    if (homeBody.primary_focus) buckets.push(homeBody.primary_focus);
    for (const p of homeBody.priorities || []) {
      for (const it of p.items || []) buckets.push(it);
    }
    for (const it of homeBody.insights || []) buckets.push(it);
    const benefitItems = buckets.filter(
      (it) => it?.subtype === 'life_benefit' || /adesso posso/i.test(String(it?.title || '')),
    );
    expect(benefitItems.length).toBeGreaterThan(0);
    for (const it of benefitItems) {
      const t = `${it.title || ''} ${it.description || ''}`.toLowerCase();
      expect(t).not.toContain('completa il profilo');
      expect(t).not.toContain('life setup');
      expect(t).toMatch(/adesso posso|mutuo|casa|document/);
    }

    // 7) Proactive — benefit reason, never completa profilo
    const pro = await fetch(`${API}/api/suggestions`, {
      method: 'GET',
      headers: auth(token),
    }).catch(() => null);
    if (pro && pro.ok) {
      const proBody = await pro.json();
      const proText = JSON.stringify(proBody).toLowerCase();
      expect(proText).not.toContain('completa il profilo');
    }

    // UI path
    await loginUI(page, email, password);
    await page.goto('/life-setup');
    await page.waitForTimeout(2000);
    const onConv = await page.getByTestId('life-setup-conversation').isVisible().catch(() => false);
    if (onConv) {
      await expect(page.getByTestId('life-setup-not-wizard')).toBeAttached();
      await expect(page.getByTestId('life-experience-root')).toBeAttached();
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.toLowerCase()).not.toContain('completa il profilo');
      await shot(page, '01-no-wizard');
    } else {
      await page.goto('/(tabs)');
      await page.waitForTimeout(1500);
      const homeUi = await page.locator('body').innerText();
      expect(homeUi.toLowerCase()).not.toMatch(/completa il profilo|life setup section/i);
      await shot(page, '02-home-benefits');
    }
  });

  test('UI: conversazione naturale + upload + explain + exit', async ({ page }) => {
    const { email, password } = await apiRegister('ui');
    await loginUI(page, email, password);
    const conv = page.getByTestId('life-setup-conversation');
    const loading = page.getByTestId('life-setup-loading');
    const landed = await conv.or(loading).isVisible().catch(() => false);
    if (!landed) {
      await page.goto('/life-setup');
      await page.waitForTimeout(1500);
    }
    await expect(page.getByTestId('life-setup-conversation')).toBeVisible({ timeout: 45_000 });
    await expect(page.getByTestId('life-setup-not-wizard')).toBeAttached();
    await expect(page.getByTestId('wizard-step')).toHaveCount(0);
    await expect(page.getByTestId('life-setup-progress-bar')).toHaveCount(0);

    await page.getByTestId('life-setup-input').fill('Ho comprato casa.');
    await page.getByTestId('life-setup-send').click();
    await page.waitForTimeout(2000);
    await shot(page, '03-after-casa');

    const upload = page.getByTestId('life-setup-upload-doc');
    if (await upload.isVisible().catch(() => false)) {
      await upload.click();
      await page.waitForTimeout(2000);
      await shot(page, '04-after-rogito');
    }

    if (await page.getByTestId('life-setup-why').isVisible().catch(() => false)) {
      await page.getByTestId('life-setup-why').click();
      await page.waitForTimeout(800);
      const expl = page.getByTestId('life-setup-explain');
      if (await expl.isVisible().catch(() => false)) {
        const t = (await expl.innerText()).toLowerCase();
        expect(t).not.toContain('chain of thought');
        expect(t.length).toBeGreaterThan(10);
      }
    }

    await page.getByTestId('life-setup-exit').click();
    await page.waitForTimeout(1500);
    await shot(page, '05-after-exit');
  });
});
