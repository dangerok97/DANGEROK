/**
 * V3.21.3b — ogni link della Home ha la sua pagina.
 *
 *     CINQUE BOTTONI DIVERSI PORTAVANO TUTTI A «SITUAZIONE COMPLETA».
 *
 * «Vedi agenda» chiede *quando*, «Vedi tutto» chiede *come sta andando*, «N da
 * rispondere» chiede *che cosa vuoi da me*, «N aggiornamenti» chiede *che cosa
 * è successo*, «Apri dettagli» chiede *questo, nel dettaglio*. Sono cinque
 * domande, e finivano su una risposta sola.
 *
 * Queste guardie tengono ferme le destinazioni e la loro distinzione, più le
 * due cose che nella Home non devono tornare: il bottone «Perché ora?»
 * nell'intestazione, e le forme astratte al posto dell'immagine nella barra.
 *
 *     node --experimental-strip-types src/shell/navigazione3213b.test.ts
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

const HOME = 'app/(tabs)/index.tsx';

// ---------------------------------------------------------------------------
// A — cinque destinazioni, tutte diverse
// ---------------------------------------------------------------------------
{
  const home = leggi(HOME);

  const destinazioni = [
    ["onSeeAgenda={() => router.push('/agenda')}", '/agenda'],
    ["onSeeSummary={() => router.push('/ora-sintesi')}", '/ora-sintesi'],
    ["onSeeAll={() => router.push('/domande')}", '/domande'],
    ["onSeeAll={() => router.push('/aggiornamenti')}", '/aggiornamenti'],
    ['onOpenWork={(id) => router.push(`/aggiornamento/', '/aggiornamento/:id'],
    ["onOpenWeather={() => router.push('/meteo')}", '/meteo'],
  ] as const;

  for (const [frammento, dove] of destinazioni) {
    assert.ok(home.includes(frammento), `la Home deve portare a ${dove}`);
  }

  const distinte = new Set(destinazioni.map(([, dove]) => dove));
  assert.equal(distinte.size, destinazioni.length, 'due link non possono avere la stessa pagina');

  // E nessuno dei cinque può tornare a finire nel cestino generico.
  for (const [frammento] of destinazioni) {
    assert.ok(
      !frammento.includes('/situazione'),
      '«Situazione completa» non è la destinazione di nessuno di questi link',
    );
  }
}

// ---------------------------------------------------------------------------
// B — ogni pagina esiste davvero, con la rotta che il link nomina
// ---------------------------------------------------------------------------
{
  for (const file of [
    'app/agenda.tsx',
    'app/ora-sintesi.tsx',
    'app/domande.tsx',
    'app/aggiornamenti.tsx',
    'app/aggiornamento/[id].tsx',
    'app/meteo.tsx',
  ]) {
    assert.ok(existsSync(resolve(FRONTEND, file)), `manca la pagina ${file}`);
  }
}

// ---------------------------------------------------------------------------
// C — il meteo in alto a destra, e «Perché ora?» solo nel focus
// ---------------------------------------------------------------------------
{
  const home = leggi(HOME);
  const chrome = leggi('src/components/home/v3/HomeChrome.tsx');
  const hero = leggi('src/components/home/v3/HeroAdesso.tsx');

  assert.ok(
    home.includes('weather={home?.weather || null}'),
    'la Home deve passare il meteo alla sua intestazione',
  );
  assert.ok(
    !chrome.includes('Perché ora?'),
    'l\'intestazione non deve più avere il bottone «Perché ora?»',
  );
  assert.ok(
    hero.includes('Perché ora?'),
    '«Perché ora?» resta dentro la card del focus, dov\'è la cosa che spiega',
  );
  assert.ok(
    chrome.includes('Meteo non disponibile'),
    'col meteo spento lo si dice, invece di inventare un grado',
  );
  assert.ok(
    chrome.includes('temperature_c') && chrome.includes('c.place'),
    'il modulo mostra temperatura e località, come nella reference',
  );
  assert.ok(
    chrome.includes('accessibilityRole="button"') && chrome.includes('onOpen'),
    'il meteo si apre: non è un\'etichetta',
  );
  // Nessun grado scritto a mano: il numero arriva sempre dal backend.
  assert.ok(
    !/\b\d{1,2}°C\b/.test(chrome.replace(/\$\{[^}]*\}°C/g, '')),
    'niente meteo scritto a mano nel componente',
  );

  // L'intestazione vive dentro la colonna centrale, non sopra tutta la pagina:
  // è lì che la reference mette il meteo, accanto al saluto.
  const testa = home.indexOf('<HomeHeaderV3');
  const colonne = home.indexOf('{twoColumn ?');
  assert.ok(testa > 0 && colonne > 0 && testa < colonne, 'l\'intestazione sta nella colonna centrale');
}

// ---------------------------------------------------------------------------
// D — la barra condivisa mostra un'immagine vera, non forme astratte
// ---------------------------------------------------------------------------
{
  const rail = leggi('src/shell/SideRail.tsx');

  assert.ok(
    rail.includes("overflow: 'hidden'") && !rail.includes("overflow: 'scroll'"),
    'la barra ci sta tutta: niente scorrimento',
  );
  assert.ok(
    rail.includes("objectFit: 'cover'") && rail.includes('StyleSheet.absoluteFill'),
    "l'immagine riempie la card e il testo le sta sopra, come nella reference",
  );
  assert.ok(
    rail.includes("require('@/assets/images/rail-calm.png')"),
    'la card della barra deve mostrare l\'asset versionato, non un URL remoto',
  );
  assert.ok(
    !/styles\.hill\b|hillBack|hillFront/.test(rail),
    'le colline finte non devono tornare al posto dell\'immagine',
  );
  assert.ok(
    !/source=\{\{\s*uri:/.test(rail),
    'nessun URL remoto per l\'immagine della barra',
  );

  const asset = resolve(FRONTEND, 'assets/images/rail-calm.png');
  assert.ok(existsSync(asset), 'l\'immagine della barra deve stare nel repository');
  // Un file da pochi byte sarebbe un placeholder con un altro nome.
  assert.ok(statSync(asset).size > 20_000, 'l\'immagine della barra deve essere un\'immagine vera');
}

// ---------------------------------------------------------------------------
// E — le pagine nuove contano quello che conta la Home
// ---------------------------------------------------------------------------
{
  const elenco = leggi('src/components/home/v3/aggiornamenti.ts');
  const pagina = leggi('app/aggiornamenti.tsx');
  const dettaglio = leggi('app/aggiornamento/[id].tsx');

  assert.ok(
    pagina.includes('elencoAggiornamenti(home)') && dettaglio.includes('elencoAggiornamenti(home)'),
    'pagina e dettaglio devono leggere lo stesso insieme della Home',
  );
  assert.ok(
    elenco.includes('originale non disponibile'),
    'una fonte che non si ricostruisce si dichiara anche qui',
  );
}

console.log('V3.21.3b navigation guards: tutte le asserzioni passate');
