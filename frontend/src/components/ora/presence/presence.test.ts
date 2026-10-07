import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { readPresenceActivity, presenceMode, readPresenceNode, AREA_IDS, AREA_DETAILS, completionFocusKey, presenceFocus } from './state.ts';
import { sceneSource } from './sceneSource.ts';
import { changedStars, geometryFor } from './knowledge.ts';
const now = Date.now();
const activity = { request_id: 'turn-a', sequence: 2, phase: 'tool', area: 'calendar', touched: ['memory', 'calendar'], updated_at: now / 1000 };
test('first turn focus requires a matching, fresh real signal', () => {
  assert.equal(readPresenceActivity(activity, 'turn-a', null, now)?.area, 'calendar');
  assert.equal(readPresenceActivity(activity, 'turn-b', null, now), null);
  assert.equal(readPresenceActivity(activity, 'turn-a', null, now + 121000), null);
  assert.equal(readPresenceActivity(null, 'turn-a'), null);
  assert.equal(readPresenceActivity({ ...activity, updated_at: NaN }, 'turn-a'), null);
});
test('late polling cannot roll back a newer area; unknown areas stay generic', () => {
  const current = readPresenceActivity({ ...activity, sequence: 5, area: 'documents' }, 'turn-a', null, now);
  assert.equal(readPresenceActivity(activity, 'turn-a', current, now)?.area, 'documents');
  assert.equal(readPresenceActivity({ ...activity, area: 'calendar from user prose' }, 'turn-a', null, now)?.area, null);
});
test('listening, processing, actual speech and idle are distinct states', () => {
  assert.equal(presenceMode(false), 'idle');
  assert.equal(presenceMode(true), 'think');
  assert.equal(presenceMode(true, 'listening'), 'listen');
  assert.equal(presenceMode(false, 'preparing'), 'think');
  assert.equal(presenceMode(false, 'speaking'), 'speak');
  assert.equal(presenceMode(false, 'blocked'), 'idle');
});
test('completed focus remains visible until expiry, then releases; new turns do not inherit it', () => {
  for (const area of AREA_IDS) {
    const done = readPresenceActivity({ ...activity, phase: 'done', area, basis: 'topic' }, 'turn-a', null, now)!;
    const key = completionFocusKey(done);
    assert.equal(presenceFocus(done, 'idle', null), area);
    assert.equal(presenceFocus(done, 'idle', key), null);
    assert.equal(presenceFocus(done, 'speak', key), area, 'speech retains focus even after the visual hold');
    assert.equal(presenceFocus(done, 'listen', null), null);
    assert.equal(presenceFocus({ ...done, phase: 'error' }, 'think', null), null);
    const next = { ...done, request_id: 'turn-b' };
    assert.equal(presenceFocus(next, 'idle', key), area, 'same topic in another turn gets a fresh hold');
    assert.equal(presenceFocus({ ...next, phase: 'processing', area: null }, 'think', key), null);
    assert.equal(done.basis, 'topic');
  }
  assert.equal(presenceFocus(null, 'think', null), null);
  assert.equal(readPresenceActivity({ ...activity, basis: 'secret source' }, 'turn-a', null, now)?.basis, null);
});
test('native embeds the exact renderer, independent of Metro helper closures', () => {
  assert.equal(sceneSource, readFileSync(new URL('./scene.js', import.meta.url), 'utf8').replace('export function createPresenceScene', 'function createPresenceScene'));
  assert.equal(typeof new Function(`${sceneSource}; return createPresenceScene;`)(), 'function');
});

