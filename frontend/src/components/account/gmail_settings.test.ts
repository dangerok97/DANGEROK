/**
 * V3.10 S3 — la casella collegata si vede dove si guardano le connessioni.
 *
 *   UNA CONNESSIONE CHE NON SI VEDE DOVE SI GUARDANO LE CONNESSIONI
 *   NON E' UNA CONNESSIONE: E' UNA COSA CHE SUCCEDE ALLE TUE SPALLE.
 *
 * Il bug era esattamente quello: Permessi diceva «Connesso», la freccia
 * portava a /settings, e li' c'era solo il calendario. La persona resta con
 * due schermate che si contraddicono e nessun modo di scollegare.
 *
 * Questi controlli guardano il sorgente perche' la promessa e' strutturale:
 * la scheda deve esserci, deve chiamare gli endpoint Gmail e non quelli del
 * calendario, e non deve diventare un client di posta. Il rendering vero e'
 * negli screenshot.
 *
 *   node --experimental-strip-types --test src/components/account/gmail_settings.test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { MAIL_BOUNDARY, autoSyncLabel, connectionStateOf } from './accountModel.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const SOURCE = readFileSync(path.join(ROOT, 'app/settings.tsx'), 'utf-8');
const PERMESSI = readFileSync(path.join(ROOT, 'app/account/permessi.tsx'), 'utf-8');
const CLIENT = readFileSync(path.join(ROOT, 'src/api/client.ts'), 'utf-8');

/** Il file senza commenti: un guardiano che legge la prosa inciampa nella
 *  frase che spiega la regola. */
const code = (text: string) =>
  text.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^\s*\/\/.*$/gm, ' ');
const SETTINGS = code(SOURCE);

// ---------------------------------------------------------------------------
// A — la casella arriva in pagina
// ---------------------------------------------------------------------------
{
  assert.ok(
    /api\.gmailInstances\(\)/.test(SETTINGS),
    '/settings non chiede affatto le caselle collegate',
  );
  // Insieme alle altre letture e con lo stesso `attempt`: una casella che non
  // risponde non deve portarsi via il calendario dalla pagina.
  assert.ok(
    /attempt\(\(\) => api\.gmailInstances\(\)\)/.test(SETTINGS),
    'la lettura della casella non e\' isolata dalle altre',
  );
  assert.ok(/setMailbox/.test(SETTINGS), 'la casella non finisce nello stato');
  assert.ok(
    /name="Google Gmail"/.test(SETTINGS),
    'la scheda della casella non esiste',
  );
  assert.ok(
    /testID={mailState === 'connected' \? 'gmail-connected' : 'gmail-disconnected'}/
      .test(SETTINGS),
    'la scheda non distingue collegata da scollegata',
  );
}

// ---------------------------------------------------------------------------
// B — dice le cinque cose, e sono quelle di un calendario
// ---------------------------------------------------------------------------
{
  // Cosa e', di chi e', se funziona, da quando, cosa ci fa ORA.
  assert.ok(/account={mailbox\.display_label \|\| null}/.test(SETTINGS));
  assert.ok(/state={mailState}/.test(SETTINGS));
  // Da quanto e' aggiornata lo dice la sorgente, non l'istanza: e' l'unica
  // che sa se in questo momento ORA ci sta riuscendo.
  assert.ok(/source={sourceOf\(sources, 'email'\)}/.test(SETTINGS));
  assert.ok(/autoSyncLabel\(source\)/.test(SETTINGS));
  assert.ok(
    SETTINGS.includes(
      'ORA legge le comunicazioni collegate per capire quando qualcosa cambia o richiede attenzione.',
    ),
    'manca la frase che dice a cosa serve',
  );
  assert.ok(/MAIL_BOUNDARY/.test(SETTINGS), 'manca la frase di confine');

  // E lo stato viene dalla stessa funzione del calendario, non da una regola
  // scritta a parte per la posta.
  assert.equal(connectionStateOf({ status: 'connected' }), 'connected');
  assert.equal(connectionStateOf({ status: 'revoked' }), 'disconnected');
  assert.equal(connectionStateOf(null), 'absent');
  // Le tre frasi, e nessuna di esse chiede di premere qualcosa.
  const fresh = new Date(Date.now() - 6 * 60_000).toISOString();
  assert.equal(
    autoSyncLabel({ state: 'Connesso', last_read_at: fresh }),
    'Aggiornato automaticamente \u00b7 6 minuti fa',
  );
  assert.equal(
    autoSyncLabel({ state: 'Collegato, ma quello che so \u00e8 vecchio', last_read_at: null }),
    'Connesso \u00b7 ultimo aggiornamento molto tempo fa',
  );
  assert.equal(
    autoSyncLabel({ state: 'Non riesco a leggerlo in questo momento' }),
    'Connesso \u00b7 non riesco ad aggiornarlo in questo momento',
  );
  // Collegato non vuol dire aggiornato, e la frase non li confonde mai.
  assert.ok(!/^Connesso$/.test(autoSyncLabel({ state: 'Connesso' })));
}

