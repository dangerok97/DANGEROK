/**
 * V3.10 Sprint 3 — la posta nei permessi, e cosa la schermata non diventa.
 *
 *   UNA CASELLA COLLEGATA NON E' UNA CASELLA DENTRO ORA.
 *
 * Il rischio di questo sprint non e' un bug: e' che una schermata di
 * permessi diventi piano piano un client di posta. Un conteggio di non
 * letti, l'oggetto dell'ultimo messaggio, un elenco — ognuna di queste cose
 * sembra utile da sola, e insieme sono una casella di posta che nessuno ha
 * chiesto e che ORA non ha alcun motivo di mostrare.
 *
 * Questi controlli guardano il sorgente, non la resa: una promessa scritta
 * nel testo e' facile da rispettare finche' qualcuno non aggiunge un
 * componente, e allora e' il sorgente a dirlo.
 *
 *   node --experimental-strip-types --test src/components/account/mail_s3.test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { MAIL_BOUNDARY } from './accountModel.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const SOURCE = readFileSync(
  path.join(ROOT, 'app/account/permessi.tsx'), 'utf-8',
);

/**
 * Il file senza i commenti.
 *
 * Un controllo che legge anche la prosa inciampa nella frase che spiega la
 * regola — «nessun conteggio di non letti» e' esattamente il testo che il
 * guardiano cerca — e la lezione, imparata piu' di una volta, e' che allora
 * si finisce per riscrivere il commento invece del codice.
 */
const PERMESSI = SOURCE
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ');

// ---------------------------------------------------------------------------
// A — la frase di confine dice le due cose che contano
// ---------------------------------------------------------------------------
{
  // Cosa ORA legge lo dice la scheda; la frase di confine non lo ripete.
  assert.ok(
    !/legge le comunicazioni collegate/i.test(MAIL_BOUNDARY),
    "la frase di confine ripete quello che la scheda dice gia'",
  );
  assert.ok(
    /ORA legge le comunicazioni collegate per capire quando qualcosa cambia o richiede attenzione\./
      .test(PERMESSI),
    "la scheda non dice piu' a cosa serve",
  );
  // E soprattutto cosa non fa. E' la meta' che toglie la paura vera, ed e'
  // anche l'unica verificabile dal codice: non esiste una capability di
  // invio cablata da nessuna parte.
  assert.ok(
    /non scrive/i.test(MAIL_BOUNDARY) && /non risponde/i.test(MAIL_BOUNDARY),
    'la frase non dice che ORA non scrive e non risponde',
  );
  assert.ok(
    /non archivia niente al posto tuo/.test(MAIL_BOUNDARY),
    "la frase non dice niente sull'archiviazione",
  );
}

// ---------------------------------------------------------------------------
// B — la schermata non e' una casella di posta
// ---------------------------------------------------------------------------
{
  for (const forbidden of [
    /non letti/i,
    /unread/i,
    /messaggi recenti/i,
    /ultimo messaggio/i,
    /oggetto:/i,
    /mittente/i,
    /inbox/i,
    /posta in arrivo/i,
  ]) {
    assert.ok(
      !forbidden.test(PERMESSI),
      `permessi.tsx mostra qualcosa da client di posta: ${forbidden}`,
    );
  }

  // La riga della casella dice tre cose: che c'e', se funziona, da quando.
  assert.ok(/perm-email/.test(PERMESSI), 'la sezione email non esiste');
  assert.ok(
    /mailboxDetail/.test(PERMESSI),
    'la riga non usa lo stato leggibile della sorgente',
  );
  assert.ok(
    /Connesso · letto/.test(PERMESSI),
    'la riga non dice da quando ORA ha letto',
  );
}

// ---------------------------------------------------------------------------
// C — compare solo se c'e' davvero una casella
// ---------------------------------------------------------------------------
{
  // Una sezione vuota che annuncia «nessuna email collegata» insegnerebbe
  // che qui si collega la posta. Non e' cosi', e la sezione e' condizionale.
  assert.ok(
    /\{mailboxes\.length \?/.test(PERMESSI),
    'la sezione email compare anche senza casella collegata',
  );
}

console.log('mail_s3: ok');
