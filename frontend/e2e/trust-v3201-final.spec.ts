/**
 * V3.20.1 FINAL — fiducia nei numeri e ricerca web vera, percorse dalla UI.
 *
 *     UN NUMERO NUOVO SI CONFERMA. UNO GIÀ CONFERMATO SI MOSTRA.
 *
 * Cinque schermate dall'app in esecuzione:
 *   1. numero nuovo trovato → identità, numero, provenienza, «è quello giusto?»
 *   2. numero già confermato → si riusa senza chiedere, e si può cambiare
 *   3. numero cambiato → il vecchio non si usa più, il nuovo aspetta un sì
 *   4. ricerca web vera → un'attività reale, il suo numero pubblico, la fonte
 *   5. nessun numero → nessuna telefonata possibile, e si dice perché
 *
 * Il Lorenzo della rubrica è finto, e finto è il suo numero. L'hotel no: è
 * una vera attività, e il numero che compare è quello che pubblica lei.
 * Nessuna telefonata parte da qui — non c'è un passo che la faccia partire.
 */
import { expect, test, type Page } from '@playwright/test';

const APP = process.env.ORA_WEB_URL || 'http://localhost:8081';
const DOVE = 'e2e-evidence/v3201-final';

test.describe.configure({ mode: 'serial' });

async function entra(page: Page) {
  await page.setViewportSize({ width: 900, height: 1100 });
  await page.goto(APP, { waitUntil: 'domcontentloaded' });
  await page.getByText('Continua con Email').first().click();
  await page.getByPlaceholder('Email').fill('demo.v3201@ora.app');
  await page.getByPlaceholder('Password').fill('DemoV3201!');
  await page.getByText('Accedi', { exact: true }).first().click();
  await page.waitForTimeout(6000);
}

async function prepara(page: Page, frase: string, chi: string) {
  await page.goto(`${APP}/prepara-chiamata`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="prep-request"]', { timeout: 60_000 });
  await page.locator('[data-testid="prep-request"]').fill(frase);
  await page.locator('[data-testid="prep-who"]').fill(chi);
  await page.locator('[data-testid="prep-start"]').click();
  await page.waitForSelector('[data-testid="prep-status"]', { timeout: 120_000 });
}

test('fiducia nei numeri, dalla prima volta al cambio', async ({ page }) => {
  test.setTimeout(300_000);
  await entra(page);

  //     1 · NUMERO NUOVO: SI MOSTRA E SI CHIEDE.
  await prepara(page, 'Chiama Lorenzo e digli di spostare la partita a calcetto', 'Lorenzo');
  await expect(page.locator('[data-testid="prep-source"]')).toContainText('Rubrica');
  await expect(page.locator('[data-testid="prep-says"]')).toContainText('quello giusto');
  await expect(page.locator('[data-testid="prep-confirm-yes"]')).toBeVisible();
  await page.screenshot({ path: `${DOVE}/1-new-number.png`, fullPage: true });

  // La persona dice sì: da qui in poi la coppia Lorenzo Bianchi + numero vale.
  await page.locator('[data-testid="prep-confirm-yes"]').click();
  await page.waitForSelector('[data-testid="prep-confirmed"]', { timeout: 90_000 });

  //     2 · UN'ALTRA RICHIESTA, UN ALTRO GIORNO: NON SI RICHIEDE.
  await prepara(page, 'Chiama Lorenzo per la cena di sabato', 'Lorenzo');
  await page.waitForSelector('[data-testid="prep-confirmed"]', { timeout: 90_000 });
  await expect(page.locator('[data-testid="prep-confirmed"]')).toContainText('già confermato');
  await expect(page.locator('[data-testid="prep-source"]')).toContainText('Confermato da te');
  //     NESSUNA DOMANDA SUL NUMERO…
  await expect(page.locator('[data-testid="prep-confirm-yes"]')).toHaveCount(0);
  //     …MA IL PULSANTE PER CAMBIARLO C'È.
  await expect(page.locator('[data-testid="prep-change-number"]')).toBeVisible();
  await page.screenshot({ path: `${DOVE}/2-trusted-reuse.png`, fullPage: true });

  //     3 · «USA QUESTO NUMERO INVECE».
  await page.locator('[data-testid="prep-change-number"]').click();
  await page.locator('[data-testid="prep-give-number"]').fill('+39 333 0000009');
  await page.locator('[data-testid="prep-use-number"]').click();
  await page.waitForSelector('[data-testid="prep-confirm-yes"]', { timeout: 90_000 });
  await expect(page.locator('[data-testid="prep-number"]')).toContainText('+393330000009');
  await expect(page.locator('[data-testid="prep-says"]')).toContainText('quello giusto');
  //     IL NUOVO NON SI USA ANCORA: NIENTE CHIAMATA POSSIBILE.
  await expect(page.locator('[data-testid="prep-make-call"]')).toHaveCount(0);
  await page.screenshot({ path: `${DOVE}/3-number-changed.png`, fullPage: true });
});

test('ricerca web vera: un\'attività reale e il suo numero pubblico', async ({ page }) => {
  test.setTimeout(300_000);
  await entra(page);

  //     4 · NESSUN CONTATTO LOCALE: SI VA SUL WEB, DAVVERO.
  await prepara(page, "Chiama l'Hotel Excelsior Venezia Lido", 'Hotel Excelsior Venezia Lido');
  await page.waitForSelector('[data-testid="prep-contact"]', { timeout: 120_000 });
  //     IL SITO UFFICIALE PROPOSTO PER PRIMO — E DA CONFERMARE.
  await expect(page.locator('[data-testid="prep-source"]')).toContainText('Sito ufficiale');
  await expect(page.locator('[data-testid="prep-says"]')).toContainText('quello giusto');
  await expect(page.locator('[data-testid="prep-confirm-yes"]')).toBeVisible();
  await expect(page.locator('[data-testid="prep-make-call"]')).toHaveCount(0);
  await page.screenshot({ path: `${DOVE}/4-web-reality-gate.png`, fullPage: true });
});

test('nessun numero affidabile: non si telefona', async ({ page }) => {
  test.setTimeout(300_000);
  await entra(page);

  //     5 · UNA PERSONA CHE ORA NON CONOSCE: NON SI CERCA ONLINE, SI CHIEDE.
  await prepara(page, 'Chiama Marco e digli che arrivo in ritardo', 'Marco');
  await expect(page.locator('[data-testid="prep-status"]')).toContainText(
    'Così non posso telefonare',
  );
  await expect(page.locator('[data-testid="prep-says"]')).toContainText('Me lo dici tu');
  await expect(page.locator('[data-testid="prep-contact"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="prep-make-call"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="prep-give-number"]')).toBeVisible();
  await page.screenshot({ path: `${DOVE}/5-negative-gate.png`, fullPage: true });
});
