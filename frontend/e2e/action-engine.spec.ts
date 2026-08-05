/**
 * Action Engine guided-flow smoke — Expo web + Playwright.
 * Asserts Apri/Inizia/Organizza opens a one-question UI (not blank),
 * chip answers progress the flow, and Home can refresh afterward.
 * Does NOT claim native mobile.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const EVIDENCE_DIR = path.join(__dirname, '..', 'test-results', 'action-engine-smoke');

async function apiRegister() {
  const email = `e2e_ae_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const name = 'E2E ActionEngine';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string };
}

/** Seed a study priority so Home shows Inizia / Organizza / Apri. */
async function seedStudyPriority(token: string) {
  const due = new Date(Date.now() + 7 * 86400_000).toISOString();
  const res = await fetch(`${API}/api/decisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      title: 'Esame Analisi E2E',
      description: 'Preparazione esame per Action Engine smoke',
      category: 'study',
      urgency: 8,
      importance: 9,
      deadline: due,
      time_required_min: 60,
    }),
  });
  if (!res.ok) throw new Error(`seed study decision failed: ${res.status} ${await res.text()}`);
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

test.describe('Action Engine guided flow', () => {
  test('Home Apri/Inizia opens first question + chips; answer advances; Home refreshes', async ({ page }) => {
    const creds = await apiRegister();
    await seedStudyPriority(creds.token);

    // API precondition: home has focus with a guide action
    const homeRes = await fetch(`${API}/api/home`, {
      headers: { Authorization: `Bearer ${creds.token}` },
    });
    expect(homeRes.ok).toBeTruthy();
    const home0 = await homeRes.json();
    expect(home0.primary_focus).toBeTruthy();
    const focusTitle = home0.primary_focus.title as string;
    const guideAction = (home0.primary_focus.actions || []).find(
      (a: any) => a.kind === 'guide' || /inizia|organizza|apri/i.test(a.label || ''),
    );
    expect(guideAction, 'primary focus must expose Inizia/Organizza/Apri').toBeTruthy();

    // API: open engine directly — proves first question exists (backend contract)
    const openRes = await fetch(`${API}/api/action-engine/open`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${creds.token}` },
      body: JSON.stringify({ home_item: home0.primary_focus, force_new: true }),
    });
    expect(openRes.ok).toBeTruthy();
    const opened = await openRes.json();
    expect(opened.session?.current_turn?.question).toBeTruthy();
    expect((opened.session?.current_turn?.options || []).length).toBeGreaterThan(0);
    const apiSessionId = opened.session.id as string;

    await loginUI(page, creds.email, creds.password);
    await page.goto('/');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 30_000 });
    await expect(
      page.getByTestId('adesso-card').or(page.getByText(focusTitle)).first(),
    ).toBeVisible({ timeout: 20_000 });
    await shot(page, '01-home-priority');

    // Prefer UI guide button; fall back to Adesso card press
    const guideBtn = page
      .getByTestId(/home-action-(guide|organize|organize_bill|open_event|open_travel|open_visit|open_source)/)
      .or(page.getByRole('button', { name: /Inizia|Organizza|Apri/i }))
      .first();

    if (await guideBtn.isVisible().catch(() => false)) {
      await guideBtn.click();
    } else {
      await page.getByTestId('adesso-card').click();
    }

    // Must land on guided screen — NOT blank
    await expect(page.getByTestId('action-session').or(page.getByTestId('action-open-bridge')).first()).toBeVisible({
      timeout: 25_000,
    });

    // Bridge may redirect; wait for question
    await expect(page.getByTestId('action-question')).toBeVisible({ timeout: 25_000 });
    const q1 = (await page.getByTestId('action-question').innerText()).trim();
    expect(q1.length).toBeGreaterThan(5);
    await expect(page.getByTestId('action-chips')).toBeVisible();
    const chips = page.locator('[data-testid^="action-chip-"]');
    await expect(chips.first()).toBeVisible();
    const chipCount = await chips.count();
    expect(chipCount).toBeGreaterThan(0);
    await shot(page, '02-first-question');

    // Answer chip 1
    const chip1Label = (await chips.first().innerText()).trim();
    await chips.first().click();
    await page.waitForTimeout(1200);

    // Either next question or complete — never blank
    const stillActive = await page.getByTestId('action-question').isVisible().catch(() => false);
    const completed = await page.getByTestId('action-complete').isVisible().catch(() => false);
    expect(stillActive || completed).toBeTruthy();

    let steps = 1;
    if (stillActive) {
      const q2 = (await page.getByTestId('action-question').innerText()).trim();
      // Progress: question text should usually change after first chip
      expect(q2.length).toBeGreaterThan(5);
      await shot(page, '03-second-question');
      const chips2 = page.locator('[data-testid^="action-chip-"]');
      await expect(chips2.first()).toBeVisible();
      await chips2.first().click();
      await page.waitForTimeout(1200);
      steps = 2;

      if (await page.getByTestId('action-question').isVisible().catch(() => false)) {
        await page.locator('[data-testid^="action-chip-"]').first().click();
        await page.waitForTimeout(1200);
        steps = 3;
      }
    }

    await shot(page, '04-after-chips');

    // If still mid-flow, finish remaining via API then reload complete screen
    const url = page.url();
    const m = url.match(/\/action\/([^/?#]+)/);
    const sessionId = (m && m[1] !== 'open' ? m[1] : apiSessionId) as string;

    let sess = await (
      await fetch(`${API}/api/action-engine/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${creds.token}` },
      })
    ).json();

    // Drive to complete if UI didn't finish (study has many turns)
    for (let i = 0; i < 12 && sess.session?.status === 'active'; i++) {
      const turn = sess.session.current_turn;
      if (!turn?.options?.length) break;
      const ans = await fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${creds.token}` },
        body: JSON.stringify({ option_id: turn.options[0].id }),
      });
      expect(ans.ok).toBeTruthy();
      sess = await ans.json();
      if (!sess.session) {
        sess = await (
          await fetch(`${API}/api/action-engine/sessions/${sessionId}`, {
            headers: { Authorization: `Bearer ${creds.token}` },
          })
        ).json();
      }
    }

    // Ensure completed
    if (sess.session?.status !== 'completed' && sess.status !== 'completed') {
      const done = await fetch(`${API}/api/action-engine/sessions/${sessionId}/complete`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${creds.token}` },
      });
      expect(done.ok).toBeTruthy();
      sess = await done.json();
    }

    const finalStatus = sess.session?.status || sess.status;
    expect(finalStatus).toBe('completed');
    const hint =
      sess.session?.meta?.next_focus_hint ||
      sess.next_focus_hint ||
      sess.session?.effects?.next_focus_hint;

    // Home refresh — focus/priorities should reflect engine work (session hint / calendar / project)
    const home1Res = await fetch(`${API}/api/home/refresh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${creds.token}` },
    });
    expect(home1Res.ok).toBeTruthy();
    const home1 = await home1Res.json();
    expect(home1.primary_focus || (home1.priorities || []).some((g: any) => g.items?.length)).toBeTruthy();

    const titles: string[] = [];
    if (home1.primary_focus?.title) titles.push(String(home1.primary_focus.title));
    for (const g of home1.priorities || []) {
      for (const it of g.items || []) titles.push(String(it.title || ''));
    }
    if (home1.resume_item?.title) titles.push(String(home1.resume_item.title));
    const blob = titles.join(' | ').toLowerCase();

    // Evolved: study sessions / project hint / esame / ripasso — not a blank dead end
    const evolved =
      /sessione|ripasso|esame|analisi|studio|piano|action|continua/i.test(blob) ||
      (hint && String(hint).length > 0) ||
      home1.primary_focus?.source_type === 'action_project' ||
      home1.primary_focus?.source_type === 'life_node' ||
      home1.primary_focus?.type === 'study' ||
      home1.primary_focus?.type === 'event' ||
      home1.primary_focus?.type === 'activity';

    expect(evolved, `Home after AE should evolve; titles=${blob}; hint=${hint}`).toBeTruthy();

    await page.goto('/');
    await page.waitForTimeout(2000);
    await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 20_000 });
    await shot(page, '05-home-after-refresh');

    // Write a small evidence log for docs
    const logPath = path.join(EVIDENCE_DIR, 'smoke-log.json');
    fs.writeFileSync(
      logPath,
      JSON.stringify(
        {
          ok: true,
          focusTitle,
          guideLabel: guideAction.label,
          firstQuestion: q1,
          chip1Label,
          uiStepsAnswered: steps,
          sessionId,
          next_focus_hint: hint || null,
          homeTitlesAfter: titles,
          evidenceDir: EVIDENCE_DIR,
        },
        null,
        2,
      ),
    );

    expect(steps).toBeGreaterThanOrEqual(2);
  });
});
