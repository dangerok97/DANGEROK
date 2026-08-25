/**
 * PX1.6 — Attività / trust centre contract guards.
 *
 * Two distinctions carry this page, and both are easy to lose by accident:
 * a question ORA asks is not an action it has prepared and is holding for a
 * yes, and something a person postponed is not something that is blocked. If
 * either collapses, the page still looks fine and quietly stops being true —
 * which is why they are asserted here rather than left to review.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  actorLabel,
  dayBadge,
  dueLabel,
  heroAction,
  isActivityEmpty,
  questionCta,
  questionEyebrow,
  waitingLabel,
  whenLabel,
} from './activityView.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const BACKEND = resolve(FRONTEND, '../backend');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readBackend = (rel: string) => readFileSync(resolve(BACKEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
const readBackendCode = (rel: string) =>
  readBackend(rel)
    .replace(/^\s*#.*$/gm, '')
    .replace(/"""[\s\S]*?"""/g, '');

const ROUTE = 'app/(tabs)/attivita.tsx';
const PARTS = 'src/components/activity/ActivityParts.tsx';
const MODEL = 'activity/presentation.py';

// ---------------------------------------------------------------------------
// A — Consent is not a question with a different label
// ---------------------------------------------------------------------------
{
  assert.equal(questionCta(true), 'Conferma');
  assert.equal(questionCta(false), 'Rispondi');
  assert.equal(questionEyebrow(true), 'Serve la tua conferma');
  assert.equal(questionEyebrow(false), null);

  const model = readBackendCode(MODEL);
  assert.ok(
    /DELIVERY_CONSENT = "propose_action"/.test(model) &&
      /DELIVERY_QUESTION = "ask_user"/.test(model),
    'the two delivery modes must stay distinct in the read model',
  );
  assert.ok(
    /"needs_consent": delivery == DELIVERY_CONSENT/.test(model),
    'consent must be carried as a fact on the row, not inferred by the client',
  );

  // The page may never take the proposed action itself.
  const route = readCode(ROUTE);
  assert.ok(
    !/suggestionAccept|api\.\w*accept|acceptSuggestion/i.test(route),
    'Attività must never execute a proposed action on the user behalf',
  );
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// B — Waiting is a dependency, never a future date, and snooze is not one
// ---------------------------------------------------------------------------
// A first pass treated any item with an upcoming date as "waiting", which put
// ordinary future deadlines next to genuine blockers. A date that has not
// arrived yet is not a dependency; it belongs in PROSSIME SCADENZE. Only two
// structured signals now qualify a row: a named blocker Home already records
// on the goal, or the item's own status ("waiting"), set deliberately by the
// adapters that own a real hold — never derived from a date. The one thing
// that also produces that status without meaning any of that is the user's
// own snooze, so it is excluded explicitly.
{
  const model = readBackendCode(MODEL);
  const waitingFn = model.slice(model.indexOf('def _waiting_rows'), model.indexOf('def _route_for_item'));
  assert.ok(
    waitingFn.includes('item.get("status") == "waiting" and not meta.get("snoozed_until")'),
    'a snoozed item must be excluded even when its status happens to read "waiting"',
  );
  assert.ok(waitingFn.includes('goal_blockers'), 'a named blocker on the goal must still qualify a row');
  assert.ok(
    !waitingFn.includes('UPCOMING'),
    'a future date must never by itself qualify a row as waiting',
  );

  assert.equal(waitingLabel('una risposta esterna'), 'In attesa di una risposta esterna');
  assert.equal(waitingLabel(null, null), 'In attesa di procedere');
}

// ---------------------------------------------------------------------------
// B2 — Completed shows outcomes, never the invitation back into a conversation
// ---------------------------------------------------------------------------
// A résumé card is an open door, not a result: it reaches home_item_state as
// completed only because Home stops tracking a conversation once its session
// closes, a fact about the session, not something the user or ORA finished.
// The read model refuses it by structural kind, never by matching its words.
{
  const model = readBackendCode(MODEL);
  const completedFn = model.slice(
    model.indexOf('async def _completed_rows'),
    model.indexOf('# --- assembly'),
  );
  assert.ok(
    completedFn.includes(
      'item.get("type") == "resume" or item.get("source_type") == "conversation_session"',
    ),
    'a résumé card must be excluded from completed by its structural kind',
  );
  assert.ok(
    !/startswith\(.Continua|title\.lower\(\)\s*==|in title/.test(completedFn),
    'completed must never filter by matching the title text',
  );
}

// ---------------------------------------------------------------------------
// C — Attribution: what ORA did vs what ORA noticed
// ---------------------------------------------------------------------------
{
  assert.equal(actorLabel('ora'), 'ORA');
  assert.equal(actorLabel('observed'), 'Risulta aggiornato');
  assert.notEqual(actorLabel('ora'), actorLabel('observed'));

  const model = readBackendCode(MODEL);
  assert.ok(
    /"actor": "observed"/.test(model) && /"actor": "ora"/.test(model),
    'both attributions must exist — a single one would make every change ORA work',
  );
}

// ---------------------------------------------------------------------------
// D — Time is spoken
// ---------------------------------------------------------------------------
{
  const now = new Date('2026-08-25T18:00:00Z');
  assert.ok(/^Oggi, /.test(whenLabel('2026-08-25T09:12:00Z', now) || ''));
  assert.ok(/^Ieri, /.test(whenLabel('2026-08-24T18:45:00Z', now) || ''));
  const old = whenLabel('2026-06-01T10:00:00Z', now) || '';
  assert.ok(old && !/\d{4}-\d{2}-\d{2}/.test(old));
  assert.equal(whenLabel(null), null);

  // Midday timestamps: the distance is counted in calendar days as the user
  // lives them, so an instant near midnight legitimately belongs to the next
  // day in some zones and would make the expectation, not the code, wrong.
  assert.equal(dueLabel('2026-08-25T12:00:00Z', now), 'Scade oggi');
  assert.equal(dueLabel('2026-08-26T12:00:00Z', now), 'Scade domani');
  assert.equal(dueLabel('2026-08-28T12:00:00Z', now), 'Scade tra 3 giorni');
  assert.equal(dueLabel('2026-08-20T12:00:00Z', now), 'Scaduta');
  assert.equal(dueLabel(undefined), null);

  const badge = dayBadge('2026-08-28T09:00:00Z');
  assert.equal(badge?.day, '28');
  assert.ok(badge && /^[A-Z]{3}$/.test(badge.month) && !/\d/.test(badge.month));
}

// ---------------------------------------------------------------------------
// E — The hero offers a real action, never a dismissal
// ---------------------------------------------------------------------------
{
  assert.equal(
    heroAction([
      { kind: 'snooze', label: 'Rimanda' },
      { kind: 'resume', label: 'Continua' },
    ])?.kind,
    'resume',
  );
  assert.equal(
    heroAction([{ kind: 'snooze', label: 'Rimanda' }, { kind: 'ignore', label: 'Ignora' }]),
    null,
    'an item whose only actions dismiss it has no primary action',
  );
  assert.equal(heroAction([]), null);
  assert.equal(heroAction(undefined), null);
}

// ---------------------------------------------------------------------------
// F — Empty, and sections that vanish
// ---------------------------------------------------------------------------
{
  assert.equal(isActivityEmpty(null), true);
  assert.equal(isActivityEmpty({ questions: [], waiting: [], updates: [] }), true);
  assert.equal(isActivityEmpty({ completed: [{}] }), false);
  assert.equal(isActivityEmpty({ attention: { title: 'x' } }), false);

  const parts = read(PARTS);
  for (const guard of [
    'if (!questions.length) return null',
    'if (!waiting.length) return null',
    'if (!updates.length) return null',
    'if (!rows.length) return null',
    'if (!deadlines.length) return null',
    'if (!completed.length) return null',
  ]) {
    assert.ok(parts.includes(guard), `missing empty guard: ${guard}`);
  }
  assert.ok(
    /if \(!present\.length\) return null/.test(parts),
    'a panel with no children must not render its own chrome',
  );
}

// ---------------------------------------------------------------------------
// G — Dedupe is by identity, never by words
// ---------------------------------------------------------------------------
{
  const model = readBackendCode(MODEL);
  const dedupe = model.slice(model.indexOf('def _dedupe'), model.indexOf('async def build_activity'));
  assert.ok(/row\.get\("id"\)/.test(dedupe), 'dedupe must key on the composed identity');
  assert.ok(
    !/title|lower\(\)|similar|ratio|difflib/.test(dedupe),
    'dedupe must never compare titles',
  );
  // Ids are namespaced by source so two systems cannot collide by accident.
  for (const ns of ['f"suggestion:', 'f"memory:', 'f"item:']) {
    assert.ok(model.includes(ns), `rows must carry a namespaced identity: ${ns}`);
  }
}

// ---------------------------------------------------------------------------
// H — No implementation state reaches the interface
// ---------------------------------------------------------------------------
{
  const surface = readCode(ROUTE) + readCode(PARTS) + readCode('src/components/activity/activityView.ts');
  for (const leak of [
    'AttentionDecision',
    'waiting_user',
    'pending_turn',
    'action_session',
    'ImpactAssessment',
    'LifeChangeSignal',
    'confidence',
    'dedupe_key',
  ]) {
    assert.ok(!surface.includes(leak), `internal state must not appear in the UI: ${leak}`);
  }
  // The delivery vocabulary stays in the read model; the client reads a boolean.
  assert.ok(
    !/'ask_user'|"ask_user"|'propose_action'|"propose_action"/.test(surface),
    'the client must not branch on Attention delivery strings',
  );
}

// ---------------------------------------------------------------------------
// I — Answers go where they belong, and nothing dead-ends
// ---------------------------------------------------------------------------
{
  const route = readCode(ROUTE);
  assert.ok(
    /api\.lifeMemoryClarifyStart/.test(route) && /memory-clarify\//.test(route),
    'a clarification must open the loop that owns it',
  );
  assert.ok(/if \(q\.route\)/.test(route), 'a suggestion must open the route it carries');
  assert.ok(
    /buildOraConversationHref/.test(route),
    'the last resort must still be a real destination',
  );
  assert.ok(
    !/PATCH|api\.\w*[Ww]rite|api\.\w*[Mm]utate/.test(route),
    'Attività is presentation only',
  );
}

// ---------------------------------------------------------------------------
// J — Composition, bounds and one read
// ---------------------------------------------------------------------------
{
  const route = read(ROUTE);
  const rail = Number(/const RAIL_WIDTH = (\d+)/.exec(route)?.[1]);
  const twoCol = Number(/const TWO_COLUMN_MIN = (\d+)/.exec(route)?.[1]);
  assert.ok(rail >= 280 && rail <= 320, `context rail must stay a rail (${rail})`);
  assert.ok(twoCol - rail - 24 * 3 >= 700, 'main area too narrow at the two-column threshold');

  // One aggregated read, not a fan-out from the page.
  const fetches = (readCode(ROUTE).match(/await api\.\w+\(/g) || []).filter(
    (f) => !f.includes('lifeMemoryClarifyStart'),
  );
  assert.deepEqual(fetches, ['await api.getActivity('], 'the page must load from one request');

  const model = readBackendCode(MODEL);
  for (const cap of ['MAX_QUESTIONS', 'MAX_WAITING', 'MAX_UPDATES', 'MAX_DEADLINES', 'MAX_COMPLETED']) {
    assert.ok(new RegExp(`${cap} = \\d+`).test(model), `${cap} must bound its section`);
  }
  assert.ok(
    /COMPLETED_WINDOW_DAYS = \d+/.test(model) && /UPDATE_WINDOW_DAYS = \d+/.test(model),
    'recent must mean a window, not all history',
  );
  // A failing source costs its rows, never the page.
  assert.ok(
    /partial\.append\("home"\)/.test(model) && /partial\.append\("life_memory"\)/.test(model),
    'each source must fail soft and mark the payload partial',
  );
}

console.log('activity16: all assertions passed');
