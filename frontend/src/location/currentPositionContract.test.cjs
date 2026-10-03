const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function read(relative) {
  return fs.readFileSync(path.join(__dirname, relative), 'utf8');
}

test('current device location has a native acquisition path', () => {
  const source = read('foregroundGeo.ts');
  assert.match(source, /export async function requestCurrentPosition/);
  assert.match(source, /Platform\.OS !== 'ios' && Platform\.OS !== 'android'/);
  assert.match(source, /await import\('expo-location'\)/);
  assert.match(source, /getForegroundPermissionsAsync/);
  assert.match(source, /getCurrentPositionAsync/);
});

test('ORA client capability uses cross-platform current position, not web-only helper', () => {
  const screen = read('../components/ora/OraConversationScreen.tsx');
  assert.match(screen, /requestCurrentPosition\(/);
  const runGeo = screen.slice(screen.indexOf('const runGeo'), screen.indexOf('const postSignal'));
  assert.match(runGeo, /requestCurrentPosition/);
  assert.doesNotMatch(runGeo, /requestForegroundPosition/);
});

test('departure and conversational location share one native-capable acquisition', () => {
  const source = read('foregroundGeo.ts');
  const departure = source.slice(source.indexOf('export async function requestDeparturePosition'));
  assert.match(departure, /return requestCurrentPosition/);
});