test('selection bridge accepts only a known node identity and drops arbitrary content', () => {
  for (let i = 0; i < 8; i++) {
    const area = AREA_IDS[i];
    assert.deepEqual(readPresenceNode({ index: i, area, kind: 'area', secret: 'ignored' }), { index: i, area, kind: 'area' });
    const geometry = [{ id: `star_${i}`, area, kind: 'node' }];
    assert.equal(readPresenceNode({ index: 8, id: `star_${i}`, area, kind: 'node' }, geometry)?.area, area);
    assert.equal(readPresenceNode({ index: 8, id: 'forged', area, kind: 'node' }, geometry), null);
    assert.ok(AREA_DETAILS[area].description && AREA_DETAILS[area].prompt);
  }
  for (const invalid of [null, {}, {index: 402, area: 'home', kind: 'node'}, {index: 0, area: 'home', kind: 'area'}, {index: 0, area: 'memory', kind: 'node'}, {index: 9.5, area: 'memory', kind: 'node'}, {index: 0, area: 'constructor', kind: 'area'}]) assert.equal(readPresenceNode(invalid), null);
});


test('temporary memory becomes red-star geometry without changing durable semantics', () => {
  const geometry = geometryFor({
    stars: [{
      id: 'star_temp',
      area: 'memory',
      branch_id: null,
      title: 'Memoria temporanea',
      statement: 'Situazione momentanea',
      status: 'known',
      provenance: 'Situazione attiva',
      temporary: true,
      situation_id: 'sit_1',
    }],
    count: 1,
    known_count: 1,
    temporary_count: 1,
    percent: 0,
    branches: [],
    revision: 'r1',
  });
  assert.equal(geometry[0]?.temporary, true);
  assert.equal(geometry[0]?.tentative, false);
  assert.ok(sceneSource.includes('temporary?palette.temporaryNode'));
  assert.ok(sceneSource.includes('temporary?palette.temporaryGlow'));
  assert.ok(sceneSource.includes("const inspected=hovered>=0?hovered:selected>=0?selected:spotlight"));
  assert.ok(sceneSource.includes("i===spotlight?.82"));
  assert.ok(sceneSource.includes("const label='NUOVA'"));
  assert.ok(sceneSource.includes('options.zoomOverride'), 'cockpit zoom controls must affect the real camera');
});


test('new and materially updated permanent stars both become spotlight candidates', () => {
  const base = {
    stars: [{
      id: 'star_birthdays',
      area: 'people',
      branch_id: null,
      title: 'Compleanni',
      statement: '1 compleanno salvato',
      status: 'known' as const,
      provenance: 'Salvati in memoria',
      updated_at: '2026-10-07T20:00:00Z',
      source_refs: ['mem_elena'],
      group_kind: 'birthdays',
      group_items: [{ memory_ref: 'mem_elena', label: 'Elena', date_label: '8 ottobre' }],
    }],
    count: 1, known_count: 1, temporary_count: 0, percent: 0, branches: [], revision: 'a',
  };
  const grown = {
    ...base,
    stars: [{
      ...base.stars[0],
      statement: '2 compleanni salvati',
      updated_at: '2026-10-07T20:01:00Z',
      source_refs: ['mem_elena', 'mem_marco'],
      group_items: [
        { memory_ref: 'mem_elena', label: 'Elena', date_label: '8 ottobre' },
        { memory_ref: 'mem_marco', label: 'Marco', date_label: '4 agosto' },
      ],
    }],
    revision: 'b',
  };
  assert.deepEqual(changedStars(base, grown).map(star => star.id), ['star_birthdays']);

  const born = {
    ...grown,
    stars: [...grown.stars, {
      id: 'star_other',
      area: 'memory',
      branch_id: null,
      title: 'Ricordo',
      statement: 'Nuovo ricordo',
      status: 'known' as const,
      provenance: 'Salvato in memoria',
      updated_at: '2026-10-07T20:02:00Z',
      source_refs: ['mem_other'],
    }],
    count: 2,
    revision: 'c',
  };
  assert.deepEqual(changedStars(grown, born).map(star => star.id), ['star_other']);
});

test('spotlight drives both glow and camera target', () => {
  assert.ok(sceneSource.includes("const focused=points.find(p=>p.id===options.spotlightId)"));
  assert.ok(sceneSource.includes("const target=focused||"));
  assert.ok(sceneSource.includes("i===spotlight?.82"));
});
