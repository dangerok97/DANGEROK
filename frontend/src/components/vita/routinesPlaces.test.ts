import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');

const section = read('src/components/vita/PlacesSection.tsx');
const client = read('src/api/client.ts');

assert.ok(section.includes('ORA ha notato'), 'Luoghi deve rendere visibili le routine apprese');
assert.ok(
  section.includes('Sono ipotesi, non regole.'),
  'la UI deve dichiarare che una routine appresa non è una verità imposta',
);
assert.ok(
  section.includes('È corretto') && section.includes('Non è così'),
  'l’utente deve poter confermare o rifiutare una routine',
);
assert.ok(
  section.includes('placesSetRoutineState'),
  'le azioni della UI devono raggiungere il backend',
);
assert.ok(
  client.includes("state: 'candidate' | 'accepted' | 'stale'"),
  'il client deve distinguere routine candidate e confermate',
);
assert.ok(
  client.includes("state: 'accepted' | 'dismissed'"),
  'il client deve poter inviare un verdetto esplicito',
);

console.log('Routine Places guards: tutte le asserzioni passate');
