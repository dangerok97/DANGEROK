import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');

const editor = read('src/components/vita/PlaceEditor.tsx');
const client = read('src/api/client.ts');

assert.ok(
  editor.includes('openMapAtCurrentPosition'),
  'Scegli sulla mappa deve avere un percorso dedicato che parte dalla posizione corrente',
);
assert.ok(
  editor.includes("requestCurrentPosition"),
  'il picker deve usare la geolocalizzazione corrente cross-platform',
);
assert.ok(
  editor.includes('onPress={() => void openMapAtCurrentPosition()}'),
  'il bottone mappa deve aprire dal GPS e non dal fallback Roma',
);
assert.ok(
  editor.includes("setSource('map_selection')") && editor.includes('setFromCurrentPosition(false)'),
  'il GPS deve centrare la vista senza trasformare la scelta mappa in una dichiarazione Sono qui',
);
assert.ok(
  editor.includes('if (!res.available)'),
  'l autocomplete deve distinguere provider indisponibile da zero risultati',
);
assert.ok(
  editor.includes('Ricerca indirizzi non disponibile'),
  'la UI deve spiegare un errore Places invece di sembrare vuota',
);
assert.ok(
  client.includes('why_unavailable?: string'),
  'il client deve trasportare il motivo di indisponibilità Places',
);

console.log('Luoghi GPS + address lookup guards: tutte le asserzioni passate');
