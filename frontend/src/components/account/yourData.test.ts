import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('./YourData.tsx', import.meta.url), 'utf8');
// Deletion asks for the exact word and is wired to the real endpoint.
assert.match(src, /DELETE_WORD = 'ELIMINA'/);
assert.match(src, /api\.deleteMyAccount/);
assert.match(src, /disabled=\{!canConfirmDeletion\(word\) \|\| !!busy\}/);
assert.match(src, /api\.exportMyData/);
const client = readFileSync(new URL('../../api/client.ts', import.meta.url), 'utf8');
assert.match(client, /\/auth\/account\/delete/);
assert.match(client, /\/api\/auth\/account\/export/);
const privacy = readFileSync(new URL('../../../app/privacy.tsx', import.meta.url), 'utf8');
assert.match(privacy, /I tuoi dati puoi eliminare l’account/);
assert.doesNotMatch(privacy, /richiedere la gestione o cancellazione dei dati attraverso i canali di assistenza/);
console.log('Your data: PASS');
