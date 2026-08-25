/**
 * PX1.3 — Workspace 2.0 contract guards.
 *
 * Run: node --experimental-strip-types src/components/workspace/workspace2.test.ts
 *
 * Same two kinds of assertion as the PX1.1 suite: real behaviour executed, and
 * source guards that read the Workspace files and assert on what they do NOT
 * contain. The guards matter here because the failure mode is a *reappearance*
 * — an internal revision number, a raw date, a percentage — creeping back into
 * a surface that is supposed to speak human.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  completedCount,
  humanDate,
  isPlanComplete,
  materials,
  planProgression,
  publicSources,
} from './planView.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
/** Judge what the product renders, not what a comment says about it. */
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

const ROUTE = 'app/goal-workspace/[planId].tsx';

// ---------------------------------------------------------------------------
// A — The plan reads as a progression, and "now" is the backend's choice
// ---------------------------------------------------------------------------
{
  const items = [
    { id: 'c', title: 'Terzo', order: 2, status: 'not_started' },
    { id: 'a', title: 'Primo', order: 0, status: 'completed' },
    { id: 'b', title: 'Secondo', order: 1, status: 'in_progress' },
  ];
  const steps = planProgression(items, 'b');
  assert.deepEqual(
    steps.map((s) => [s.id, s.state]),
    [['a', 'done'], ['b', 'now'], ['c', 'next']],
    'progression must follow plan order and mark only the backend next_item as now',
  );

  // The interface must never promote a step on its own — with no next_item
  // from the backend, nothing is "now".
  assert.equal(
    planProgression(items, undefined).filter((s) => s.state === 'now').length,
    0,
    'without a backend next_item the UI must not invent a current step',
  );

  // A skipped step is behind you, not ahead of you.
  assert.equal(
    planProgression([{ id: 'x', title: 'X', status: 'skipped' }], null)[0].state,
    'done',
  );
  assert.equal(completedCount(items), 1);
  assert.deepEqual(planProgression(null, null), [], 'a plan with no steps renders no progression');
}

// ---------------------------------------------------------------------------
// B — Completion is a real state, not the absence of a next step
// ---------------------------------------------------------------------------
{
  const done = [{ id: 'a', title: 'A', status: 'completed' }];
  assert.equal(isPlanComplete({ status: 'active', items: done }, null), true);
  assert.equal(isPlanComplete({ status: 'completed', items: [] }, null), true);
  assert.equal(
    isPlanComplete({ status: 'active', items: done }, { id: 'a' }),
    false,
    'a plan the backend still has work for is not complete',
  );
  assert.equal(
    isPlanComplete({ status: 'active', items: [] }, null),
    false,
    'a plan with no steps at all is empty, not finished',
  );
  assert.equal(isPlanComplete(null, null), false);
}

// ---------------------------------------------------------------------------
// C — Sources are things a person recognises, never internal references
// ---------------------------------------------------------------------------
{
  const out = publicSources([
    { display_name: 'Contratto di locazione.pdf', authority_label: 'Caricato da te' },
    { display_name: 'lcf_9f31c2', authority_label: 'internal' },
    { display_name: 'DOC_44', authority_label: 'internal' },
    { display_name: 'lop_1', authority_label: '' },
    { display_name: '   ', authority_label: 'x' },
  ]);
  assert.deepEqual(
    out.map((s) => s.name),
    ['Contratto di locazione.pdf'],
    'identifier-shaped and empty sources must never reach the screen',
  );
}

// ---------------------------------------------------------------------------
// D — Dates are spoken, never printed as stored
// ---------------------------------------------------------------------------
{
  const label = humanDate('2026-09-19');
  assert.ok(label && !/\d{4}-\d{2}-\d{2}/.test(label), 'a date must not render as YYYY-MM-DD');
  assert.equal(humanDate(null), null);
  assert.equal(humanDate('not-a-date'), null, 'an unparseable date says nothing rather than lying');
}

// ---------------------------------------------------------------------------
// E — Materials keep their names; a nameless object still gets a human label
// ---------------------------------------------------------------------------
{
  const m = materials([
    { id: '1', title: 'Checklist trasloco', purpose: 'Cosa fare prima' },
    { id: '2' },
    { title: 'senza id' },
  ]);
  assert.deepEqual(m.map((x) => x.id), ['1', '2']);
  assert.equal(m[1].title, 'Materiale', 'an untitled object must not render as blank');
}

