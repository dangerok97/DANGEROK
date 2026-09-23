/**
 * V3.21.3d — la testata c'è, e i numeri vengono da una parte sola.
 *
 *     UNA FOTO CHE NON C'È È UN PLACEHOLDER CON UN NOME PIÙ BELLO.
 *
 * La reference mette in alto a destra una natura morta — pianta, libri,
 * portapenne, lampada — e la frase scritta a mano accanto. La frase deve
 * restare interfaccia: dentro l'immagine non si correggerebbe più.
 *
 * E la percentuale del profilo deve arrivare dal backend, sempre: due conti
 * fatti in due posti diversi finiscono per dire due numeri diversi, e a quel
 * punto non si crede più a nessuno dei due.
 *
 *     node --experimental-strip-types src/shell/vita3213d.test.ts
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync, statSync } from 'node:fs';
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

// ---------------------------------------------------------------------------
// A — la scena editoriale esiste, è locale, ed è un'immagine vera
// ---------------------------------------------------------------------------
{
  const asset = resolve(FRONTEND, 'assets/images/vita-header.png');
  assert.ok(existsSync(asset), 'manca l\'immagine della testata di Vita');
  // Un file da pochi byte sarebbe un placeholder con un altro nome.
  assert.ok(statSync(asset).size > 20_000, 'la testata deve essere un\'immagine vera');
  assert.ok(
    existsSync(resolve(FRONTEND, 'scripts/make-vita-header.py')),
    'un asset di cui nessuno sa come è nato è un asset che nessuno può correggere',
  );

  const schermo = leggi(SCHERMO);
  assert.ok(
    schermo.includes("require('@/assets/images/vita-header.png')"),
    'la testata usa l\'asset versionato',
  );
  assert.ok(
    schermo.includes("from 'expo-image'") &&
      schermo.includes('styles.introArtwork') &&
      schermo.includes('styles.introCopyMobile'),
    'la testata deve preservare la scena su desktop e dare piena larghezza al testo su mobile',
  );
  assert.ok(!/source=\{\{\s*uri:/.test(schermo), 'nessun URL remoto nella schermata');
  // La frase resta interfaccia: si corregge senza rifare un'immagine.
  assert.ok(
    schermo.includes('Un quadro più completo'),
    'la frase manoscritta deve stare nell\'interfaccia, non dentro il file',
  );
}

// ---------------------------------------------------------------------------
// B — la percentuale viene dal backend, e non si ricalcola qui
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(
    /const percent = [^\n]*state\?\.percent/.test(schermo),
    'la percentuale del profilo è quella che manda il backend',
  );
  // Nessun conto sulle percentuali dentro la schermata: niente medie, niente
  // somme, niente «known/applicable * 100».
  assert.ok(
    !/percent\s*[*/+-]\s*(?!\}|\s*['"`])/.test(schermo.replace(/percent \* 100/g, '')),
    'la schermata non deve fare aritmetica sulle percentuali',
  );
  assert.ok(
    !/known_count\s*\/\s*applicable_count/.test(schermo),
    'la completezza di un\'area non si ricalcola nel client',
  );
}

// ---------------------------------------------------------------------------
// C — i fatti mostrati arrivano già detti in italiano dal backend
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(
    schermo.includes('current.known') && schermo.includes('k.value'),
    'i fatti si leggono da `known`, che il backend manda già in italiano',
  );
  // Nessuna traduzione sparsa nel componente: le parole stanno in `human.py`.
  assert.ok(
    !/['"]true['"]\s*[:?]|['"]unknown['"]/.test(schermo),
    'niente traduzioni di valori grezzi dentro la schermata',
  );
  assert.ok(
    schermo.includes('source_ref'),
    'modificare un fatto deve riscrivere dov\'è scritto, non creare una copia',
  );
}

// ---------------------------------------------------------------------------
// D — quello che il V3.21.3c ha sistemato non è regredito
// ---------------------------------------------------------------------------
{
  const voci = leggi('src/shell/navItems.ts');
  const schermo = leggi(SCHERMO);

  assert.ok(voci.includes("href: '/vita'"), 'Vita deve ancora aprire /vita');
  assert.ok(existsSync(resolve(FRONTEND, 'app/vita.tsx')), 'manca la pagina /vita');
  assert.ok(schermo.includes('Continua con {current.title}'), '«Continua con X» resta');
  assert.ok(schermo.includes('Lo faccio più tardi'), '«Lo faccio più tardi» resta');
  assert.ok(!schermo.includes('Entra in ORA'), '«Entra in ORA» non deve tornare');
  assert.ok(schermo.includes('useLocalSearchParams'), 'il resume per area resta');
  assert.ok(
    schermo.includes('goNextArea(current.area_id, o.ref)'),
    'le voci di «cosa manca» restano apribili',
  );
}

console.log('V3.21.3d Vita guards: tutte le asserzioni passate');
