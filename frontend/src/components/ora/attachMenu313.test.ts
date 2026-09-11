/**
 * V3.13 Sprint 2 — il menu del «+».
 *
 * Run: node --experimental-strip-types src/components/ora/attachMenu313.test.ts
 *
 *     IL «+» È UNA DOMANDA, NON UN COMANDO.
 *
 * Il comportamento vero — si apre, Esc chiude, il click fuori chiude, la voce
 * apre il selettore giusto, su un telefono non esce dallo schermo — si guarda
 * su una pagina vera, e in questo sprint è stato guardato: sette prove, due
 * viewport, due screenshot. Quello che si può perdere in silenzio, e che
 * quindi si tiene qui, sono le cose che nessuno vedrebbe sparire: una voce che
 * non porta da nessuna parte, una fotocamera che finge, il «+» che torna ad
 * aprire dritto il file picker.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

const MENU = 'src/components/ora/OraAttachMenu.tsx';
const COMPOSER = 'src/components/ora/OraComposer.tsx';
const SCREEN = 'src/components/ora/OraConversationScreen.tsx';

let checks = 0;
const ok = (cond: unknown, what: string) => {
  assert.ok(cond, what);
  checks += 1;
};

// ---------------------------------------------------------------------------
// A — Il «+» chiede, non esegue
// ---------------------------------------------------------------------------
{
  const composer = readCode(COMPOSER);
  ok(
    /onPress=\{\(\) => setMenuOpen\(/.test(composer),
    'il «+» deve aprire il menu, non chiamare direttamente chi allega',
  );
  ok(
    !/testID=\{`\$\{testID\}-attach`\}[\s\S]{0,400}onPress=\{onAttachPress\}/.test(composer),
    'il «+» è tornato ad aprire dritto il selettore di sistema',
  );
  ok(composer.includes('<OraAttachMenu'), 'il menu deve vivere accanto al suo pulsante');
  ok(
    composer.includes('expanded: menuOpen'),
    'mentre il menu è aperto il «+» deve dirlo, anche a chi non lo vede',
  );
  ok(
    /anchor: \{ position: 'relative' \}/.test(composer),
    'il menu deve essere ancorato al pulsante, non al composer',
  );
}

// ---------------------------------------------------------------------------
// B, C — Si chiude da fuori e da tastiera
// ---------------------------------------------------------------------------
{
  const menu = readCode(MENU);
  ok(menu.includes("e?.key === 'Escape'"), 'Esc deve chiudere il menu');
  ok(
    menu.includes("document.removeEventListener('keydown'"),
    "l'ascolto della tastiera deve finire quando il menu si chiude",
  );
  ok(/testID=\{`\$\{testID\}-veil`\}/.test(menu), 'un tocco fuori deve chiudere il menu');
  ok(
    /onPress=\{\(\) => \{\s*onClose\(\);\s*onChoose\(/.test(menu),
    'scegliere una voce deve chiudere il menu prima di aprire il selettore',
  );
}

// ---------------------------------------------------------------------------
// D — Ogni voce apre la cosa che dice
// ---------------------------------------------------------------------------
{
  const menu = readCode(MENU);
  const composer = readCode(COMPOSER);

  for (const [title, hint] of [
    ['Foto e file', 'Carica dal dispositivo'],
    ['Foto', 'Scegli dalla libreria'],
    ['Fotocamera', 'Scatta una foto'],
    ['Documenti', 'Aggiungi un documento'],
  ]) {
    ok(menu.includes(title) && menu.includes(hint), `manca la voce «${title}»`);
  }

  //     NIENTE FUNZIONI FINTE.
  //
  // Una voce che non porta da nessuna parte la si tocca una volta, non succede
  // niente, e da lì in poi il menu intero è sospetto. Dal composer questi
  // percorsi non esistono, quindi non si annunciano.
  for (const absent of [
    'Cerca sul web',
    'Genera immagine',
    'Deep research',
    'Gmail',
    'Calendar',
    'Connetti',
  ]) {
    ok(!menu.includes(absent), `il menu promette una cosa che non esiste: ${absent}`);
  }

  ok(
    composer.includes("if (kind === 'photo' || kind === 'camera')"),
    '«Foto» e «Fotocamera» devono chiedere immagini, non qualunque file',
  );
  ok(
    composer.includes("input.setAttribute('capture', 'environment')"),
    '«Fotocamera» deve aprire l\'obiettivo, non la stessa finestra di «Foto»',
  );
  ok(
    /Platform\.OS !== 'web'[\s\S]{0,200}return false/.test(menu),
    'la fotocamera deve comparire solo dove si apre davvero',
  );
  ok(
    /filter\(\(e\) => e\.kind !== 'camera' \|\| cameraOpens\(\)\)/.test(readCode(MENU)),
    'la voce Fotocamera deve sparire dove non è supportata, non restare inerte',
  );
  ok(
    readCode(COMPOSER).includes('input.oncancel'),
    'chiudere il selettore senza scegliere deve riportare indietro il «+»',
  );
}

// ---------------------------------------------------------------------------
// E — Su un telefono il menu resta dentro lo schermo
// ---------------------------------------------------------------------------
{
  const menu = readCode(MENU);
  ok(menu.includes("maxWidth: '92%'"), 'il menu deve restringersi su uno schermo stretto');
  /*
    Il menu si apre verso l'alto e sopra tutto il contenitore, non solo sopra
    il pulsante: misurato, ancorato al «+» copriva il campo di ventidue punti
    su telefono e su desktop. L'alzata non è fissa perché il campo cresce con
    il testo, e la calcola chi quel testo lo misura già.
  */
  ok(/bottom: lift/.test(menu), 'il menu deve aprirsi verso l\'alto');
  ok(
    /lift=\{72 \+ Math\.min\(Math\.max\(grown, 24\), 132\)\}/.test(readCode(COMPOSER)),
    "l'alzata deve seguire il campo che cresce, o il menu tornerà a coprirlo",
  );
  ok(
    !/width: \d{3,}/.test(menu.split('sheet:')[1]?.split('},')[0] ?? ''),
    'una larghezza fissa da desktop uscirebbe dal bordo di un telefono',
  );
}