// ---------------------------------------------------------------------------
// C — i due bottoni, sugli endpoint della posta
// ---------------------------------------------------------------------------
{
  // Un solo pulsante: scollegare. Sincronizzare non e' una cosa che si
  // chiede a una persona di fare.
  assert.ok(/testID="btn-gmail-revoke"/.test(SETTINGS), 'manca Scollega');
  assert.ok(/api\.gmailRevoke\(mailbox\.id\)/.test(SETTINGS));
  assert.ok(!/testID="btn-gmail-sync"/.test(SETTINGS), 'il pulsante Sincronizza e\u2019 tornato');
  assert.ok(!/api\.gmailSync\(/.test(SETTINGS), 'la schermata sincronizza a mano');

  // Scollegare chiede conferma, come per il calendario, e dice cosa NON
  // succede: staccare una casella non cancella quello che ORA ha capito.
  assert.ok(/testID="confirm-gmail-revoke"/.test(SETTINGS));
  assert.ok(
    /Quello che ha già capito resta/.test(SOURCE),
    'la conferma non dice che le osservazioni restano',
  );

  // E dopo la revoca la pagina si rilegge dal server invece di spegnere la
  // scheda a mano.
  const revoke = SETTINGS.slice(SETTINGS.indexOf('const onMailRevoke'));
  const body = revoke.slice(0, revoke.indexOf('const onAppleDisconnect'));
  assert.ok(/await load\(\)/.test(body), 'dopo la revoca la UI non si aggiorna');

  // Gli endpoint esistono nel client e sono quelli del connettore Gmail.
  for (const method of ['gmailInstances', 'gmailSync', 'gmailRevoke']) {
    assert.ok(new RegExp(`${method}:`).test(CLIENT), `manca api.${method}`);
  }
  assert.ok(/\/connectors\/gmail\/instances\/\$\{instanceId\}\/sync/.test(CLIENT));
  assert.ok(/\/connectors\/gmail\/instances\/\$\{instanceId\}\/revoke/.test(CLIENT));
}

// ---------------------------------------------------------------------------
// D — il calendario e' rimasto dov'era
// ---------------------------------------------------------------------------
{
  for (const kept of [
    /name="Google Calendar"/,
    /testID="btn-revoke"/,
    /testID="btn-settings-manage"/,
    /api\.googleCalendarRevoke\(instance\.id\)/,
    /CALENDAR_WRITE_BOUNDARY/,
  ]) {
    assert.ok(kept.test(SETTINGS), `il calendario ha perso qualcosa: ${kept}`);
  }
  // E ha perso il pulsante, come Gmail.
  assert.ok(!/testID="btn-settings-sync"/.test(SETTINGS));
  assert.ok(!/api\.googleCalendarSync\(/.test(SETTINGS));
  // «Sincronizza» non compare piu' da nessuna parte, nemmeno per Apple: in
  // una pagina dove tutto si aggiorna da solo quella parola direbbe il
  // contrario di quello che succede.
  assert.ok(!/Sincronizza/.test(SETTINGS), 'la parola Sincronizza e\u2019 ancora in pagina');
  // E i bottoni della posta non chiamano per sbaglio quelli del calendario.
  const mailCard = SETTINGS.slice(
    SETTINGS.indexOf('name="Google Gmail"'),
    SETTINGS.indexOf('appleVisible ?'),
  );
  assert.ok(mailCard.length > 100, 'la scheda della posta non e\' stata trovata');
  assert.ok(
    !/googleCalendar/.test(mailCard),
    'un bottone della posta chiama il calendario',
  );
}

// ---------------------------------------------------------------------------
// E — la freccia dei permessi porta qui, e qui non c'e' una casella di posta
// ---------------------------------------------------------------------------
{
  const permessi = code(PERMESSI);
  const card = permessi.slice(
    permessi.indexOf('testID="perm-email"'),
    permessi.indexOf('MAIL_BOUNDARY}</BoundaryNote>'),
  );
  assert.ok(card.length > 100, "la scheda Email dei permessi non e' stata trovata");
  assert.ok(
    card.includes("router.push('/settings'"),
    "la riga della posta non porta piu' alle connessioni",
  );

  for (const forbidden of [
    /non letti/i, /unread/i, /inbox/i, /posta in arrivo/i,
    /oggetto:/i, /mittente/i, /anteprima/i, /messaggi recenti/i,
  ]) {
    assert.ok(
      !forbidden.test(SETTINGS),
      `/settings mostra qualcosa da client di posta: ${forbidden}`,
    );
  }
  // Nessun campo tecnico sulla scheda: niente cursori, id, scope, token.
  for (const technical of [
    /mailbox\.cursor/, /history_id/, /authorized_scopes/, /secret_reference/,
    /mailbox\.id}<\//,
  ]) {
    assert.ok(!technical.test(SETTINGS), `la scheda mostra un dettaglio tecnico: ${technical}`);
  }
  assert.ok(/non scrive/i.test(MAIL_BOUNDARY) && /non risponde/i.test(MAIL_BOUNDARY));
}

console.log('gmail_settings: ok');
