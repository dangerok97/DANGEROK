/**
 * V3.20.1 — il flusso vero, percorso dalla UI, con le prove su disco.
 *
 *     UNA COSA CHE FUNZIONA SOLO NEI TEST NON FUNZIONA.
 *
 * Le prove del backend dicono che i pezzi reggono. Questo file dice un'altra
 * cosa, e non è la stessa: che una persona seduta davanti all'app arriva
 * davvero da «chiama Lorenzo e sposta il calcetto» a una telefonata pronta,
 * passando dalle stesse schermate che vedrebbe chiunque.
 *
 * Due percorsi, perché sono due storie diverse: quella in cui il numero è
 * giusto, e quella in cui non lo è. La seconda conta quanto la prima — anzi
 * di più, perché è quella che deve finire con un telefono che non squilla.
 *
 * I dati sono finti apposta — un Lorenzo che non esiste, un numero che non
 * squilla da nessuna parte — perché un'immagine di prova finisce in un
 * rapporto, e un rapporto lo legge più di una persona.
 */
import { expect, test, type Page } from '@playwright/test';

const APP = process.env.ORA_WEB_URL || 'http://localhost:8081';
const EMAIL = 'demo.v3201@ora.app';
const PASSWORD = 'DemoV3201!';
const DOVE = 'e2e-evidence/v3201';

test.describe.configure({ mode: 'serial' });

/** Si entra, e si arriva sulla schermata. Uguale per tutti e due i percorsi. */
async function entra(page: Page, frase: string) {
  await page.setViewportSize({ width: 900, height: 1100 });
  await page.goto(APP, { waitUntil: 'domcontentloaded' });
  await page.getByText('Continua con Email').first().click();
  await page.getByPlaceholder('Email').fill(EMAIL);
  await page.getByPlaceholder('Password').fill(PASSWORD);
  await page.getByText('Accedi', { exact: true }).first().click();
  await page.waitForTimeout(6000);

  await page.goto(`${APP}/prepara-chiamata`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="prep-request"]', { timeout: 60_000 });
  await page.locator('[data-testid="prep-request"]').fill(frase);
  await page.locator('[data-testid="prep-who"]').fill('Lorenzo');
  await page.locator('[data-testid="prep-start"]').click();
  await page.waitForSelector('[data-testid="prep-contact"]', { timeout: 90_000 });
}

test('il numero è giusto: si arriva a una missione pronta', async ({ page }) => {
  test.setTimeout(240_000);
  await entra(page, 'Chiama Lorenzo e digli di spostare la partita a calcetto');

  //     1 · CHI HO TROVATO, E DA DOVE.
  // La provenienza sta accanto al numero, sempre. «Rubrica» e «Trovato sul
  // web» sono due cose molto diverse davanti alla stessa cifra.
  await expect(page.locator('[data-testid="prep-source"]')).toContainText('Rubrica');
  await expect(page.locator('[data-testid="prep-says"]')).toContainText('quello giusto');
  await expect(page.locator('[data-testid="prep-known"]')).toContainText('Calcetto');
  await page.screenshot({ path: `${DOVE}/1-contact-resolution.png`, fullPage: true });

  //     3 · IL NUMERO ACCETTATO.
  await page.locator('[data-testid="prep-confirm-yes"]').click();
  await page.waitForSelector('[data-testid="prep-confirmed"]', { timeout: 90_000 });
  await page
    .locator('[data-testid="prep-contact"]')
    .screenshot({ path: `${DOVE}/3-number-confirmed.png` });

  //     2 · LA DOMANDA, E SOLO SU QUELLO CHE MANCA.
  // Accanto alla domanda c'è quello che ORA sapeva già: è la prova che non
  // sta chiedendo una cosa che aveva sotto gli occhi.
  await page.waitForSelector('[data-testid="prep-answer"]', { timeout: 60_000 });
  await expect(page.locator('[data-testid="prep-says"]')).not.toHaveText('');
  await page
    .locator('[data-testid="prep-known"]')
    .screenshot({ path: `${DOVE}/2-missing-information.png` });
  await page.screenshot({ path: `${DOVE}/2b-missing-information-full.png`, fullPage: true });

  //     4 · PRONTA, DETTA AL FUTURO.
  await page.locator('[data-testid="prep-answer"]').fill('sabato alle 19, al massimo alle 20');
  await page.locator('[data-testid="prep-send-answer"]').click();
  await page.waitForSelector('[data-testid="prep-ready"]', { timeout: 90_000 });

  const riassunto = await page.locator('[data-testid="prep-ready"]').innerText();
  expect(riassunto).toContain('Chiamerò');
  expect(riassunto).toContain('19:00');
  //     E NIENTE DI TECNICO DAVANTI A UNA PERSONA.
  for (const tecnico of ['prep_', 'plan_', 'ced_', 'READY', 'authority', '{']) {
    expect(riassunto).not.toContain(tecnico);
  }
  await page.screenshot({ path: `${DOVE}/4-mission-ready.png`, fullPage: true });
});

test('il numero non è giusto: non si telefona a nessuno', async ({ page }) => {
  test.setTimeout(240_000);
  //     UNA FRASE DIVERSA, PERCHÉ LA STESSA RICHIESTA È LA STESSA PRATICA.
  // L'idempotenza fa il suo lavoro anche qui: ripetere la frase di prima
  // ritroverebbe la preparazione già confermata, non ne aprirebbe una nuova.
  await entra(page, 'Chiama Lorenzo per la partita a calcetto di venerdì');

  await page.locator('[data-testid="prep-confirm-no"]').click();
  await page.waitForSelector('[data-testid="prep-blocked"]', { timeout: 60_000 });

  await expect(page.locator('[data-testid="prep-status"]')).toContainText(
    'Così non posso telefonare',
  );
  //     E NON C'È NESSUN MODO DI CHIAMARE DA QUI.
  // Non un pulsante disabilitato: un pulsante che non esiste. Un cancello
  // che si vede e non si apre insegna comunque che esiste una porta.
  await expect(page.locator('[data-testid="prep-make-call"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="prep-give-number"]')).toBeVisible();
  await page.screenshot({ path: `${DOVE}/5-negative-gate.png`, fullPage: true });
});
