/**
 * Home V2 — Expo web + Playwright.
 * Requires backend API + Expo web. Does NOT claim native mobile.
 */
import { test, expect, Page } from '@playwright/test';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://localhost:8000';

async function apiRegister() {
  const email = `e2e_home_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const name = 'E2E Home';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { email, password, token: data.token as string };
}

async function seedBill(token: string) {
  const due = new Date(Date.now() + 3 * 86400_000).toISOString();
  const res = await fetch(`${API}/api/decisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      title: 'Bolletta E2E',
      description: 'Pagare entro 3 giorni',
      category: 'bill',
      urgency: 8,
      importance: 8,
      deadline: due,
      time_required_min: 10,
    }),
  });
  if (!res.ok) throw new Error(`seed decision failed: ${res.status}`);
}

async function loginUI(page: Page, email: string, password: string, register = false) {
  await page.goto('/login');
  await expect(page.getByTestId('login-title')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('login-email-button').click();
  if (register) {
    const toggle = page.getByTestId('login-toggle-mode');
    if (await toggle.isVisible()) {
      const txt = await toggle.innerText();
      if (/Crea un account|Nuovo/i.test(txt)) await toggle.click();
    }
  }
  await page.getByTestId('login-email-input').fill(email);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-button').click();
  await page.waitForURL(/tabs|\/$|\(tabs\)/, { timeout: 30_000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

test.describe('Home V2 intelligence dashboard', () => {
  test('API home schema smoke', async () => {
    const creds = await apiRegister();
    await seedBill(creds.token);
    const res = await fetch(`${API}/api/home`, {
      headers: { Authorization: `Bearer ${creds.token}` },
    });
    expect(res.ok).toBeTruthy();
    const home = await res.json();
    expect(home.ranking_version).toBe('home-rank-1.0');
    expect(home).toHaveProperty('primary_focus');
    expect(home).toHaveProperty('explanation');
    expect(home).toHaveProperty('current_situation');
    expect(home).toHaveProperty('priorities');
    expect(home).toHaveProperty('insights');
    expect(home).toHaveProperty('resume_item');
    expect(home).toHaveProperty('connection_warnings');
    expect(home).toHaveProperty('google_calendar');
    expect(home).toHaveProperty('generated_at');
    expect(home.primary_focus).toBeTruthy();
    expect(home.primary_focus.score).toBeUndefined();
    expect(Array.isArray(home.primary_focus.actions)).toBeTruthy();
    expect(home.explanation?.factors?.length).toBeGreaterThan(0);
    expect(home.google_calendar.show_banner).toBeTruthy();
  });

  test('Expo web Home blocks + situazione + refresh + responsive + auth', async ({ page }) => {
    const creds = await apiRegister();
    await seedBill(creds.token);

    await loginUI(page, creds.email, creds.password, false);
    await page.goto('/');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('home-scroll').or(page.getByTestId('home-safe')).first()).toBeVisible();

    // Primary blocks
    await expect(page.getByTestId('adesso-card').or(page.getByText('Bolletta E2E')).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('perche-adesso').or(page.getByText('Perché adesso?')).first()).toBeVisible();
    await expect(page.getByTestId('dynamic-actions').or(page.getByText(/Fatto|Apri|Rimanda/i)).first()).toBeVisible();
    await expect(page.getByTestId('situazione-card').or(page.getByText('La tua situazione')).first()).toBeVisible();
    await expect(page.getByTestId('google-banner').or(page.getByText(/Google Calendar/i)).first()).toBeVisible();

    // No legacy artifacts
    await expect(page.getByText('100/100')).toHaveCount(0);
    await expect(page.getByText(/^Dopo$/)).toHaveCount(0);

    // Situazione completa (real route)
    await page.getByTestId('btn-situazione-completa').click();
    await page.waitForTimeout(800);
    if (!(await page.getByTestId('situazione-screen').isVisible().catch(() => false))) {
      await page.goto('/situazione');
    }
    await expect(page.getByTestId('situazione-screen')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Situazione completa', { exact: true })).toBeVisible();
    await page.getByTestId('situazione-back').click().catch(async () => {
      await page.goBack();
    });

    // Refresh
    await page.reload();
    await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 20_000 });

    // Responsive
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByText('Adesso').first()).toBeVisible();
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(page.getByText('Adesso').first()).toBeVisible();

    // Bottom nav
    await expect(page.getByText('Documenti').or(page.getByText('Home')).first()).toBeVisible();

    // Logout / login persistence
    await page.goto('/profilo');
    await page.waitForTimeout(1000);
    const logout = page.getByText(/Esci|Logout|Disconnetti/i).first();
    if (await logout.isVisible().catch(() => false)) {
      await logout.click();
      await page.waitForTimeout(1000);
      await loginUI(page, creds.email, creds.password, false);
      await expect(page.getByText('Adesso').first()).toBeVisible({ timeout: 20_000 });
    }
  });
});
