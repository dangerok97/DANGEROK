import { expect, test, type Page } from '@playwright/test';
import type { HouseScan, HouseSurface } from '../src/features/houseScan/types';

// Actual exported ORA UI, synthetic geometry/account only. These tests do not
// certify native RoomPlan, LiDAR hardware, iOS signing or physical accuracy.
function surface(id: string, length: number, x: number, z: number, angle = 0): HouseSurface {
  return { id, dimensions: { x: length, y: 2.8, z: 0 }, confidence: 'high',
    transform: [Math.cos(angle), 0, Math.sin(angle), 0, 0, 1, 0, 0, -Math.sin(angle), 0, Math.cos(angle), 0, x, 0, z, 1] };
}
function scanFixture(): HouseScan {
  return {
    id: 'a'.repeat(32), title: 'Casa di prova', capture_id: 'synthetic-capture', source: 'apple_roomplan',
    captured_at: '2026-10-21T10:00:00Z', created_at: '2026-10-21T10:00:00Z', updated_at: '2026-10-21T10:00:00Z',
    revision: 1, room_count: 1, wall_count: 4, verified_wall_count: 0, room_labels: [], wall_measurements: [],
    capture: { schema_version: 1, capture_id: 'synthetic-capture', source: 'apple_roomplan', captured_at: '2026-10-21T10:00:00Z', rooms: [{
      id: 'room1', name: 'Stanza 1', walls: [surface('wall1', 4, 0, 0), surface('wall2', 3, 2, 1.5, Math.PI / 2), surface('wall3', 4, 0, 3), surface('wall4', 3, -2, 1.5, Math.PI / 2)],
      doors: [], windows: [], openings: [], floors: [], objects: [],
    }] },
  };
}

async function fixture(page: Page, options: { anonymous?: boolean; empty?: boolean; conflict?: boolean } = {}) {
  let scan = scanFixture();
  let exists = !options.empty;
  let conflict = !!options.conflict;
  let posts = 0;
  const patches: Record<string, any>[] = [];
  const user = { user_id: 'synthetic-house-owner', name: 'Persona di prova', email: 'house-qa@example.invalid',
    provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1 };
  await page.addInitScript(({ anonymous }) => {
    if (!anonymous) localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-house-session-not-a-credential'));
    (window as any).__houseCameraAttempts = 0;
    if (navigator.mediaDevices) {
      navigator.mediaDevices.getUserMedia = async () => {
        (window as any).__houseCameraAttempts += 1;
        throw new Error('Browser camera must not start in house scan UI tests');
      };
    }
  }, { anonymous: !!options.anonymous });
  await page.route(url => url.protocol.startsWith('http') && !['localhost', '127.0.0.1'].includes(url.hostname)
    && !url.pathname.startsWith('/api/'), route => route.abort());
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const headers = { 'access-control-allow-origin': request.headers().origin || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization, content-type',
      'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS', 'cache-control': 'no-store' };
    if (request.method() === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    let json: unknown = {};
    let status = 200;
    if (path.includes('providers')) json = { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
    else if (path.endsWith('/auth/me')) json = user;
    else if (path.includes('/auth/') && request.method() === 'POST') json = { token: 'synthetic-house-session-not-a-credential', user };
    else if (path.includes('life-setup')) json = { enabled: false, completed: true };
    else if (path.startsWith('/api/calendar/events/home/')) json = [];
    else if (path.includes('home')) json = { primary_focus: null, current_situation: null, priorities: [], insights: [], opportunities: [], connection_warnings: [], google_calendar: {}, weather: { available: false }, ambient: {} };
    else if (path.includes('knowledge-map')) json = { stars: [], branches: [], count: 0, known_count: 0, temporary_count: 0, percent: 0, revision: 'synthetic' };
    else if (path === '/api/house-scans' && request.method() === 'POST') {
      posts++; status = 400; json = { detail: 'Synthetic browser fixture does not capture rooms' };
    } else if (path === '/api/house-scans') {
      const { capture, room_labels, wall_measurements, ...summary } = scan;
      json = { scans: exists ? [summary] : [], has_more: false, next_offset: null };
    } else if (path === `/api/house-scans/${scan.id}`) {
      expect(request.headers().authorization).toBe('Bearer synthetic-house-session-not-a-credential');
      if (request.method() === 'PATCH') {
        const body = request.postDataJSON(); patches.push(body);
        if (conflict) { conflict = false; scan.revision++; status = 409; json = { detail: 'Revision conflict' }; }
        else {
          expect(body.revision).toBe(scan.revision);
          if (body.room_labels) scan.room_labels = body.room_labels;
          if (body.wall_measurements) {
            const item = body.wall_measurements[0];
            scan.wall_measurements = item.length_m === null ? [] : [{ ...item, verified_at: '2026-10-21T10:10:00Z', source: 'user_verified' }];
            scan.verified_wall_count = scan.wall_measurements.length;
          }
          scan.revision++; json = { scan };
        }
      } else if (request.method() === 'DELETE') {
        expect(new URL(request.url()).searchParams.get('revision')).toBe(String(scan.revision));
        exists = false; json = { deleted: true };
      } else json = { scan };
    }
    await route.fulfill({ status, headers, json });
  });
  return { scan: () => scan, posts: () => posts, patches: () => patches };
}

