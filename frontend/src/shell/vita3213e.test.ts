/**
 * V3.21.3e — la selezione non riscrive quello che ORA sa.
 *
 *     UN CLIC NON È UN'INFORMAZIONE SULLA TUA VITA.
 *
 * Due bug visti in app su V3.21.3d, e tutti e due nascevano qui dentro:
 * `stateLabel` cominciava con `if (area.current) return 'In corso'`, così
 * Famiglia al 100% appena cliccata si dichiarava in corso; e la «prossima
 * area» era `areas.find(a => a.percent < 100)`, cioè l'ordine del menu, con
 * accanto una frase che nessuno aveva verificato.
 *
 * Queste asserzioni non guardano l'estetica: guardano che le tre cose —
 * selezionata, in corso, completa — restino separate nel codice, perché è lì
 * che si erano confuse.
 *
 *     node --experimental-strip-types src/shell/vita3213e.test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const leggi = (rel: string) =>
  readFileSync(resolve(FRONTEND, rel), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

const SCHERMO = 'src/life-setup/GuidedSetupScreen.tsx';
const schermo = leggi(SCHERMO);

/** Il corpo di una funzione, per guardarci dentro invece che intorno. */
function corpoDi(sorgente: string, firma: string): string {
  const da = sorgente.indexOf(firma);
  assert.ok(da >= 0, `non trovo ${firma}`);
  // Il corpo comincia dopo la parentesi che chiude i parametri: la firma ne
  // contiene già una graffa sua, quella del tipo dell'argomento.
  let tonde = 0;
  let inizio = -1;
  for (let i = da; i < sorgente.length; i += 1) {
    if (sorgente[i] === '(') tonde += 1;
    if (sorgente[i] === ')') {
      tonde -= 1;
      if (tonde === 0) {
        inizio = sorgente.indexOf('{', i);
        break;
      }
    }
  }
  assert.ok(inizio > 0, `non trovo il corpo di ${firma}`);
  let profondita = 0;
  for (let i = inizio; i < sorgente.length; i += 1) {
    if (sorgente[i] === '{') profondita += 1;
    if (sorgente[i] === '}') {
      profondita -= 1;
      if (profondita === 0) return sorgente.slice(da, i + 1);
    }
  }
  throw new Error(`${firma} non si chiude`);
}

/** Dove comincia un blocco, riconosciuto dal suo testID. */
const dove = (testID: string) => schermo.indexOf(`testID="${testID}"`);

// ---------------------------------------------------------------------------
// A — selezionata non vuol dire «in corso»
// ---------------------------------------------------------------------------
{
  const label = corpoDi(schermo, 'function stateLabel(');

  assert.ok(
    !/\barea\.(current|selected)\b/.test(label),
    'lo stato di un\'area non può dipendere da dove stai guardando',
  );
  assert.ok(
    label.includes('area.percent >= 100') && label.includes("return 'Conosciuta'"),
    'al 100% un\'area è conosciuta, anche mentre è aperta',
  );
  assert.ok(
    /if \(area\.in_progress\) return 'In corso'/.test(label),
    '«In corso» lo dice il backend, e solo con una domanda aperta',
  );

  // E «In corso» non è scritto da nessun'altra parte: il chip sotto il titolo
  // lo era, e smentiva l'area che stava descrivendo.
  const quante = schermo.split("'In corso'").length - 1;
  assert.equal(quante, 1, '«In corso» deve uscire da stateLabel e basta');
  assert.ok(
    schermo.includes('{stateLabel(current)}'),
    'il chip del pannello mostra lo stato vero dell\'area',
  );
  assert.ok(schermo.includes('{stateLabel(a)}'), 'la colonna di destra pure');
}

// ---------------------------------------------------------------------------
// B — la selezione resta evidenza visiva, e solo quella
// ---------------------------------------------------------------------------
{
  // La riga della colonna di destra usa `selected` per bordo, sfondo e icona.
  assert.ok(
    schermo.includes('a.selected ? colors.accent : colors.divider')
      && schermo.includes('a.selected && { backgroundColor: colors.accentMuted }'),
    'la selezione si vede dal bordo e dallo sfondo',
  );
  assert.ok(
    !/selected \? .*state_label|selected \? '[^']*In corso/.test(schermo),
    'la selezione non deve scegliere un\'etichetta di stato',
  );
  assert.ok(schermo.includes('guided-rail-'), 'la colonna di destra esiste');
}

// ---------------------------------------------------------------------------
// C — a un'area completa non si chiede di continuare, né di rimandare
// ---------------------------------------------------------------------------
{
  const passo = dove('guided-next-step');
  const completa = dove('guided-area-complete');
  const prossima = dove('guided-next-area');

  assert.ok(passo > 0 && completa > passo, 'i due rami esistono, in quest\'ordine');
  assert.ok(
    schermo.includes("current.open_objectives?.length ? ("),
    'il ramo si sceglie da quello che manca davvero, non da un flag di UI',
  );

  const ramoCompleto = schermo.slice(completa, prossima > 0 ? prossima : schermo.length);
  assert.ok(
    ramoCompleto.includes('Di {current.title} so già tutto quello che mi serve.'),
    'un\'area finita si dichiara finita',
  );
  assert.ok(!ramoCompleto.includes('Continua con'), 'niente «Continua con» su un\'area completa');
  // E il terzo stato, che è diverso dai primi due: non piena, ma senza più
  // niente da chiedere perché quello che manca è stato rifiutato. Dire «so già
  // tutto» sarebbe falso; richiedere sarebbe non aver ascoltato.
  assert.ok(
    schermo.includes('current.percent >= 100 ? ('),
    'completa non è la stessa cosa di «non ho altro da chiederti»',
  );
  assert.ok(
    ramoCompleto.includes('guided-area-nothing-to-ask')
      && ramoCompleto.includes('Di {current.title} non ho altro da chiederti.'),
    'un\'area con solo buchi rifiutati lo dice, e non si spaccia per completa',
  );
  assert.ok(
    !ramoCompleto.includes('Lo faccio più tardi'),
    'non si rimanda il niente',
  );

  // Le due CTA esistono una volta sola, e stanno nel ramo incompleto.
  for (const cta of ['guided-later', 'guided-continue-area']) {
    assert.equal(
      schermo.split(`testID="${cta}"`).length - 1, 1,
      `${cta} deve esistere in un posto solo`,
    );
    assert.ok(dove(cta) > passo && dove(cta) < completa, `${cta} vale solo se manca qualcosa`);
  }
}

