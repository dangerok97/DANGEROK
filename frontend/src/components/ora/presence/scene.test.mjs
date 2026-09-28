import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPresenceScene } from './scene.js';

const fixtureStars = Array.from({length:394}, (_,i) => ({id:`star_test_${i}`, area:['memory','calendar','people','places','home','documents','finances','calls'][i%8], kind:'node'}));
function harness(options = {}) {
  let next = 0, time = 0;
  const pending = new Map(), listeners = new Map();
  const on = (name, fn) => listeners.set(name, fn);
  const off = name => listeners.delete(name);
  globalThis.window = { devicePixelRatio: 2, addEventListener: on, removeEventListener: off };
  globalThis.document = { hidden: false, addEventListener: on, removeEventListener: off };
  globalThis.requestAnimationFrame = fn => { pending.set(++next, fn); return next; };
  globalThis.cancelAnimationFrame = id => pending.delete(id);
  const gradient = { addColorStop() {} };
  let draws = 0;
  const ctx = new Proxy({ measureText: text => ({ width: text.length * 6 }), createRadialGradient: () => gradient, createLinearGradient: () => gradient,
    arc(...values) { assert.ok(values.every(Number.isFinite), 'projection contains a non-finite coordinate'); }, fillRect() { draws++; } }, { get: (target, key) => target[key] || (() => {}) });
  const selections = [];
  const canvas = { style: {}, getContext: () => ctx, getBoundingClientRect: () => ({ width: 360, height: 240, left: 30, top: 60 }), addEventListener: on, removeEventListener: off };
  const palette = new Proxy({}, { get: () => '170,200,220' });
  const scene = createPresenceScene(canvas, { mode: 'idle', active: true, stars: fixtureStars, ...options }, palette, { onSelect: node => selections.push(node) });
  function frames(n) { for (let i = 0; i < n; i++) { const batch = [...pending]; pending.clear(); time += 16.67; for (const [, fn] of batch) fn(time); } }
  function pointer(event, x, y, type = 'mouse', id = 1) {
    listeners.get(event)({ clientX: x + 30, clientY: y + 60, pointerId: id, pointerType: type, button: 0 });
  }
  return { scene, frames, pending, listeners, pointer, selections, draws: () => draws };
}

test('registration starts with one nucleus and reveals only completed steps', () => {
  const h = harness({ intro: true, reveal: true, stars: [] });
  assert.equal(h.scene.snapshot().visiblePoints, 1);
  h.frames(180);
  assert.equal(h.scene.snapshot().visiblePoints, 1, 'empty registration never exposes the eight navigation hubs');
  assert.equal(h.scene.snapshot().edges, 0);
  const start = { id: 'intro_step_one', area: 'memory', kind: 'node' };
  const name = { id: 'draft_first_name', area: 'memory', kind: 'node' };
  const surname = { id: 'draft_last_name', area: 'memory', kind: 'node' };
  h.scene.update({ stars: [start] }); h.frames(100);
  assert.equal(h.scene.snapshot().visiblePoints, 2, 'the first completed step adds one star');
  h.scene.update({ stars: [start, name] }); h.frames(100);
  assert.equal(h.scene.snapshot().visiblePoints, 3, 'writing a name adds one more');
  h.scene.update({ stars: [start, name, surname] }); h.frames(100);
  assert.equal(h.scene.snapshot().visiblePoints, 4, 'the surname adds one more');
  const example = { id: 'intro_example_home', area: 'home', kind: 'node' };
  h.scene.update({ stars: [start, name, surname, example] }); h.frames(100);
  assert.equal(h.scene.snapshot().visiblePoints, 5, 'finishing the identity step reveals its example');
  assert.equal(h.scene.snapshot().edges, 7, 'only links to unlocked stars exist');
  h.scene.update({ stars: [start, name, surname, { ...example, id: 'intro_example_people', area: 'people' }] }); h.frames(100);
  assert.equal(h.scene.snapshot().visiblePoints, 5, 'changing demo areas replaces the example, rather than accumulating stars');
  assert.equal(h.scene.snapshot().projected.filter(p => p.id === 'intro_example_home').length, 0);
  h.scene.destroy();
});