// ---------------------------------------------------------------------------
// F — Human presentation: no implementation state on the surface
// ---------------------------------------------------------------------------
{
  const code = readCode(ROUTE) + readCode('src/components/workspace/WorkspaceParts.tsx')
    + readCode('src/components/workspace/ActiveWork.tsx');

  assert.ok(!/\brev\b|\.revision\b/.test(code), 'the object revision number must not be rendered');
  assert.ok(
    !/progress_ratio|progressPct|%`|\{progress/.test(code),
    'a completion percentage must not be the way progress is communicated',
  );
  assert.ok(
    !/plan\.target_date\}|\{it\.due_date\}|due_date\s*\?\s*`/.test(code),
    'raw stored dates must pass through humanDate before being shown',
  );
  assert.ok(
    !/object_kind|schema_version|content_schema|Oggetti creati/.test(code),
    'internal object vocabulary must not appear in the interface',
  );
}

// ---------------------------------------------------------------------------
// G — The generative object architecture is reused, not reimplemented
// ---------------------------------------------------------------------------
{
  const route = read(ROUTE);
  const work = read('src/components/workspace/ActiveWork.tsx');

  assert.ok(
    /GenerativeObjectRenderer/.test(work),
    'the active work surface must render the existing GenerativeObjectRenderer',
  );
  for (const prop of ['content=', 'objectId=', 'onInteract=']) {
    assert.ok(work.includes(prop), `renderer must keep receiving ${prop}`);
  }
  assert.ok(
    /api\.lifeOsObjectInteract/.test(route) && /api\.lifeOsSessionFocus/.test(route),
    'object interaction and session focus must still be reported to the backend',
  );

  // The hand-off to ORA carries the context that makes the conversation know
  // what we were doing. Losing any of these turns "Continua" into a cold start.
  for (const key of ['planId:', 'objectId', 'planItemId:', 'entryPoint', 'sessionId:']) {
    assert.ok(route.includes(key), `ORA continuation must preserve ${key}`);
  }
  assert.ok(
    /entryPoint:\s*'goal_workspace'|entryPoint,/.test(route),
    'the goal_workspace entry point must survive',
  );
  // Within the hand-off, focus is recorded before the navigation that carries
  // the session — otherwise the conversation can open before ORA has been told
  // what we were looking at.
  const handoff = route.slice(route.indexOf('const openOra'), route.indexOf('const continueWithOra'));
  const focusAt = handoff.indexOf('lifeOsSessionFocus');
  const sessionPushAt = handoff.indexOf('sessionId: sess');
  assert.ok(focusAt > 0 && sessionPushAt > 0, 'the hand-off must both record focus and pass the session');
  assert.ok(focusAt < sessionPushAt, 'focus must be recorded before navigating away');
}

// ---------------------------------------------------------------------------
// H — Composition: one shell language, work column wider than the rail
// ---------------------------------------------------------------------------
{
  const route = read(ROUTE);
  const railWidth = Number(/const RAIL_WIDTH = (\d+)/.exec(route)?.[1]);
  const twoColMin = Number(/const TWO_COLUMN_MIN = (\d+)/.exec(route)?.[1]);
  const maxWidth = Number(/const WORKSPACE_MAX_WIDTH = (\d+)/.exec(route)?.[1]);

  assert.ok(railWidth >= 260 && railWidth <= 320, 'context rail must stay a rail (260–320)');
  const mainAtMin = twoColMin - railWidth - 24 * 3;
  assert.ok(mainAtMin >= 660, `main work area too narrow at the two-column threshold (${mainAtMin})`);
  assert.ok(maxWidth - railWidth <= 900, 'the work column must not sprawl past a readable width');
  assert.ok(
    !/AppScreen|ScreenHeader|SectionHeader|AppCard/.test(readCode(ROUTE)),
    'Workspace 2.0 uses the Home 3.0 shell language, not a second one layered on top',
  );
}

// ---------------------------------------------------------------------------
// I — Every state is handled
// ---------------------------------------------------------------------------
{
  const route = readCode(ROUTE);
  for (const state of ['WorkspaceSkeleton', 'WorkspaceError', 'PlanComplete', 'NoWorkYet']) {
    assert.ok(route.includes(state), `the ${state} state must be reachable from the route`);
  }
  assert.ok(!/ActivityIndicator/.test(route), 'loading is a shaped skeleton, not a bare spinner');

  // Sources and the material selector disappear when they have nothing to say.
  assert.ok(
    /if \(!sources\.length\) return null/.test(read('src/components/workspace/WorkspaceParts.tsx')),
    'the sources section must be absent, not empty, when there are no sources',
  );
  assert.ok(
    /if \(materials\.length < 2\) return null/.test(read('src/components/workspace/WorkspaceParts.tsx')),
    'a single material needs no chooser',
  );
}

console.log('workspace2: all assertions passed');
