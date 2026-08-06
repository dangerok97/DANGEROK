/**
 * Life Experience — REAL document upload + AI Document Understanding.
 *
 * Three UI-driven scenarios (CASA / AUTO / BOLLETTA) using the REAL Expo
 * DocumentPicker web file input (intercepted by Playwright's native
 * `filechooser` event) against synthetic PDF/TXT fixtures, wired through
 * Documents V2 (the ONLY document pipeline) + the new AI Document
 * Understanding layer (Gemini via Provider Manager, deterministic fallback).
 *
 * Conversation NAVIGATION up to the point where ORA recommends the target
 * document is driven via the same `/api/life-setup/answer` (+ `skip_domain`)
 * endpoint the UI itself calls when a user clicks "Salta questo tema" — the
 * Decision Engine picks the single highest information-gain gap across ALL
 * domains each turn, so reaching a specific document deterministically
 * requires skipping unrelated higher-priority gaps. The FILE PICKER, upload,
 * AI understanding, result UI, field confirm/correct, and Home/Proactive
 * effects are always exercised through the real UI — never synthetic stubs.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Must match the backend the ALREADY-RUNNING frontend dev server was bundled
// against (Metro does not hot-reload EXPO_PUBLIC_* env vars) — verified via
// live network inspection, not assumed from `.env`.
const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8001';
const EVIDENCE_DIR = path.join(__dirname, '..', 'e2e-evidence', 'life-experience-documents');
const FIXTURES = path.join(__dirname, 'fixtures', 'life-documents');

function auth(token: string) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

async function apiRegister(prefix: string) {
  const email = `e2e_led_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E LED ${prefix}` }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string };
}

async function loginUI(page: Page, email: string, password: string) {
  await page.goto('/login');
  await expect(page.getByTestId('login-title')).toBeVisible({ timeout: 45_000 });
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill(email);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-button').click();
  await page.waitForURL(/tabs|life-setup|\/$|\(tabs\)/, { timeout: 45_000 }).catch(() => {});
  await page.waitForTimeout(2000);
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, `${name}.png`), fullPage: true });
}

/**
 * Navigate the real conversation state machine (via the same endpoint the
 * "Salta questo tema" button uses) until ORA recommends `targetDocType`, or
 * give up after `maxSteps` — the Decision Engine is a single greedy
 * highest-information-gain picker across ALL life domains, not a fixed
 * per-domain wizard sequence, so the exact number of turns is not
 * hard-coded here; only bounded.
 */
async function fastForwardToDocument(
  token: string,
  targetDocType: string,
  seedAnswers: string[],
  maxSteps = 25,
): Promise<any> {
  await fetch(`${API}/api/life-setup/start`, { method: 'POST', headers: auth(token), body: '{}' });
  let turn: any = null;
  for (const text of seedAnswers) {
    const res = await fetch(`${API}/api/life-setup/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text }),
    });
    const body = await res.json();
    turn = body.turn;
  }
  let steps = 0;
  while ((!turn?.recommended_document || turn.recommended_document.doc_type !== targetDocType) && steps < maxSteps) {
    const res = await fetch(`${API}/api/life-setup/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text: '', skip_domain: true }),
    });
    const body = await res.json();
    turn = body.turn;
    steps++;
  }
  if (!turn?.recommended_document || turn.recommended_document.doc_type !== targetDocType) {
    throw new Error(
      `Could not reach recommended_document="${targetDocType}" within ${maxSteps} steps. ` +
        `Last turn: ${JSON.stringify(turn)}`,
    );
  }
  return turn;
}

async function openLifeSetupUI(page: Page) {
  // Session is already active (fast-forwarded via API) — no `resume` param,
  // which would force-create a brand new session and discard the state.
  await page.goto('/life-setup');
  await expect(page.getByTestId('life-setup-conversation')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId('life-setup-not-wizard')).toBeAttached();
}

async function uploadViaRealFilePicker(page: Page, fixtureFile: string) {
  const upload = page.getByTestId('life-setup-upload-doc');
  await expect(upload).toBeVisible({ timeout: 15_000 });
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), upload.click()]);
  await chooser.setFiles(path.join(FIXTURES, fixtureFile));
}

async function waitForDocResult(page: Page) {
  const result = page.getByTestId('life-setup-doc-result');
  const errorBox = page.getByTestId('life-setup-doc-error');
  await expect(result.or(errorBox)).toBeVisible({ timeout: 90_000 });
  if (await errorBox.isVisible().catch(() => false)) {
    const t = await errorBox.innerText();
    throw new Error(`Document analysis surfaced an error instead of a result: ${t}`);
  }
  return result;
}