test('the progressive introduction respects reduced motion; normal ORA still has its navigation hubs', () => {
  const h = harness({ intro: true, reduced: true, stars: [] });
  assert.equal(h.scene.snapshot().visiblePoints, 1);
  assert.equal(h.pending.size, 0);
  h.scene.update({ stars: [{ id: 'draft_first_name', area: 'memory', kind: 'node' }] });
  assert.equal(h.scene.snapshot().visiblePoints, 2);
  h.scene.destroy();
  const ora = harness({ intro: false, stars: [] });
  assert.equal(ora.scene.snapshot().visiblePoints, 8, 'the conversational map retains all navigation hubs');
  ora.scene.destroy();
});

test('opening grows from one central point to the full 3D network, once', () => {
  const h = harness({ reveal: true });
  assert.equal(h.scene.snapshot().visiblePoints, 1);
  assert.equal(h.scene.snapshot().projected[0].x, 180);
  h.frames(65);
  const midway = h.scene.snapshot();
  assert.ok(midway.visiblePoints > 1 && midway.visiblePoints < 402);
  h.frames(120);
  assert.equal(h.scene.snapshot().opening, 1);
  assert.equal(h.scene.snapshot().visiblePoints, 402);
  h.scene.update({ reveal: true, resetKey: 1 });
  assert.equal(h.scene.snapshot().opening, 1, 'updates and centre never replay');
  h.scene.destroy();
});

test('a late first-message trigger restarts at the centre after the mounted map has moved', () => {
  const h = harness({ mode: 'think', area: 'calendar' });
  h.frames(180);
  assert.notEqual(h.scene.snapshot().camera.x, 0);
  h.scene.update({ revealKey: 'first-message' });
  assert.equal(h.scene.snapshot().visiblePoints, 1);
  assert.equal(h.scene.snapshot().projected[0].x, 180);
  assert.equal(h.scene.snapshot().camera.zoom, 1);
  h.frames(65);
  assert.ok(h.scene.snapshot().visiblePoints > 1 && h.scene.snapshot().visiblePoints < 402);
  h.scene.update({ mode: 'speak', revealKey: 'first-message' });
  h.frames(120);
  assert.equal(h.scene.snapshot().opening, 1);
  h.scene.update({ revealKey: 'first-message' });
  assert.equal(h.scene.snapshot().opening, 1);
  h.scene.destroy();
});

test('a Home handoff starts with a point on its very first canvas frame', () => {
  const h = harness({ revealKey: 'home-session' });
  assert.equal(h.scene.snapshot().visiblePoints, 1);
  assert.equal(h.scene.snapshot().opening, 0);
  h.frames(180);
  assert.equal(h.scene.snapshot().visiblePoints, 402);
  h.scene.destroy();
});

test('opening respects background, reduced motion and immediate interaction', () => {
  const h = harness({ reveal: true, active: false });
  h.frames(200);
  assert.equal(h.scene.snapshot().opening, 0);
  h.scene.update({ active: true }); h.frames(5);
  assert.ok(h.scene.snapshot().opening > 0);
  h.pointer('pointerdown', 180, 120, 'touch');
  assert.equal(h.scene.snapshot().visiblePoints, 402);
  h.scene.destroy();
  const quiet = harness({ reveal: true, reduced: true });
  assert.equal(quiet.scene.snapshot().opening, 1);
  assert.equal(quiet.pending.size, 0);
  quiet.scene.destroy();
  const work = harness({ reveal: true });
  work.scene.update({ mode: 'think', area: 'calendar' });
  assert.equal(work.scene.snapshot().opening, 0, 'the first working turn can unfold while the request runs');
  work.frames(180);
  assert.equal(work.scene.snapshot().opening, 1);
  work.scene.update({ revealKey: 'second-session' });
  assert.equal(work.scene.snapshot().opening, 0);
  work.frames(180);
  work.scene.update({ revealKey: 'second-session' });
  assert.equal(work.scene.snapshot().opening, 1);
  work.scene.destroy();
});

