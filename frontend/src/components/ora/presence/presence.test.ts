import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { readPresenceActivity, presenceMode } from './state.ts';
import { sceneSource } from './sceneSource.ts';
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
test('native embeds the exact renderer, independent of Metro helper closures', () => {
  assert.equal(sceneSource, readFileSync(new URL('./scene.js', import.meta.url), 'utf8').replace('export function createPresenceScene', 'function createPresenceScene'));
  assert.equal(typeof new Function(`${sceneSource}; return createPresenceScene;`)(), 'function');
});
