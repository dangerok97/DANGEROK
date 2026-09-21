/**
 * V3.21.3c — Vita e Conosciamoci sono una cosa sola.
 *
 *     LA VOCE «VITA» APRE L'ESPERIENZA APPROVATA.
 *
 * Portava a `/contesti`, che è un'altra grammatica per la stessa domanda — che
 * cosa sai di me, e che cosa ti manca — mentre il percorso approvato viveva a
 * `/life-setup` e ci si arrivava solo al primo accesso. Due esperienze
 * concorrenti per la stessa persona.
 *
 * Queste guardie tengono ferme la destinazione, le cose che nella schermata
 * non devono tornare (un bottone che non apre niente, una CTA che non vuole
 * dire niente) e il fatto che quello che manca sia raggiungibile.
 *
 *     node --experimental-strip-types src/shell/vita3213c.test.ts
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
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
// A — la voce Vita porta all'esperienza approvata
// ---------------------------------------------------------------------------
{
  const voci = leggi('src/shell/navItems.ts');
  const shell = leggi('src/shell/DesktopShell.tsx');

  assert.ok(voci.includes("href: '/vita'"), 'la voce Vita deve portare a /vita');
  assert.ok(existsSync(resolve(FRONTEND, 'app/vita.tsx')), 'manca la pagina /vita');
  assert.ok(
    leggi('app/vita.tsx').includes('GuidedSetupScreen'),
    '/vita deve essere Conosciamoci, non una terza schermata',
  );
  // Tre indirizzi, una sola voce accesa nella barra.
  for (const rotta of ['/vita', '/life-setup', '/contesti']) {
    assert.ok(shell.includes(`pathname.startsWith('${rotta}')`), `${rotta} deve accendere Vita`);
  }
}

// ---------------------------------------------------------------------------
// B — niente CTA che non vogliono dire niente
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(!schermo.includes('Entra in ORA'), '«Entra in ORA» non vuole dire niente: la persona è già dentro');
  assert.ok(schermo.includes('Lo faccio più tardi'), 'la CTA secondaria della reference deve esserci');
  assert.ok(schermo.includes('Continua con {current.title}'), '«Continua con X» deve nominare l\'area');
  // E il menu tutto suo che portava Vita su /contesti non deve tornare.
  assert.ok(!schermo.includes("{ label: 'Vita', href: '/contesti' }"), 'niente seconda navigazione');
}

// ---------------------------------------------------------------------------
// C — quello che manca si può aprire, e le aree si scelgono
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(
    schermo.includes('goNextArea(current.area_id, o.ref)'),
    'ogni voce di «cosa manca» deve aprire quella domanda',
  );
  assert.ok(
    (schermo.match(/onPress=\{\(\) => void goNextArea\(a\.area_id\)\}/g) || []).length >= 2,
    'percorso e colonna di destra devono aprire l\'area',
  );
  assert.ok(
    schermo.includes('testID={`guided-gap-${o.ref}`}'),
    'le voci mancanti devono essere raggiungibili anche dalle prove',
  );
}

// ---------------------------------------------------------------------------
// D — riprendere è riprendere, non ricominciare
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(schermo.includes('useLocalSearchParams'), '?area= deve essere letto davvero');
  assert.ok(
    schermo.includes('void goNextArea(voluta)'),
    'con ?area= si apre quell\'area, non quella che capita',
  );
}

// ---------------------------------------------------------------------------
// E — si dice a che cosa servono le risposte
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(schermo.includes('current?.purpose'), 'ogni area dice a che cosa serve');
  assert.ok(
    schermo.includes('setPercheAperto'),
    '«Perché queste domande?» deve aprire una spiegazione, non fare finta',
  );
}

// ---------------------------------------------------------------------------
// F — le situazioni della vecchia pagina non sono sparite
// ---------------------------------------------------------------------------
{
  const schermo = leggi(SCHERMO);

  assert.ok(schermo.includes('In questo periodo'), 'le situazioni in corso restano');
  assert.ok(schermo.includes('api.getLifeMap()'), 'e vengono dalla stessa fonte di prima');
}

console.log('V3.21.3c Vita guards: tutte le asserzioni passate');
