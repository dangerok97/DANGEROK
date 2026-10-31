import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// The card's rule, kept in sync with SetupCard.tsx (no React in node tests).
const src = readFileSync(new URL('./SetupCard.tsx', import.meta.url), 'utf8');
assert.match(src, /return !!st && !st\.done && !st\.dismissed;/);
const guide = readFileSync(new URL('../../../app/inizia.tsx', import.meta.url), 'utf8');
for (const id of ['setup-push', 'setup-location', 'setup-home-input', 'setup-home-gps', 'setup-mode-${m.id}', 'setup-brief-${h}', 'setup-brief-off', 'setup-done'])
  assert.ok(guide.includes(id), `missing ${id}`);
assert.ok(guide.includes("location_source: 'current_position'") && guide.includes("role: 'home'"));
assert.ok(guide.includes('ORE_BRIEF = [6, 7, 8, 9, 10, 11]'));
assert.ok(!guide.includes('Va bene alle 8'));
assert.ok(guide.includes('MAX_HOME_ACCURACY_M = 150'));
assert.ok(guide.includes("pathname: '/ora', params: { draft: p }"));
const client = readFileSync(new URL('../../api/client.ts', import.meta.url), 'utf8');
for (const path of ["'/brief/setup'", "'/brief/setup/dismiss'", "'/brief/travel-mode'"])
  assert.ok(client.includes(path), path);
const home = readFileSync(new URL('../../../app/(tabs)/index.tsx', import.meta.url), 'utf8');
assert.ok(home.includes('<SetupCard />'));
console.log('setupCard ok');