test('iPhone web offers an honest native handoff without starting browser capture', async ({ page }, info) => {
  const state = await fixture(page, { empty: true });
  await page.goto('/casa?scan=1');
  await expect(page.getByTestId('house-empty')).toBeVisible();
  await expect(page.getByTestId('house-ios-release-pending')).toContainText('L’installazione non è ancora disponibile');
  await expect(page.getByTestId('house-start-scan')).toHaveCount(0);
  await expect(page.getByTestId('house-install-native')).toHaveCount(0);
  await expect(page.getByTestId('house-open-native')).toHaveCount(0);
  await page.getByTestId('house-installed-confirm').click();
  await expect(page.getByTestId('house-open-native')).toBeVisible();
  expect(await page.evaluate(() => (window as any).__houseCameraAttempts)).toBe(0);
  expect(state.posts()).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await page.screenshot({ path: `mobile-qa/house-scan-entry-${info.project.name}.png`, fullPage: true, animations: 'disabled' });
});

test('saved geometry can be inspected and a verified quote preserves the original scan', async ({ page }, info) => {
  const state = await fixture(page);
  await page.goto('/casa');
  await page.getByTestId(`house-saved-${state.scan().id}`).click();
  await expect(page.getByTestId('house-floor-plan')).toBeVisible();
  await page.getByTestId('house-wall-wall1').click();
  await expect(page.getByTestId('house-wall-inspector')).toContainText('Scansione: 4,00 m');
  await page.getByTestId('house-verified-length').fill('4,03');
  await page.getByTestId('house-save-measurement').click();
  await expect(page.getByTestId('house-wall-wall1')).toContainText('4,03 m');
  await expect(page.getByTestId('house-wall-wall1')).toContainText('Verificata da te');
  await expect(page.getByTestId('house-wall-inspector')).toContainText('Scansione: 4,00 m');
  expect(state.scan().capture.rooms[0].walls[0].dimensions.x).toBe(4);
  expect(state.patches()[0]).not.toHaveProperty('capture');
  await page.getByTestId('house-room-name').fill('Soggiorno');
  await page.getByRole('button', { name: 'Rinomina', exact: true }).click();
  await expect(page.getByTestId('house-room-room1')).toContainText('Soggiorno');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(392);
  await page.getByTestId('house-floor-plan').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `mobile-qa/house-scan-plan-${info.project.name}.png`, fullPage: true, animations: 'disabled' });
  await page.reload();
  await page.getByTestId(`house-saved-${state.scan().id}`).click();
  await expect(page.getByTestId('house-room-room1')).toContainText('Soggiorno');
  await expect(page.getByTestId('house-wall-wall1')).toContainText('4,03 m');
  await page.getByRole('button', { name: 'Elimina questa pianta', exact: true }).click();
  await page.getByTestId('house-confirm-delete').click();
  await expect(page.getByTestId('house-empty')).toBeVisible();
});

test('revision conflict preserves typed quote until refreshed and explicitly retried', async ({ page }) => {
  const state = await fixture(page, { conflict: true });
  await page.goto('/casa');
  await page.getByTestId(`house-saved-${state.scan().id}`).click();
  await page.getByTestId('house-wall-wall1').click();
  await page.getByTestId('house-verified-length').fill('4,02');
  await page.getByTestId('house-save-measurement').click();
  await expect(page.getByTestId('house-error')).toContainText('aggiornata da un altro dispositivo');
  await expect(page.getByTestId('house-verified-length')).toHaveValue('4,02');
  expect(state.scan().wall_measurements).toHaveLength(0);
  await page.getByTestId('house-refresh').click();
  await expect(page.getByTestId('house-refresh')).toBeEnabled();
  await page.getByTestId('house-save-measurement').click();
  await expect(page.getByTestId('house-wall-wall1')).toContainText('4,02 m');
  expect(state.patches().map(patch => patch.revision)).toEqual([1, 2]);
});

test('sign-in preserves the bounded scan action and returns to the web handoff', async ({ page }) => {
  const state = await fixture(page, { anonymous: true, empty: true });
  await page.goto('/casa?scan=1');
  await expect(page).toHaveURL(/\/login\?next=%2Fcasa%3Fscan%3D1$/);
  await page.getByTestId('login-email-button').click();
  await page.getByTestId('login-email-input').fill('house-qa@example.invalid');
  await page.getByTestId('login-password-input').fill('SyntheticFixture123!');
  await page.getByTestId('login-submit-button').click();
  await expect(page.getByTestId('house-scan-entry')).toBeVisible();
  await expect(page).toHaveURL(/\/casa\?scan=1$/);
  expect(await page.evaluate(() => (window as any).__houseCameraAttempts)).toBe(0);
  expect(state.posts()).toBe(0);
});

test('Google browser completion preserves the local scan destination and clears one-use state', async ({ page }) => {
  const state = await fixture(page, { anonymous: true, empty: true });
  await page.addInitScript(() => {
    sessionStorage.setItem('ora:google:browser:proof', 'synthetic-browser-proof-not-a-credential');
    sessionStorage.setItem('ora:google:browser:next', '/casa?scan=1');
  });
  const completion = page.waitForRequest(request => new URL(request.url()).pathname === '/api/auth/google/browser/complete'
    && request.method() === 'POST');
  await page.goto('/google-auth-complete#ticket=synthetic-ticket');
  expect((await completion).postDataJSON()).toEqual({ ticket: 'synthetic-ticket', proof: 'synthetic-browser-proof-not-a-credential' });
  await expect(page.getByTestId('house-scan-entry')).toBeVisible();
  await expect(page).toHaveURL(/\/casa\?scan=1$/);
  expect(await page.evaluate(() => ({ proof: sessionStorage.getItem('ora:google:browser:proof'),
    next: sessionStorage.getItem('ora:google:browser:next'), cameraAttempts: (window as any).__houseCameraAttempts })))
    .toEqual({ proof: null, next: null, cameraAttempts: 0 });
  expect(state.posts()).toBe(0);
});
