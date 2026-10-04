import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const loginSource = fs.readFileSync(path.join(here, '../../app/login.tsx'), 'utf8');
const providerSource = fs.readFileSync(path.join(here, 'providersConfig.ts'), 'utf8');

test('Apple login requires backend configuration before becoming actionable', () => {
  assert.match(providerSource, /backendConfigured !== true/);
  assert.match(providerSource, /platform === 'ios'/);
  assert.match(providerSource, /return nativeAvailable/);
  assert.match(loginSource, /appleProviderReady\(/);
  assert.match(loginSource, /disabled=\{anyBusy \|\| !appleReady\}/);
});

test('Apple login remains visible with honest unavailable copy', () => {
  assert.match(loginSource, /Continua con Apple/);
  assert.match(loginSource, /Accesso Apple non configurato in questo ambiente/);
});
