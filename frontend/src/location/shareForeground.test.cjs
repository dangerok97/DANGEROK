const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

function load(fix) {
  const calls = [];
  const api = {
    locationSetPreference: async mode => calls.push(['preference', mode]),
    locationPostSignal: async body => calls.push(['signal', body]),
    locationPermissionOutcome: async reason => calls.push(['outcome', reason]),
    locationGetPreference: async () => ({ mode: 'off' }),
  };
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(__dirname + '/shareForeground.ts', 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, Date, Error, require: name => {
    if (name.includes('api/client')) return { api };
    return { requestForegroundPosition: async () => { calls.push(['request']); return fix; } };
  }});
  return { module: exports, calls, api };
}

test('permission request precedes consent and posts the actual device fix', async () => {
  const { module, calls } = load({ ok: true, latitude: 41.89, longitude: 12.49, accuracyMeters: 40 });
  await module.shareForegroundPosition();
  assert.deepEqual(calls.map(c => c[0]), ['request', 'preference', 'signal']);
  assert.equal(calls[2][1].latitude, 41.89);
  assert.equal(calls[2][1].reverse_geocode, true);
});

test('denied permission never enables ORA location or posts invented coordinates', async () => {
  const { module, calls } = load({ ok: false, reason: 'denied' });
  await assert.rejects(module.shareForegroundPosition(), /impostazioni del sito/);
  assert.deepEqual(calls.map(c => c[0]), ['request', 'outcome']);
});

test('a timeout has its own recovery message', async () => {
  const { module, calls } = load({ ok: false, reason: 'timeout' });
  await assert.rejects(module.shareForegroundPosition(), /non ha risposto in tempo/);
  assert.equal(calls[1][1], 'timeout');
});

test('Home does not request device permission without existing ORA consent', async () => {
  const { module, calls } = load({ ok: true });
  assert.equal(await module.refreshConsentedPosition(), false);
  assert.equal(calls.length, 0);
});
