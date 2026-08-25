/**
 * PX1.4 — ORA conversation surface contract guards.
 *
 * Run: node --experimental-strip-types src/components/ora/ora14.test.ts
 *
 * The regression this suite exists for is silent: the Workspace hands off a
 * plan, an object and a plan item in the URL, and every one of them can be
 * dropped without anything breaking, erroring or looking wrong — the user just
 * finds themselves talking to an ORA that has never heard of their goal. So the
 * guards assert on the handoff itself, not only on the shaping helpers.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { contextFromPlanBundle, oraErrorSentence } from './contextView.ts';
import { buildOraConversationHref, oraEntryPointFrom } from '../../ora/oraNav.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

const SCREEN = 'src/components/ora/OraConversationScreen.tsx';
const START_ROUTE = 'app/ora/index.tsx';
const SESSION_ROUTE = 'app/ora/[sessionId].tsx';

// ---------------------------------------------------------------------------
// A — The handoff URL and the screen that receives it
// ---------------------------------------------------------------------------
{
  const href = buildOraConversationHref({
    planId: 'lop_x',
    objectId: 'lgo_y',
    planItemId: 'lpi_z',
    entryPoint: 'goal_workspace',
  });
  assert.equal(href, '/ora?planId=lop_x&objectId=lgo_y&planItemId=lpi_z&entry=goal_workspace');

  // Both ORA routes must read every identifier the Workspace can send. The bug
  // this replaces was exactly one file reading none of them.
  for (const route of [START_ROUTE, SESSION_ROUTE]) {
    const src = readCode(route);
    for (const key of ['planId', 'objectId', 'planItemId', 'entry']) {
      assert.ok(src.includes(key), `${route} must consume ${key} from the URL`);
    }
    assert.ok(
      /OraConversationScreen/.test(src),
      `${route} must render the one conversation surface, not a second start screen`,
    );
  }

  // A start with no session still carries the context into the runtime.
  const screen = readCode(SCREEN);
  assert.ok(
    /aiCoreStart\(\{[\s\S]*?plan_id: planId \|\| undefined[\s\S]*?object_id: objectId \|\| undefined/.test(screen),
    'creating a session must pass plan and object to AI Core',
  );
  assert.ok(
    /entry_point: entryPoint/.test(screen),
    'the entry point must reach the runtime, not be flattened to "ora"',
  );
  assert.ok(
    /announceFocus\(\{ sessionId: String\(id\)/.test(screen),
    'a freshly created session must be told which plan item it is about',
  );
  assert.ok(
    /planItemId \? \{ planItemId: String\(planItemId\) \} : \{\}/.test(screen),
    'the replaced URL must keep the plan item, or a reload loses it',
  );
}

// ---------------------------------------------------------------------------
// B — Entry point parsing
// ---------------------------------------------------------------------------
{
  assert.equal(oraEntryPointFrom('goal_workspace'), 'goal_workspace');
  assert.equal(oraEntryPointFrom('object'), 'object');
  assert.equal(oraEntryPointFrom(['home']), 'home');
  assert.equal(oraEntryPointFrom('nonsense'), 'ora');
  assert.equal(oraEntryPointFrom(undefined), 'ora');
}

// ---------------------------------------------------------------------------
// C — Context is human, or absent
// ---------------------------------------------------------------------------
{
  const bundle = {
    plan: {
      summary: "Preparare l'esame di diritto privato",
      items: [
        { id: 'lpi_1', title: 'Ripasso obbligazioni' },
        { id: 'lpi_2', title: 'Ripasso contratti' },
      ],
    },
    objects: [{ id: 'lgo_1', title: 'Ripasso: obbligazioni' }],
    next_item: { title: 'Ripasso contratti' },
  };

  const full = contextFromPlanBundle(bundle, { objectId: 'lgo_1', planItemId: 'lpi_2' });
  assert.deepEqual(full, {
    goal: "Preparare l'esame di diritto privato",
    step: 'Ripasso contratti',
    material: 'Ripasso: obbligazioni',
  });

  // Falls back to the plan's own next step, so ORA and the Workspace agree.
  assert.equal(
    contextFromPlanBundle(bundle, { objectId: null, planItemId: null })?.step,
    'Ripasso contratti',
  );
  assert.equal(
    contextFromPlanBundle(bundle, { objectId: 'lgo_missing', planItemId: null })?.material,
    null,
    'an object that is not in the bundle must not invent a material label',
  );
  assert.equal(
    contextFromPlanBundle({ plan: { summary: '  ' } }, {}),
    null,
    'a nameless plan produces no header rather than an empty one',
  );
  assert.equal(contextFromPlanBundle(null, {}), null);

  // Nothing identifier-shaped can reach the header.
  const rendered = JSON.stringify(full);
  assert.ok(
    !/lop_|lgo_|lpi_|ces_/.test(rendered),
    'internal identifiers must never appear in the context header',
  );
}

// ---------------------------------------------------------------------------
// D — Errors speak to a person who cannot restart a server
// ---------------------------------------------------------------------------
{
  assert.equal(
    oraErrorSentence({ code: 'network_unreachable' }),
    'Non riesco a raggiungere ORA in questo momento. Riprova fra poco.',
  );
  assert.equal(
    oraErrorSentence({ message: 'TypeError: Failed to fetch' }),
    'Non riesco a raggiungere ORA in questo momento. Riprova fra poco.',
  );
  assert.equal(
    oraErrorSentence({ status: 503 }),
    'ORA ha avuto un problema nel rispondere. Riprova fra poco.',
  );
  for (const err of [
    { code: 'network_unreachable' },
    { code: 'backend_url_missing' },
    { status: 500 },
  ]) {
    const msg = oraErrorSentence(err);
    assert.ok(
      !/backend|url|expo|http|status|500|503/i.test(msg),
      `conversation errors must not expose internals: ${msg}`,
    );
  }
}

// ---------------------------------------------------------------------------
// E — The runtime the surface is built on is preserved, not replaced
// ---------------------------------------------------------------------------
{
  const screen = readCode(SCREEN);
  for (const call of [
    'api.aiCoreStart',
    'api.aiCoreMessage',
    'api.aiCoreGet',
    'api.aiCoreClientResume',
    'api.aiCoreFileUpload',
    'api.lifeOsSessionFocus',
    'api.locationPostSignal',
  ]) {
    assert.ok(screen.includes(call), `${call} must still be part of the surface`);
  }
  assert.ok(
    /client_message_id: clientMessageId/.test(screen),
    'idempotent message ids must survive — retry depends on them',
  );
  assert.ok(
    /fulfilledPendingTurns/.test(screen),
    'StrictMode protection on pending client actions must remain',
  );
  assert.ok(
    /LocationPermissionSheet/.test(screen) && /requestForegroundPosition/.test(screen),
    'the location client capability must not regress',
  );
  assert.ok(
    !/ora-ai\/(?!RichOraText)/.test(screen),
    'production ORA must not depend on the dev harness beyond rich text',
  );
}

// ---------------------------------------------------------------------------
// F — A conversation, not a chat
// ---------------------------------------------------------------------------
{
  const turns = readCode('src/components/ora/OraTurns.tsx');
  assert.ok(
    /RichOraText/.test(turns),
    'ORA answers must render as rich text, not as plain bubble content',
  );
  // The ORA turn is open text: the bubble surface belongs to the user only.
  const oraTurnBlock = turns.slice(turns.indexOf('function OraTurnView'), turns.indexOf('export function OraSources'));
  assert.ok(
    !/userBubble|styles\.bubble/.test(oraTurnBlock),
    'the ORA turn must not be wrapped in a chat bubble',
  );
  assert.ok(
    /showMark={turns\[i - 1\]\?\.role !== 'ora'}/.test(turns),
    'the ORA mark appears when ORA starts speaking, not on every turn',
  );
}

// ---------------------------------------------------------------------------
// G — Composer and voice honesty
// ---------------------------------------------------------------------------
{
  const screen = readCode(SCREEN);
  assert.ok(/placeholder="Scrivi a ORA…"/.test(screen), 'composer placeholder must be short and human');
  assert.ok(
    /La voce non è ancora disponibile\./.test(screen),
    'the mic must admit voice is not available, in plain words',
  );
  assert.ok(
    !/stesso motore|riconoscimento vocale/.test(screen),
    'no engine-level wording in the conversation surface',
  );
  assert.ok(
    !/Cosa vuoi raccontare a ORA/.test(screen),
    'the onboarding-flavoured placeholder must not return',
  );
}

// ---------------------------------------------------------------------------
// H — Reading width, and one surface only
// ---------------------------------------------------------------------------
{
  const width = Number(/const READING_MAX_WIDTH = (\d+)/.exec(read(SCREEN))?.[1]);
  assert.ok(width >= 680 && width <= 760, `conversation reading width out of range: ${width}`);
  assert.ok(
    !/aiCoreStart/.test(readCode(START_ROUTE)),
    'the start route must delegate, never hold a second copy of the send logic',
  );
}

// ---------------------------------------------------------------------------
// I — Opening state: invitation and composer are one block
// ---------------------------------------------------------------------------
{
  const screen = readCode(SCREEN);
  assert.ok(
    /const emptyStart = !boot && turns\.length === 0 && !busy;/.test(screen),
    'the opening layout must be chosen by whether anything has been said yet',
  );
  assert.ok(
    /startSpacerTop|startBlock/.test(screen),
    'with no turns the composer must sit with the invitation, not at the page foot',
  );
  assert.ok(
    /divider=\{!emptyStart\}/.test(screen),
    'the composer rule belongs to the anchored layout only',
  );

  const chrome = readCode('src/components/ora/OraChrome.tsx');
  assert.ok(/Ci sono\./.test(chrome), 'the contextual opening must state that ORA is ready');
  assert.ok(
    !/senza rispiegare/.test(chrome),
    'the opening must not tell the user what they do not have to do',
  );
  assert.ok(
    !/\{about\}|context\.material|context\.step|context\.goal/.test(
      chrome.slice(chrome.indexOf('OraContextOpening'), chrome.indexOf('OraWorking')),
    ),
    'the opening must not repeat what the header already shows',
  );
}

console.log('ora14: all assertions passed');