// ---------------------------------------------------------------------------
// F, G — Quello che c'era prima è ancora lì
// ---------------------------------------------------------------------------
{
  const composer = readCode(COMPOSER);
  const screen = readCode(SCREEN);

  ok(composer.includes('previewUri'), 'la miniatura dell\'immagine allegata deve restare');
  ok(composer.includes('expo-document-picker'), 'su nativo deve restare il selettore di Expo');
  ok(screen.includes('api.aiCoreFileUpload'), 'il caricamento deve restare quello di prima');
  ok(
    screen.includes('onAttach(kind)'),
    'la scelta fatta nel menu deve arrivare fino al selettore',
  );

  // Microfono, Live Voice e invio non sono stati toccati.
  for (const kept of ['}-mic`', '}-voice-mode`', '}-send`']) {
    ok(composer.includes(kept), `il menu ha portato via un comando: ${kept}`);
  }

  // E il bersaglio del tocco resta quello che una mano trova.
  ok(
    readCode(MENU).includes('minHeight: tokens.touch.min'),
    'ogni voce del menu deve restare toccabile',
  );
}

// ---------------------------------------------------------------------------
// La tastiera: si apre, si raggiunge, si esce, e il focus torna dov'era
// ---------------------------------------------------------------------------
{
  const menu = readCode(MENU);
  const composer = readCode(COMPOSER);

  // Il velo raccoglie il tocco fuori e nient'altro: tabulando ci si finiva
  // dentro, e la prima cosa che una persona alla tastiera incontrava aprendo
  // il menu era un rettangolo invisibile grande quanto lo schermo.
  ok(menu.includes('focusable={false}'), 'il velo è ancora un comando');
  ok(/tabIndex: -1/.test(menu), 'il velo è ancora nel giro della tastiera su web');
  ok(
    menu.includes('accessibilityElementsHidden'),
    'un lettore di schermo annuncia ancora il velo',
  );

  // E chiudendo con Esc da una voce, quella voce sparisce: senza questo il
  // focus finisce sul corpo della pagina e si ricomincia da capo.
  ok(composer.includes('plusRef'), 'nessuno sa dove riportare il focus');
  ok(
    /plusRef\.current\?\.focus\?\.\(\)/.test(composer),
    'il focus non torna sul «+» quando il menu si chiude',
  );
  ok(
    composer.includes('onClose={closeMenu}'),
    'la chiusura non passa da chi restituisce il focus',
  );
}

console.log(`attachMenu313: ${checks}/${checks} guardie verdi`);
