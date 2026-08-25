/**
 * PX1.5 — Vita / memory trust contract guards.
 *
 * Run: node --experimental-strip-types src/components/vita/vita15.test.ts
 *
 * This page is the one where a wrong detail costs trust rather than time: a
 * fabricated question, a count that does not add up, an internal identifier or
 * an English instruction meant for the reasoning core would each turn a map of
 * someone's life into a view over a database. So the guards check what reaches
 * the screen, and what must never reach it.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { buildVita, isVitaEmpty, salientFacts, whenLabel, FACTS_PER_AREA } from './vitaModel.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

const ROUTE = 'app/(tabs)/contesti.tsx';
const DETAIL = 'app/life-area/[areaId].tsx';

const MAP = {
  areas: [
    { id: 'area:casa', domain: 'casa', title: 'Casa', identity: 'via Roma 15' },
    { id: 'area:auto', domain: 'auto', title: 'Auto', identity: null },
  ],
  situations: [
    {
      id: 'situation:1',
      kind: 'life_os',
      title: 'Trasferirmi a Milano',
      temporal: 'tra 12g',
      summary: 'Visitare tre appartamenti',
      href: '/goal-workspace/lop_1',
      visual: { status: 'ready', url: '/api/visuals/vis_1' },
    },
    { id: 'situation:2', kind: 'study', title: '  ', href: '' },
  ],
};

const MEMORY = {
  memories: [
    { id: 'm1', statement: 'Vivi in via Roma 15.', belief_statement: 'Indirizzo: via Roma 15.', status: 'known', domain: 'casa', provenance_label: 'Me lo hai detto', updated_at: '2026-08-25T10:00:00Z' },
    { id: 'm2', statement: 'Il regolamento vieta i traslochi la domenica.', status: 'known', domain: 'casa', provenance_label: 'Da un documento', updated_at: '2026-08-25T09:00:00Z' },
    { id: 'm3', statement: 'Il contratto è un affitto.', status: 'known', domain: 'casa', provenance_label: 'Da un documento', updated_at: '2026-08-24T09:00:00Z' },
    { id: 'm4', statement: 'Hai una casella postale.', status: 'known', domain: 'casa', provenance_label: 'Me lo hai detto', updated_at: '2026-08-20T09:00:00Z' },
    {
      id: 'm5',
      statement: 'Mi risulta che la sede sia ibrida, ma non ne sono ancora sicura.',
      belief_statement: 'Sede: ibrida.',
      status: 'ambiguous',
      clarifiable: true,
      clarification_goal: 'Determine whether this belief about the user is accurate.',
      domain: 'casa',
      provenance_label: 'Da quello che ORA ha capito',
      updated_at: '2026-08-25T11:00:00Z',
    },
    { id: 'm6', statement: 'Vecchio indirizzo.', status: 'superseded', domain: 'casa', updated_at: '2026-08-25T12:00:00Z' },
    { id: 'm7', statement: 'Orfano senza area.', status: 'known', domain: 'sport', updated_at: '2026-08-25T12:00:00Z' },
  ],
};

// ---------------------------------------------------------------------------
// A — Areas come from the Life Map, never from stray memory domains
// ---------------------------------------------------------------------------
{
  const v = buildVita(MAP as any, MEMORY as any);
  assert.deepEqual(v.areas.map((a) => a.domain), ['casa', 'auto']);
  assert.ok(
    !v.areas.some((a) => a.domain === 'sport'),
    'a memory in an unknown domain must not invent a life area',
  );
  // Second area has no memories at all and still exists — the map decides.
  assert.deepEqual(v.areas[1].facts, []);
}

// ---------------------------------------------------------------------------
// B — A card is a summary, not the record
// ---------------------------------------------------------------------------
{
  const v = buildVita(MAP as any, MEMORY as any);
  const casa = v.areas[0];
  assert.equal(casa.facts.length, FACTS_PER_AREA);
  assert.equal(casa.moreCount, 2, 'the rest is counted, not dumped');
  assert.ok(
    !casa.facts.some((f) => f.statement === 'Vecchio indirizzo.'),
    'superseded memories must never be presented as current',
  );
  // Recency leads; what ORA is unsure of does not headline a summary.
  assert.equal(casa.facts[0].statement, 'Indirizzo: via Roma 15.');
  assert.equal(casa.facts.filter((f) => f.uncertain).length, 0);

  const ordered = salientFacts(MEMORY.memories.filter((m) => m.domain === 'casa') as any);
  assert.equal(ordered[ordered.length - 1].uncertain, true, 'uncertain sinks to the bottom');
}

// ---------------------------------------------------------------------------
// C — Provenance is human, and comes from the backend
// ---------------------------------------------------------------------------
{
  const v = buildVita(MAP as any, MEMORY as any);
  const provs = v.areas[0].facts.map((f) => f.provenance);
  assert.deepEqual(new Set(provs), new Set(['Me lo hai detto', 'Da un documento']));
  const rendered = JSON.stringify(v);
  assert.ok(!/confidence|0\.\d|node_|life_node|namespace/i.test(rendered),
    'no score or store vocabulary may reach the view model');
}

// ---------------------------------------------------------------------------
// D — Questions are real, answerable, and phrased for a person
// ---------------------------------------------------------------------------
{
  const v = buildVita(MAP as any, MEMORY as any);
  assert.equal(v.questions.length, 1);
  assert.equal(v.questions[0].memoryId, 'm5', 'a question must point at the memory it clarifies');
  assert.ok(
    /non ne sono ancora sicura/.test(v.questions[0].question),
    'the question must use the human uncertainty phrasing',
  );
  assert.ok(
    !/Determine whether/i.test(JSON.stringify(v)),
    'clarification_goal is an instruction to the core, never user-facing copy',
  );

  // Ambiguous but not clarifiable → nowhere to send the user → not asked.
  const noRoute = buildVita(MAP as any, {
    memories: [{ id: 'x', statement: 'Forse.', status: 'ambiguous', clarifiable: false, domain: 'casa' }],
  } as any);
  assert.equal(noRoute.questions.length, 0);
}

// ---------------------------------------------------------------------------
// E — Updates and counts are real or absent
// ---------------------------------------------------------------------------
{
  const v = buildVita(MAP as any, MEMORY as any);
  assert.ok(v.updates.length > 0);
  // Most recently touched first, whatever it belongs to. The feed is about
  // what ORA now knows differently, so a change in a domain the map has no
  // area for still counts — it simply carries no area label rather than being
  // filed under an invented one.
  assert.equal(v.updates[0].id, 'm7', 'most recently touched first');
  assert.equal(v.updates[0].areaTitle, null, 'an unknown domain gets no label, not a fake one');
  assert.equal(v.updates[1].id, 'm5');
  assert.equal(v.updates[1].areaTitle, 'Casa', 'an update says which part of life it belongs to');
  assert.ok(
    v.updates.every((u) => !!u.at),
    'an update without a real timestamp must not be shown',
  );

  const counts = Object.fromEntries(v.summary.map((r) => [r.label, r.value]));
  assert.equal(counts['Situazioni in corso'], v.situations.length);
  assert.equal(counts['Da chiarire'], v.questions.length);

  // Nothing countable → no panel at all, rather than a row of zeros.
  const bare = buildVita({ areas: MAP.areas } as any, null);
  assert.deepEqual(bare.summary, []);
  assert.deepEqual(bare.updates, []);
}

// ---------------------------------------------------------------------------
// F — Situations, visuals and empty
// ---------------------------------------------------------------------------
{
  const v = buildVita(MAP as any, MEMORY as any);
  assert.equal(v.situations.length, 1, 'a titleless situation is not a situation');
  assert.equal(v.situations[0].visualUrl, '/api/visuals/vis_1');
  assert.equal(v.situations[0].visualPending, false);

  const pending = buildVita(
    { situations: [{ id: 's', title: 'X', visual: { status: 'queued', url: null } }] } as any,
    null,
  );
  assert.equal(pending.situations[0].visualUrl, null);
  assert.equal(pending.situations[0].visualPending, true);

  assert.equal(isVitaEmpty(buildVita(null, null)), true);
  assert.equal(isVitaEmpty(v), false);
  // Memories alone are not a life map: without areas or situations the page is
  // still empty, and says so instead of drawing a page out of loose facts.
  assert.equal(isVitaEmpty(buildVita({}, MEMORY as any)), true);
}

// ---------------------------------------------------------------------------
// G — Time is spoken
// ---------------------------------------------------------------------------
{
  const now = new Date('2026-08-25T18:00:00Z');
  assert.ok(/^Oggi, /.test(whenLabel('2026-08-25T09:12:00Z', now) || ''));
  assert.ok(/^Ieri, /.test(whenLabel('2026-08-24T18:45:00Z', now) || ''));
  const old = whenLabel('2026-06-01T10:00:00Z', now) || '';
  assert.ok(old && !/^(Oggi|Ieri)/.test(old) && !/\d{4}-\d{2}-\d{2}/.test(old));
  assert.equal(whenLabel('nope'), null);
}

// ---------------------------------------------------------------------------
// H — No taxonomy is imposed by the interface
// ---------------------------------------------------------------------------
{
  const surface =
    readCode(ROUTE) +
    readCode(DETAIL) +
    readCode('src/components/vita/vitaModel.ts') +
    readCode('src/components/vita/VitaCards.tsx') +
    readCode('src/components/vita/VitaRail.tsx') +
    readCode('src/components/vita/VitaChrome.tsx');

  for (const domain of ['Casa', 'Salute', 'Finanze', 'Mobilità', 'Famiglia', 'Viaggi']) {
    assert.ok(
      !new RegExp(`['"\`]${domain}['"\`]`).test(surface),
      `Vita must not name ${domain} itself — areas come from the user's data`,
    );
  }
  assert.ok(
    !/confidence|evidence_id|node_id|source_type:\s*['"]/.test(surface),
    'no store or scoring vocabulary in the surface',
  );
}

// ---------------------------------------------------------------------------
// I — Correction runs through capabilities that already exist
// ---------------------------------------------------------------------------
{
  const route = readCode(ROUTE);
  assert.ok(
    /api\.lifeMemoryClarifyStart/.test(route),
    'a question must open the existing clarification loop',
  );
  assert.ok(
    /memory-clarify\//.test(route),
    'the clarify session must land on the surface that already handles it',
  );
  assert.ok(
    !/PATCH|api\.\w*[Uu]pdateMemory|api\.\w*[Ww]riteMemory/.test(route),
    'Vita must never write to memory directly',
  );
  assert.ok(
    /buildOraConversationHref\(\{ entryPoint: 'vita' \}\)/.test(route),
    'updating a life opens a conversation, not a taxonomy form',
  );
  assert.ok(
    /buildOraConversationHref\(\{ entryPoint: 'vita' \}\)/.test(readCode(DETAIL)),
    'the detail surface must offer the same governed correction path',
  );
  assert.ok(
    !/PATCH/.test(readCode(DETAIL)),
    'the detail surface is presentation only',
  );
}

// ---------------------------------------------------------------------------
// J — Composition and states
// ---------------------------------------------------------------------------
{
  const route = read(ROUTE);
  const rail = Number(/const RAIL_WIDTH = (\d+)/.exec(route)?.[1]);
  const twoCol = Number(/const TWO_COLUMN_MIN = (\d+)/.exec(route)?.[1]);
  assert.ok(rail >= 280 && rail <= 320, `context rail must stay a rail (${rail})`);
  const mainAtMin = twoCol - rail - 24 * 3;
  assert.ok(mainAtMin >= 700, `main area too narrow at the two-column threshold (${mainAtMin})`);

  for (const state of ['VitaSkeleton', 'ErrorState', 'VitaEmpty', 'contesti-partial']) {
    assert.ok(route.includes(state), `the ${state} state must be reachable`);
  }
  // The panels vanish rather than rendering an empty box.
  const railSrc = read('src/components/vita/VitaRail.tsx');
  for (const guard of ['if (!questions.length) return null', 'if (!updates.length) return null', 'if (!rows.length) return null']) {
    assert.ok(railSrc.includes(guard), `missing empty guard: ${guard}`);
  }
}

console.log('vita15: all assertions passed');
