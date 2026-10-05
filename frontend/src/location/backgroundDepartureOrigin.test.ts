import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');

const runtime = readFileSync(resolve(FRONTEND, 'src/location/presenceRuntime.ts'), 'utf8');
const client = readFileSync(resolve(FRONTEND, 'src/api/client.ts'), 'utf8');

assert.ok(
  runtime.includes("entry.source === 'foreground' ? 'foreground_device' : 'background_device'"),
  'il buffer nativo deve conservare la provenienza foreground/background',
);
assert.ok(
  client.includes("source?: 'foreground_device' | 'background_device'"),
  'il contratto API deve trasportare la provenienza del fix',
);
assert.ok(
  runtime.includes('event_id: entry.event_id'),
  'la provenienza non deve rompere l idempotenza delle osservazioni native',
);

console.log('Background departure provenance guards: tutte le asserzioni passate');
