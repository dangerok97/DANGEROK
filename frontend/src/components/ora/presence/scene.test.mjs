import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPresenceScene } from './scene.js';

function harness() {
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
  const scene = createPresenceScene(canvas, { mode: 'idle', active: true }, palette, { onSelect: node => selections.push(node) });
  function frames(n) { for (let i = 0; i < n; i++) { const batch = [...pending]; pending.clear(); time += 16.67; for (const [, fn] of batch) fn(time); } }
  function pointer(event, x, y, type = 'mouse', id = 1) {
    listeners.get(event)({ clientX: x + 30, clientY: y + 60, pointerId: id, pointerType: type, button: 0 });
  }
  return { scene, frames, pending, listeners, pointer, selections, draws: () => draws };
}

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
  h.scene.update({ mode: 'idle' }); h.frames(150);
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
