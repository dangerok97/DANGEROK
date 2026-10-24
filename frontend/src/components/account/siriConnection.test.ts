/**
 * The shortcut steps must name exactly what the backend reads:
 * POST, the Authorization header, a JSON field called `text`,
 * and the optional latitude / longitude.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '../../..');
const SRC = readFileSync(path.join(ROOT, 'src/components/account/SiriConnection.tsx'), 'utf-8');
const SETTINGS = readFileSync(path.join(ROOT, 'app/settings.tsx'), 'utf-8');
const BACKEND = readFileSync(path.join(ROOT, '../backend/siri/router.py'), 'utf-8');

test('steps describe the request the backend expects', () => {
  for (const word of ['POST', 'Authorization', 'chiave text', 'JSON', 'latitude', 'longitude', 'Mostra risultato']) {
    assert.ok(SRC.includes(word), `missing ${word}`);
  }
  assert.ok(SRC.includes('`Bearer ${key}`'));
  assert.ok(BACKEND.includes('@router.post("/ask")'));
  assert.ok(BACKEND.includes('body.get("text")'));
  assert.ok(BACKEND.includes('"latitude"'));
});

test('Siri lives in Connessioni e servizi next to WhatsApp', () => {
  assert.ok(SETTINGS.includes('<SiriConnection />'));
});

test('the key is never kept beyond the screen that showed it', () => {
  assert.ok(!/localStorage|SecureStore|AsyncStorage/.test(SRC));
});