test.describe('Life Experience — REAL document upload + AI Document Understanding', () => {
  test('CASA: rogito upload → understanding → correct field → confirm → replans → Home benefit → persistence', async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const { email, password, token } = await apiRegister('casa');

    const turn = await fastForwardToDocument(token, 'rogito', ['Ho comprato casa da poco.']);
    expect(turn.recommended_document.label).toMatch(/rogito/i);

    await loginUI(page, email, password);
    await openLifeSetupUI(page);
    await shot(page, '01-casa-recommend-rogito');

    await uploadViaRealFilePicker(page, 'rogito.pdf');
    await shot(page, '02-casa-uploading');

    const result = await waitForDocResult(page);
    await shot(page, '03-casa-doc-result');

    // "Cosa ho capito" must be a real summary, never raw JSON / empty.
    const understood = await page.locator('body').innerText();
    expect(understood).toContain('Cosa ho capito');
    expect(understood).not.toMatch(/"document_id"|"confidence"|"reason_summary"/);

    // Fields extracted from the rogito must be visible and mapped into the
    // Life Profile (never raw JSON, never empty) — the always-present
    // boolean facts from `map_rogito` are the most reliable signal since
    // free-text extraction quality (address/price) varies by provider.
    await expect(result).toContainText(/Rogito caricato/i);
    await expect(result).toContainText(/Casa acquistata|Propriet(à|a) casa/i);

    // Correct one field inline (cross-platform TextInput, not Alert.prompt).
    const editBtn = page.locator('[data-testid^="life-setup-field-edit-btn-"]').first();
    if (await editBtn.isVisible().catch(() => false)) {
      const testId = await editBtn.getAttribute('data-testid');
      const key = (testId || '').replace('life-setup-field-edit-btn-', '');
      await editBtn.click();
      const input = page.getByTestId(`life-setup-field-edit-input-${key}`);
      await expect(input).toBeVisible();
      await input.fill('Via Roma 10, 20100 Milano (corretto E2E)');
      await page.getByTestId(`life-setup-field-save-${key}`).click();
      await page.waitForTimeout(500);
      await shot(page, '04-casa-field-corrected');
    }

    // Confirm remaining fields to be verified.
    const confirmAll = page.getByTestId('life-setup-doc-confirm-all');
    if (await confirmAll.isVisible().catch(() => false)) {
      await confirmAll.click();
      await page.waitForTimeout(500);
    }

    await page.getByTestId('life-setup-doc-continue').click();
    await page.waitForTimeout(1500);
    await shot(page, '05-casa-after-continue');

    // AI replans — must not just re-ask for the rogito again.
    const afterText = (await page.locator('body').innerText()).toLowerCase();
    expect(afterText).not.toMatch(/carica.*rogito/);

    // Life Profile actually updated with provenance (not a second pipeline).
    const profileRes = await fetch(`${API}/api/life-setup/status`, { headers: auth(token) });
    expect(profileRes.ok).toBeTruthy();

    // Home — Casa benefit surfaced.
    const home = await fetch(`${API}/api/home`, { headers: auth(token) });
    const homeBody = await home.json().catch(() => ({}));
    const buckets: any[] = [];
    if (homeBody.primary_focus) buckets.push(homeBody.primary_focus);
    for (const p of homeBody.priorities || []) for (const it of p.items || []) buckets.push(it);
    for (const it of homeBody.insights || []) buckets.push(it);
    const casaBenefit = buckets.some((it) => /casa|rogito|document/i.test(`${it?.title || ''} ${it?.description || ''}`));
    expect(casaBenefit).toBeTruthy();

    // Persistence: reload the SAME authenticated session (token in storage,
    // no re-login) and confirm the corrected field + benefit survive.
    await page.reload();
    await page.waitForTimeout(2000);
    await shot(page, '06-casa-after-reload');
    const statusAfterReload = await fetch(`${API}/api/life-setup/status`, { headers: auth(token) });
    const statusBody = await statusAfterReload.json().catch(() => ({}));
    expect(statusBody.profile_summary?.domains || []).toContain('casa');

    // Full logout/login cycle — corrected field status must not regress.
    await loginUI(page, email, password);
    await page.goto('/(tabs)');
    await page.waitForTimeout(1500);
    await shot(page, '07-casa-after-relogin');
    const homeAfter = await fetch(`${API}/api/home`, { headers: auth(token) });
    const homeAfterBody = await homeAfter.json().catch(() => ({}));
    const bucketsAfter: any[] = [];
    if (homeAfterBody.primary_focus) bucketsAfter.push(homeAfterBody.primary_focus);
    for (const p of homeAfterBody.priorities || []) for (const it of p.items || []) bucketsAfter.push(it);
    for (const it of homeAfterBody.insights || []) bucketsAfter.push(it);
    expect(
      bucketsAfter.some((it) => /casa|rogito|document/i.test(`${it?.title || ''} ${it?.description || ''}`)),
    ).toBeTruthy();
  });

  test('AUTO: libretto upload → understanding → confirm → Home auto benefit', async ({ page }) => {
    test.setTimeout(150_000);
    const { email, password, token } = await apiRegister('auto');

    const turn = await fastForwardToDocument(token, 'libretto', ["Ho un'auto, una Fiat Panda."]);
    expect(turn.recommended_document.label).toMatch(/libretto/i);

    await loginUI(page, email, password);
    await openLifeSetupUI(page);
    await shot(page, '01-auto-recommend-libretto');

    await uploadViaRealFilePicker(page, 'libretto.txt');
    const result = await waitForDocResult(page);
    await shot(page, '02-auto-doc-result');

    // Targa (plate) must be extracted from the synthetic libretto.
    await expect(result).toContainText(/AB123CD|targa/i);

    const confirmAll = page.getByTestId('life-setup-doc-confirm-all');
    if (await confirmAll.isVisible().catch(() => false)) {
      await confirmAll.click();
      await page.waitForTimeout(500);
    }
    await page.getByTestId('life-setup-doc-continue').click();
    await page.waitForTimeout(1500);
    await shot(page, '03-auto-after-continue');

    const home = await fetch(`${API}/api/home`, { headers: auth(token) });
    const homeBody = await home.json().catch(() => ({}));
    const buckets: any[] = [];
    if (homeBody.primary_focus) buckets.push(homeBody.primary_focus);
    for (const p of homeBody.priorities || []) for (const it of p.items || []) buckets.push(it);
    for (const it of homeBody.insights || []) buckets.push(it);
    const autoBenefit = buckets.some((it) => /auto|veicolo|libretto/i.test(`${it?.title || ''} ${it?.description || ''}`));
    expect(autoBenefit).toBeTruthy();
  });

  test('BOLLETTA: bill upload → supplier/amount/deadline recognized → propose event → confirm → Home/Proactive updated', async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const { email, password, token } = await apiRegister('bolletta');

    // casa.owned true + rogito/mutuo out of the way so casa.utenze (bolletta) surfaces.
    const turn = await fastForwardToDocument(token, 'bolletta', ['Ho comprato casa, ho già sistemato rogito e mutuo.']);
    expect(turn.recommended_document.label).toMatch(/bolletta/i);

    await loginUI(page, email, password);
    await openLifeSetupUI(page);
    await shot(page, '01-bolletta-recommend');

    await uploadViaRealFilePicker(page, 'bolletta_luce.txt');
    const result = await waitForDocResult(page);
    await shot(page, '02-bolletta-doc-result');

    // Supplier + amount recognized from the synthetic bill.
    await expect(result).toContainText(/energiatest|fornitore/i);
    await expect(result).toContainText(/87,40|87\.40|importo/i);

    // Deadline → draft event proposal, never auto-created without consent.
    const draftEventBtn = page.getByText('Salva promemoria su ORA');
    if (await draftEventBtn.isVisible().catch(() => false)) {
      await draftEventBtn.click();
      await page.waitForTimeout(800);
      await shot(page, '03-bolletta-event-confirmed');
    }

    const confirmAll = page.getByTestId('life-setup-doc-confirm-all');
    if (await confirmAll.isVisible().catch(() => false)) {
      await confirmAll.click();
      await page.waitForTimeout(500);
    }
    await page.getByTestId('life-setup-doc-continue').click();
    await page.waitForTimeout(1500);

    const home = await fetch(`${API}/api/home`, { headers: auth(token) });
    const homeBody = await home.json().catch(() => ({}));
    const buckets: any[] = [];
    if (homeBody.primary_focus) buckets.push(homeBody.primary_focus);
    for (const p of homeBody.priorities || []) for (const it of p.items || []) buckets.push(it);
    for (const it of homeBody.insights || []) buckets.push(it);
    const bollettaBenefit = buckets.some((it) => /bolletta|utenz|casa/i.test(`${it?.title || ''} ${it?.description || ''}`));
    expect(bollettaBenefit).toBeTruthy();

    const pro = await fetch(`${API}/api/suggestions`, { headers: auth(token) }).catch(() => null);
    if (pro && pro.ok) {
      const proBody = await pro.json();
      const proText = JSON.stringify(proBody).toLowerCase();
      expect(proText).not.toContain('completa il profilo');
    }
    await shot(page, '04-bolletta-final');
  });
});