test('camera approaches the real selected area smoothly and returns to standby', () => {
  const h = harness();
  assert.equal(h.scene.snapshot().points, 402);
  assert.equal(h.scene.snapshot().camera.zoom, 1);
  h.scene.update({ mode: 'think', area: 'documents' });
  assert.equal(h.scene.snapshot().camera.zoom, 1, 'focus must not jump');
  h.frames(120);
  assert.equal(h.scene.snapshot().activeHub, 5);
  assert.ok(h.scene.snapshot().camera.zoom > 1.6);
  assert.ok(h.scene.snapshot().camera.x > .6);
  h.scene.update({ mode: 'idle', area: null }); h.frames(150);
  assert.equal(h.scene.snapshot().activeHub, -1);
  assert.ok(Math.abs(h.scene.snapshot().camera.zoom - 1) < .001);
  h.scene.destroy();
});
test('a fast completed reply can focus each topic in idle, then release it', () => {
  const h = harness();
  const areas = ['memory', 'calendar', 'people', 'places', 'home', 'documents', 'finances', 'calls'];
  for (const [index, area] of areas.entries()) {
    h.scene.update({ mode: 'idle', area }); h.frames(120);
    assert.equal(h.scene.snapshot().activeHub, index);
    assert.ok(h.scene.snapshot().camera.zoom > 1.6);
  }
  h.scene.update({ area: null }); h.frames(150);
  assert.equal(h.scene.snapshot().activeHub, -1);
  assert.ok(Math.abs(h.scene.snapshot().camera.zoom - 1) < .001);
  h.scene.destroy();
});
test('pause, background, reduced motion and destruction stop animation scheduling', () => {
  const h = harness();
  for (const option of ['paused', 'reduced']) {
    h.scene.update({ [option]: true });
    assert.equal(h.pending.size, 0);
    h.scene.update({ [option]: false }); assert.equal(h.pending.size, 1);
  }
  h.scene.update({ active: false }); assert.equal(h.pending.size, 0);
  h.scene.update({ active: true });
  document.hidden = true; h.listeners.get('visibilitychange')(); assert.equal(h.pending.size, 0);
  document.hidden = false; h.listeners.get('visibilitychange')(); assert.equal(h.pending.size, 1);
  h.scene.destroy(); assert.equal(h.pending.size, 0); assert.equal(h.listeners.size, 0);
});
test('unknown activity never selects an invented region and static mode still conveys focus', () => {
  const h = harness();
  h.scene.update({ mode: 'think', area: 'unknown', reduced: true });
  assert.equal(h.scene.snapshot().activeHub, -1);
  h.scene.update({ area: 'calendar' });
  assert.equal(h.scene.snapshot().activeHub, 1);
  assert.equal(h.pending.size, 0);
  h.scene.destroy();
});

