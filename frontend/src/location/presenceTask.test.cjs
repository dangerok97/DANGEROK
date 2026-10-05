const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

function harness(position, enabled = true, freshPosition = null) {
  const tasks = {};
  const saved = [];
  let deliveries = 0;
  const location = {
    GeofencingEventType: { Enter: 1, Exit: 2 },
    Accuracy: { Balanced: 3 },
    getLastKnownPositionAsync: async () => position,
    getCurrentPositionAsync: async () => freshPosition,
  };
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(__dirname + '/presenceTask.ts', 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, {
    module, exports: module.exports, require: name => {
      if (name === 'expo-location') return location;
      if (name === 'expo-task-manager') return { defineTask: (key, fn) => { tasks[key] = fn; } };
      if (name === './presenceBuffer') return { remember: async entry => saved.push(entry) };
      if (name === './presenceRuntime') return {
        isEnabled: async () => enabled,
        sendPending: async () => { deliveries++; },
      };
      throw new Error(name);
  }, Date, Math, Promise, Object, Symbol, setTimeout, clearTimeout,
  });
  return { tasks, saved, get deliveries() { return deliveries; } };
}

const region = { latitude: 41.9, longitude: 12.5, radius: 120 };
const outside = { timestamp: Date.now(), coords: { latitude: 41.905, longitude: 12.5, accuracy: 15 } };
const inside = { timestamp: Date.now(), coords: { latitude: 41.9, longitude: 12.5, accuracy: 15 } };

test('exit callback never sends the region centre as a location fix', async () => {
  const h = harness(inside);
  await h.tasks['ora-presence-geofence']({ data: { region, eventType: 2 } });
  assert.equal(h.saved.length, 0);
  assert.equal(h.deliveries, 0);
});

test('an exit with a recent fix outside is buffered and delivered while in background', async () => {
  const h = harness(outside);
  await h.tasks['ora-presence-geofence']({ data: { region, eventType: 2 } });
  assert.equal(h.saved.length, 1);
  assert.equal(h.saved[0].latitude, outside.coords.latitude);
  assert.equal(h.saved[0].source, 'geofence_exit');
  assert.equal(h.deliveries, 1);
});

test('background location fixes are delivered without reopening ORA', async () => {
  const h = harness(null);
  await h.tasks['ora-presence-location']({ data: { locations: [outside] } });
  assert.equal(h.saved.length, 1);
  assert.equal(h.deliveries, 1);
});

test('revoked monitoring ignores late callbacks without buffering coordinates', async () => {
  const h = harness(outside, false);
  await h.tasks['ora-presence-location']({ data: { locations: [outside] } });
  await h.tasks['ora-presence-geofence']({ data: { region, eventType: 2 } });
  assert.equal(h.saved.length, 0);
  assert.equal(h.deliveries, 0);
});

test('geofence wake requests a measured fix when no recent fix exists', async () => {
  const h = harness(null, true, outside);
  await h.tasks['ora-presence-geofence']({ data: { region, eventType: 2 } });
  assert.equal(h.saved.length, 1);
  assert.equal(h.saved[0].longitude, outside.coords.longitude);
});


test('native reconciliation revokes server monitoring when OS background permission is gone', () => {
  const runtime = fs.readFileSync(__dirname + '/presenceRuntime.ts', 'utf8');
  const client = fs.readFileSync(__dirname + '/../api/client.ts', 'utf8');

  assert.match(runtime, /actual\.background !== 'granted'/);
  assert.match(runtime, /await disable\(\)/);
  assert.match(runtime, /locationSetPreference\('while_using'\)/);
  assert.match(runtime, /placesSetMonitoring\(false\)\.catch/);
  assert.match(client, /location\/preference\?platform=/);
});
