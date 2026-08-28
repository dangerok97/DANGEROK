/**
 * V3.3 — the interface side of a profile that grows on its own.
 *
 * Three things are worth guarding here, and none of them is layout:
 *
 *   the figure is read, never sent — a percentage a client could set is a
 *   percentage that means nothing;
 *
 *   skipping does not trap anybody — someone who chose "salta per ora" on
 *   everything has answered the only question the gate is entitled to ask;
 *
 *   the profile is said plainly and never played — no streak, no badge, no
 *   "manca poco!", because there is nothing wrong with a person who has told
 *   ORA very little.
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
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

const PROGRESS = 'src/components/life-profile/LifeProfileProgress.tsx';
const CLIENT = 'src/api/client.ts';
const GATE = 'src/life-setup/gate.ts';
const SETUP = 'src/life-setup/LifeSetupConversationScreen.tsx';
const VITA = 'app/(tabs)/contesti.tsx';
const SURFACE = 'src/life-setup/LifeSetupSurface.tsx';
const GUIDED = 'src/life-setup/GuidedSetupScreen.tsx';
const ICONS = 'src/components/life-profile/areaIcon.ts';

// ---------------------------------------------------------------------------
// A — the number is read, never sent
// ---------------------------------------------------------------------------
{
  const client = readCode(CLIENT);
  assert.ok(
    /lifeProfileCompleteness: \(\) =>/.test(client),
    'the profile is fetched, with no arguments to shape it',
  );
  assert.ok(
    !/lifeProfileCompleteness[\s\S]{0,400}method: 'POST'/.test(client),
    'reading how much ORA knows is a GET',
  );
  // The one write a client may make says what a person chose, never a figure.
  const notApplicable = client.slice(client.indexOf('lifeProfileNotApplicable'));
  assert.ok(/JSON\.stringify\(\{ refs \}\)/.test(notApplicable), 'refs and nothing else');
  assert.ok(
    /lifeProfileNotApplicable: \(refs: string\[\]\) =>/.test(client),
    'a client sends what a person chose — references — and nothing else',
  );
}

// ---------------------------------------------------------------------------
// B — skipping everything must not trap anybody
// ---------------------------------------------------------------------------
{
  const gate = readCode(GATE);
  assert.ok(
    /const FIRST_RUN_OVER = \[/.test(gate),
    'the gate must distinguish "first run is over" from "profile is complete"',
  );
  for (const status of ['completed', 'skipped', 'cancelled', 'interrupted']) {
    assert.ok(
      new RegExp(`'${status}'`).test(gate.slice(gate.indexOf('FIRST_RUN_OVER'))),
      `${status} must let a person into the app`,
    );
  }
  assert.ok(
    /if \(isFirstRunOver\(st\)\) \{/.test(gate),
    'and the routing decision must use it',
  );
}

// ---------------------------------------------------------------------------
// C — progress is information, not a game
// ---------------------------------------------------------------------------
{
  const progress = readCode(PROGRESS);
  for (const forbidden of ['streak', 'badge', 'confetti', 'manca poco', 'punti', 'trophy']) {
    assert.ok(
      !progress.toLowerCase().includes(forbidden),
      `the profile must not be gamified: ${forbidden}`,
    );
  }
  assert.ok(
    !/incompleto/i.test(progress),
    '"profilo incompleto" reads as an error, and nothing is wrong',
  );
  assert.ok(
    /Quanto ORA conosce/.test(read(PROGRESS)),
    'the caption has to say what the number actually measures',
  );
  // A row a thumb can hit.
  assert.ok(/minHeight: 44/.test(progress), 'tap targets stay at 44');
}

// ---------------------------------------------------------------------------
// E — the guided first run renders what the server sends, and nothing else
// ---------------------------------------------------------------------------
{
  // Read raw: the file legitimately contains the string 'image/*', which a
  // naive comment stripper reads as the start of a comment and then eats
  // half the component. These checks are for testIDs and call sites, which
  // are unambiguous either way.
  const guided = read(GUIDED);

  // The screen draws a control; it never decides which question comes next.
  for (const forbidden of ['casa.', 'lavoro.', 'studio.', 'auto.', "=== 'casa'"]) {
    assert.ok(
      !guided.includes(forbidden),
      `the screen must not know the domain model: ${forbidden}`,
    );
  }

  // Every piece of the approved layout.
  for (const part of [
    'guided-title',
    'guided-profile',
    'guided-path',
    'guided-current-area',
    'guided-question',
    'guided-options',
    'guided-rail',
    'guided-skip-area',
    'guided-next',
    'guided-leave',
    'guided-grow',
  ]) {
    assert.ok(guided.includes(part), `the guided setup is missing ${part}`);
  }

  // Every area is recognisable before its name is read, in all three places
  // it appears — and from the icon set the app already uses.
  assert.ok(
    guided.includes('areaIconName(a.icon_key)'),
    'the path and the rail must draw each area its own icon',
  );
  assert.ok(
    guided.includes('areaIconName(current.icon_key)'),
    'and so must the heading of the area being worked on',
  );
  const icons = readCode(ICONS);
  assert.ok(
    icons.includes("from '@expo/vector-icons'"),
    'one icon system, the one already in the app',
  );
  for (const key of [
    'home', 'work', 'study', 'car', 'people', 'assets', 'finance', 'shield',
    'services', 'health',
  ]) {
    assert.ok(icons.includes(`${key}:`), `no icon for ${key}`);
  }
  assert.ok(icons.includes("-outline'"), 'outline weight throughout — Quiet Premium');

  // A document is handed over, not typed, and the person can always move
  // on: the way forward is the upload or "Più tardi", never a field with
  // nothing to write in it.
  assert.ok(guided.includes('guided-upload'), 'the document step needs a real action');
  assert.ok(
    guided.includes('DocumentPicker.getDocumentAsync'),
    'and it opens the real picker',
  );
  assert.ok(
    guided.includes('api.documentUpload') && guided.includes('api.lifeSetupAttachDocument'),
    'through the pipeline that already exists — never a second one',
  );
  assert.ok(
    guided.includes("objective.control !== 'document_upload'"),
    'a document step must never fall through to a text field',
  );
  assert.ok(guided.includes('guided-doc-state'), 'and it says where it has got to');

  // The place can be detected or typed, and the detected one is correctable.
  assert.ok(guided.includes('guided-use-location'), 'no way to offer the device position');
  assert.ok(
    guided.includes('requestDevicePosition') && guided.includes('api.lifeSetupReverseGeocode'),
    'the existing permission and geocoding path, not a new one',
  );
  assert.ok(
    /setTyped\(city\)/.test(guided),
    'what comes back fills the field, so it can still be corrected',
  );

  // Structured first: the only text input is the one behind "Altro" and the
  // handful of controls that genuinely are values.
  assert.ok(guided.includes('guided-option-altro'), '"Altro" must always be reachable');
  assert.ok(
    !/Racconta a ORA|ora-composer/.test(guided),
    'the first setup has no general composer — that is ORA, afterwards',
  );
  assert.ok(/minHeight: 44/.test(guided), 'tap targets stay at 44');

  const route = readCode('app/life-setup/index.tsx');
  assert.ok(
    /<GuidedSetupScreen/.test(route),
    'the first run is the guided setup, not the conversation',
  );
}

// ---------------------------------------------------------------------------
// D — it appears where a person is, and updates itself
// ---------------------------------------------------------------------------
{
  const setup = readCode(SETUP);
  assert.ok(
    /void refreshProfile\(\);/.test(setup),
    'and refreshes after every turn — an answer, a skip, a document',
  );
  assert.ok(
    /life-setup-done-note/.test(setup),
    'leaving says what ORA has, never "setup completato"',
  );
  assert.ok(
    !/completato/i.test(setup),
    'the profile is at whatever it is at; nothing is "completato"',
  );

  // The surface itself: structure around the words, and nothing to type into.
  const surface = readCode(SURFACE);
  for (const part of [
    'life-setup-welcome',
    'life-setup-current-area',
    'life-setup-area-objectives',
    'life-setup-skip-area',
    'life-setup-other-areas',
    'life-setup-footer',
  ]) {
    assert.ok(surface.includes(part), `the setup surface is missing ${part}`);
  }
  assert.ok(
    !/TextInput|onChangeText/.test(surface),
    'the objectives are things ORA would like to know, not fields to fill in',
  );
  assert.ok(/minHeight: 44/.test(surface), 'tap targets stay at 44');

  const vita = readCode(VITA);
  assert.ok(/<LifeProfileProgress/.test(vita), 'Vita is where a person comes back to it');
  assert.ok(
    /onOpenArea=\{\(id\) => continueSetup\(id\)\}/.test(vita),
    'and one tap continues the conversation that fills it',
  );
  assert.ok(
    /life-setup\?resume=1/.test(vita),
    'resuming is a resume, not a fresh start',
  );
}

console.log('V3.3 life-profile guards: all assertions passed');
