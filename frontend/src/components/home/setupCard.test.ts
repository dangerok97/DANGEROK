import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// The card's rule, kept in sync with SetupCard.tsx (no React in node tests).
const src = readFileSync(new URL('./SetupCard.tsx', import.meta.url), 'utf8');
assert.match(src, /return !!st && !st\.done && !st\.dismissed;/);
const guide = readFileSync(new URL('../../../app/inizia.tsx', import.meta.url), 'utf8');
for (const id of ['setup-push', 'setup-location', 'setup-home-input', 'setup-mode-${m.id}', 'setup-brief', 'setup-done'])
  assert.ok(guide.includes(id), `missing ${id}`);
assert.ok(guide.includes("pathname: '/ora', params: { draft: p }"));
const client = readFileSync(new URL('../../api/client.ts', import.meta.url), 'utf8');
for (const path of ["'/brief/setup'", "'/brief/setup/dismiss'", "'/brief/travel-mode'"])
  assert.ok(client.includes(path), path);
const home = readFileSync(new URL('../../../app/(tabs)/index.tsx', import.meta.url), 'utf8');
assert.ok(home.includes('<SetupCard />'));
console.log('setupCard ok');
