import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

// Synthetic EAN image; contains NO user card or account data.
const png = 'iVBORw0KGgoAAAANSUhEUgAAAXMAAABmAQAAAAARrUyjAAAAZklEQVR4nO3YsQmAMBCF4UtIYecEAddI50wuIN4EjpU1hFtAuytEZ0gTBP9Xf8Wr//BIy47YxEXw+O972z0vki6f1EXrPRbb5hzdziGpm9Swlp5/8Hg8Ho/H4/F4PL6/D/QB/I/9C7zRFh7wf8N1AAAAAElFTkSuQmCC';
const image = 'data:image/png;base64,' + png;
const ean = { format: 'EAN_13', code: '0042100005264', image };
const upc = { format: 'UPC_A', code: '042100005264', image };

type Read = { candidates?: typeof ean[]; fail?: boolean };
async function fixture(page: Page, reads: Read[]) {
  const saves: any[] = []; let scans = 0;
  await page.addInitScript(() => localStorage.setItem('ora_auth_token', JSON.stringify('synthetic-import-session')));
  await page.route('**/api/**', async route => {
    const req = route.request(); const path = new URL(req.url()).pathname;
    const headers = { 'access-control-allow-origin': req.headers().origin || 'http://127.0.0.1:8093',
      'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization,content-type',
      'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS' };
    if (req.method() === 'OPTIONS') { await route.fulfill({ status: 204, headers }); return; }
    let json: unknown = {};
    if (path.endsWith('/auth/me')) json = { user_id: 'import-test-owner', name: 'Persona di prova', email: 'import@example.invalid', provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1 };
    else if (path.includes('life-setup')) json = { enabled: false, completed: true };
    else if (path.endsWith('/wallet/decode')) {
      expect(req.headers()['content-type']).toBe('image/png');
      const response = reads[Math.min(scans++, reads.length - 1)];
      if (response.fail) { await route.fulfill({ status: 422, headers, json: { detail: 'Foto non leggibile: prova uno screenshot.' } }); return; }
      json = { candidates: response.candidates, saved: false };
    } else if (path.endsWith('/wallet/cards') && req.method() === 'PUT') {
      const input = req.postDataJSON(); saves.push(input);
      json = { card: { ...input, image, revision: 1, acceptance: 'not_verified_at_checkout', created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z' } };
    } else if (path.endsWith('/wallet/cards')) json = { cards: [] };
    await route.fulfill({ status: 200, headers, json });
  });
  await page.route(url => url.protocol.startsWith('http') && !['localhost', '127.0.0.1'].includes(url.hostname) && !url.pathname.startsWith('/api/'), route => route.abort());
  return { saves };
}
async function upload(page: Page) {
  const chooser = page.waitForEvent('filechooser'); await page.getByTestId('wallet-import').click();
  await (await chooser).setFiles({ name: 'synthetic-tessera.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
}
async function openEditor(page: Page) {
  await page.setViewportSize({ width: 390, height: 740 }); await page.goto('/portafoglio');
  await page.getByTestId('wallet-add').click();
}

for (const name of ['', 'Nome scelto prima della foto']) test(`photo auto-import fills barcode+number without technical fields; name=${name || 'optional'}`, async ({ page }, info) => {
  const { saves } = await fixture(page, [{ candidates: [upc, ean] }]); await openEditor(page);
  if (name) await page.getByTestId('wallet-name').fill(name);
  await upload(page); await expect(page.getByTestId('wallet-import-ready')).toBeVisible();
  await expect(page.getByTestId('wallet-read-code')).toHaveText(ean.code);
  await expect(page.getByTestId('wallet-code')).toHaveCount(0); await expect(page.getByRole('radio')).toHaveCount(0);
  await expect(page.getByRole('switch')).toHaveCount(0); await expect(page.getByTestId('wallet-scan-choices')).toHaveCount(0);
  await expect(page.getByTestId('wallet-name')).toHaveValue(name);
  const preview = page.locator('img[alt="Anteprima codice letto"]');
  await expect.poll(() => preview.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
  await expect(page.getByTestId('wallet-save')).toBeEnabled();
  await page.getByTestId('wallet-save').scrollIntoViewIfNeeded();
  // The floating bottom navigation must not cover the save button.
  expect(await page.getByTestId('wallet-save').evaluate(el => {
    const r = el.getBoundingClientRect(); const target = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return !!target && (target === el || el.contains(target));
  })).toBe(true);
  fs.mkdirSync('mobile-qa', { recursive: true });
  if (!name) await page.screenshot({ path: `mobile-qa/wallet-auto-import-${info.project.name}.png`, animations: 'disabled' });
  await page.getByTestId('wallet-save').click(); await expect(page.getByTestId('wallet-card-detail')).toBeVisible();
  expect(saves).toHaveLength(1); expect(saves[0]).toMatchObject({ format: 'EAN_13', code: ean.code, source: 'image', static_confirmed: true, name: name || 'Tessera fedeltà' });
});

test('only genuinely different codes require choosing a preview; no manual fields', async ({ page }) => {
  const second = { ...ean, code: '5901234123457' };
  const { saves } = await fixture(page, [{ candidates: [ean, upc, second] }]); await openEditor(page); await upload(page);
  await expect(page.getByTestId('wallet-scan-choices')).toBeVisible();
  await expect(page.locator('[data-testid^="wallet-candidate-"]')).toHaveCount(2);
  await expect(page.getByTestId('wallet-save')).toBeDisabled();
  await page.getByTestId('wallet-candidate-1').click(); await expect(page.getByTestId('wallet-read-code')).toHaveText(second.code);
  await expect(page.getByRole('radio')).toHaveCount(0); await page.getByTestId('wallet-save').click();
  await expect(page.getByTestId('wallet-card-detail')).toBeVisible(); expect(saves[0].code).toBe(second.code);
});

test('failed replacement photo clears old code and prevents stale save', async ({ page }) => {
  const { saves } = await fixture(page, [{ candidates: [ean, upc] }, { fail: true }]);
  await openEditor(page); await upload(page); await expect(page.getByTestId('wallet-import-ready')).toBeVisible();
  await upload(page); await expect(page.getByTestId('wallet-import-error')).toContainText('Foto non leggibile');
  await expect(page.getByTestId('wallet-read-code')).toHaveCount(0); await expect(page.getByTestId('wallet-save')).toBeDisabled();
  expect(saves).toHaveLength(0);
});

test('single QR payload is imported without choosing a symbology', async ({ page }) => {
  const qr = { ...ean, format: 'QR_CODE', code: 'SYNTHETIC-LOYALTY-0001' };
  const { saves } = await fixture(page, [{ candidates: [qr] }]); await openEditor(page); await upload(page);
  await expect(page.getByTestId('wallet-read-code')).toHaveText(qr.code); await expect(page.getByRole('radio')).toHaveCount(0);
  await page.getByTestId('wallet-save').click(); await expect(page.getByTestId('wallet-card-detail')).toBeVisible();
  expect(saves[0]).toMatchObject({ code: qr.code, format: 'QR_CODE' });
});
