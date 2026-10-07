import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');

const gate = read('src/shell/AuthGate.tsx');
assert.ok(gate.includes("'/privacy'"), 'privacy must remain public');
assert.ok(gate.includes("'/terms'"), 'terms must remain public');

for (const [route, expected] of [
  ['app/privacy.tsx', 'Informativa sulla privacy'],
  ['app/terms.tsx', 'Termini di servizio'],
] as const) {
  const src = read(route);
  assert.ok(src.includes(expected), `${route} must expose its legal title`);
  assert.ok(src.includes('PublicLegalPage'), `${route} must use the public legal surface`);
}

const privacy = read('app/privacy.tsx');
assert.ok(privacy.includes('Google Calendar'));
assert.ok(privacy.includes('Gmail'));
assert.ok(privacy.includes('Posizione del dispositivo'));
assert.ok(privacy.includes('Servizi bancari collegati'));

console.log('Public legal pages: PASS');