// ---------------------------------------------------------------------------
// C2 — una domanda già scritta non si infila dentro un'altra frase
// ---------------------------------------------------------------------------
{
  // Quasi tutte le etichette del catalogo sono domande. «Aggiungi ${label
  // minuscolo} per ricevere promemoria» produceva «Aggiungi vuoi aggiungere il
  // libretto? per ricevere promemoria»: una frase che nessuno ha mai detto.
  assert.ok(
    !/Aggiungi \$\{[^}]*label\.toLowerCase\(\)\} per ricevere/.test(schermo),
    "una domanda non diventa il complemento oggetto di un'altra frase",
  );
  assert.ok(
    schermo.includes("label.trim().endsWith('?')"),
    "una domanda già scritta si legge com'è",
  );
}

// ---------------------------------------------------------------------------
// D — il riepilogo globale sta in un posto solo
// ---------------------------------------------------------------------------
{
  assert.ok(
    !schermo.includes('ORA ha un buon punto di partenza'),
    'la percentuale complessiva è già in «Profilo Vita»: qui era una seconda copia',
  );
  assert.ok(!schermo.includes('guided-done'), 'il blocco duplicato non deve tornare');

  // Il riepilogo complessivo vive in «Profilo Vita», sopra il pannello. Dentro
  // il pannello di un'area non se ne parla più: era la stessa frase e lo
  // stesso numero, a due centimetri di distanza.
  const profilo = dove('guided-profile');
  const pannello = dove('guided-card');
  assert.ok(profilo > 0 && pannello > profilo, '«Profilo Vita» sta sopra il pannello');

  const dentroIlPannello = schermo.slice(pannello);
  for (const copia of ['Conosce il {percent}%', '{percent}%', 'di ciò che può aiutarti']) {
    assert.ok(
      !dentroIlPannello.includes(copia),
      `«${copia}» è già scritto in «Profilo Vita»: qui era una seconda copia`,
    );
  }
}

// ---------------------------------------------------------------------------
// E — la prossima area la decide il backend, e porta con sé il motivo
// ---------------------------------------------------------------------------
{
  assert.ok(
    schermo.includes('const consiglio = state?.recommended'),
    'la graduatoria sta nel backend, non qui',
  );
  assert.ok(
    !/areas\.find\(\([^)]*\) => [^)]*percent < 100/.test(schermo),
    'la prima della lista non è un consiglio',
  );
  assert.ok(
    schermo.includes('{consiglio.reason}'),
    'quello che si legge è la frase che il backend può giustificare',
  );
  assert.ok(
    schermo.includes('!current.open_objectives?.length && consiglio'),
    'si propone un\'altra area solo quando qui non manca più niente',
  );
  assert.ok(
    schermo.includes('Prossima area consigliata'),
    'il consiglio è staccato, e si dichiara per quello che è',
  );
  assert.ok(
    /prossimaArea: \{[\s\S]{0,160}borderTopWidth/.test(readFileSync(resolve(FRONTEND, SCHERMO), 'utf8')),
    'staccato anche a vedersi: una riga sopra e un po\' d\'aria',
  );
}

// ---------------------------------------------------------------------------
// F — i tipi tengono le tre cose separate
// ---------------------------------------------------------------------------
{
  const client = leggi('src/api/client.ts');
  assert.ok(client.includes('export type GuidedSetupArea'), 'un tipo per l\'area del percorso');
  assert.ok(client.includes('selected?: boolean'), '`selected` è dove sei');
  assert.ok(client.includes('in_progress?: boolean'), '`in_progress` è dove c\'è una domanda');
  assert.ok(client.includes('reason_code: string'), 'il motivo è verificabile');
  assert.ok(client.includes('recommended?: NextAreaAdvice | null'), 'il consiglio arriva dal backend');
}

// ---------------------------------------------------------------------------
// G — quello che i giri precedenti hanno sistemato non è regredito
// ---------------------------------------------------------------------------
{
  assert.ok(schermo.includes('Continua con {current.title}'), '«Continua con X» resta dov\'è utile');
  assert.ok(schermo.includes('Lo faccio più tardi'), '«Lo faccio più tardi» resta dov\'è utile');
  assert.ok(!schermo.includes('Entra in ORA'), '«Entra in ORA» non deve tornare');
  assert.ok(
    schermo.includes('goNextArea(current.area_id, o.ref)'),
    'le voci di «cosa manca» restano apribili',
  );
  assert.ok(
    schermo.includes("require('@/assets/images/vita-header.png')"),
    'la testata editoriale resta',
  );
}

console.log('V3.21.3e Vita state guards: tutte le asserzioni passate');