test('mouse drag rotates on both axes while pause keeps animation unscheduled', () => {
  const h = harness(); h.scene.update({ paused: true });
  const before = h.scene.snapshot();
  h.pointer('pointerdown', 150, 120); h.pointer('pointermove', 195, 150); h.pointer('pointerup', 195, 150);
  const after = h.scene.snapshot();
  assert.ok(after.rotation.yaw > before.rotation.yaw);
  assert.ok(after.rotation.pitch > before.rotation.pitch);
  assert.notDeepEqual(after.projected[0], before.projected[0]);
  assert.equal(h.pending.size, 0); assert.equal(h.selections.length, 0, 'a drag must not open a node');
  h.scene.update({ resetKey: 1 });
  assert.deepEqual(h.scene.snapshot().rotation, { yaw: 0, pitch: 0 });
  h.scene.destroy();
});
test('hover and touch light a projected node; click reports its domain at CSS coordinates', () => {
  for (const type of ['mouse', 'touch']) {
    const h = harness(); h.scene.update({ paused: true });
    const point = h.scene.snapshot().projected[2];
    h.pointer('pointermove', point.x, point.y, type);
    assert.equal(h.scene.snapshot().hovered, point.index);
    h.pointer('pointerdown', point.x, point.y, type);
    h.pointer('pointerup', point.x, point.y, type);
    assert.deepEqual(h.selections[0], { index: point.index, area: point.area, kind: point.kind });
    assert.equal(h.scene.snapshot().selected, point.index);
    if (type === 'touch') assert.equal(h.scene.snapshot().hovered, -1);
    h.pointer('pointerleave', 0, 0, type); assert.equal(h.scene.snapshot().hovered, -1);
    h.scene.destroy();
  }
});
test('touch can rotate in reduced motion and cancelled/multiple pointers never select', () => {
  const h = harness(); h.scene.update({ reduced: true });
  h.pointer('pointerdown', 140, 100, 'touch');
  h.pointer('pointerdown', 180, 90, 'touch', 2);
  h.pointer('pointermove', 200, 100, 'touch', 2);
  assert.deepEqual(h.scene.snapshot().rotation, { yaw: 0, pitch: 0 });
  h.pointer('pointerup', 200, 100, 'touch', 2);
  h.pointer('pointermove', 170, 130, 'touch');
  assert.ok(h.scene.snapshot().rotation.yaw > 0);
  h.pointer('pointercancel', 170, 130, 'touch');
  h.pointer('pointerup', 170, 130, 'touch');
  assert.equal(h.pending.size, 0); assert.equal(h.selections.length, 0);
  h.scene.destroy();
});
test('inspection holds the selected node still until details close, without losing work focus', () => {
  const h = harness(); h.scene.update({ mode: 'think', area: 'calendar' }); h.frames(60);
  h.scene.update({ selectedIndex: 2 });
  const held = h.scene.snapshot(); h.frames(30);
  assert.deepEqual(h.scene.snapshot().projected[2], held.projected[2]);
  assert.equal(h.scene.snapshot().activeHub, 1);
  h.scene.update({ selectedIndex: null }); h.frames(30);
  assert.notDeepEqual(h.scene.snapshot().projected[2], held.projected[2]);
  h.scene.destroy();
});

test('dialogue framing moves the drawn map and keeps node hit targets aligned', () => {
  const h = harness(); h.scene.update({ paused: true });
  const before = h.scene.snapshot().projected[2];
  h.scene.update({ centerY: .4 });
  const after = h.scene.snapshot().projected[2];
  assert.equal(after.x, before.x); assert.ok(after.y < before.y);
  h.pointer('pointerdown', after.x, after.y, 'touch'); h.pointer('pointerup', after.x, after.y, 'touch');
  assert.equal(h.selections[0]?.area, 'people');
  h.scene.destroy();
});


test('empty accounts contain no invented knowledge and additions grow without replaying the session', () => {
  const h = harness({ stars: [] });
  assert.equal(h.scene.snapshot().knowledgeStars, 0);
  const first = { id: 'star_first', area: 'memory', kind: 'node' };
  h.scene.update({ stars: [first] });
  assert.equal(h.scene.snapshot().knowledgeStars, 1);
  assert.equal(h.scene.snapshot().opening, 1);
  const born = h.scene.snapshot().projected.find(p => p.id === first.id);
  h.frames(120);
  const grown = h.scene.snapshot().projected.find(p => p.id === first.id);
  assert.notDeepEqual(born, grown);
  h.scene.update({ stars: [first, {id:'star_second', area:'home', kind:'node'}] });
  assert.equal(h.scene.snapshot().knowledgeStars, 2);
  assert.equal(h.scene.snapshot().opening, 1);
  h.scene.update({ stars: [first], paused: true });
  assert.equal(h.scene.snapshot().knowledgeStars, 1, 'forgotten information leaves the scene');
  assert.equal(h.pending.size, 0);
  h.scene.destroy();
});

test('knowledge selections identify the exact saved fact, including on touch', () => {
  const h = harness({ stars: [{id:'star_exact',area:'home',kind:'node'}], reduced: true });
  const p = h.scene.snapshot().projected.find(p => p.id === 'star_exact');
  h.pointer('pointerdown', p.x, p.y, 'touch'); h.pointer('pointerup', p.x, p.y, 'touch');
  assert.equal(h.selections[0]?.id, 'star_exact');
  assert.equal(h.selections[0]?.kind, 'node');
  h.scene.destroy();
});
