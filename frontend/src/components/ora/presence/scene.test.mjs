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
  const canvas = { getContext: () => ctx, getBoundingClientRect: () => ({ width: 360, height: 240 }), addEventListener: on, removeEventListener: off };
  const palette = new Proxy({}, { get: () => '170,200,220' });
  const scene = createPresenceScene(canvas, { mode: 'idle', active: true }, palette);
  function frames(n) { for (let i = 0; i < n; i++) { const batch = [...pending]; pending.clear(); time += 16.67; for (const [, fn] of batch) fn(time); } }
  return { scene, frames, pending, listeners, draws: () => draws };
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
