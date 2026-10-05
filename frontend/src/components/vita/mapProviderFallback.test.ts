import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const picker = readFileSync(resolve(FRONTEND, 'src/components/vita/MapPicker.tsx'), 'utf8');

assert.ok(
  picker.includes("mapsStatus().available"),
  'Google Maps deve restare il provider preferito quando configurato',
);
assert.ok(
  picker.includes('loadLeaflet'),
  'MapPicker deve avere un fallback cartografico senza chiave Google',
);
assert.ok(
  picker.includes('https://tile.openstreetmap.org/{z}/{x}/{y}.png'),
  'il fallback deve usare tile OpenStreetMap reali',
);
assert.ok(
  picker.includes("provider.current = 'leaflet'"),
  'il runtime deve distinguere il provider fallback',
);
assert.ok(
  !picker.includes("'La mappa non è configurata su questa installazione.'"),
  'assenza della chiave Google non deve più disabilitare la mappa',
);
assert.ok(
  picker.includes('invalidateSize'),
  'anche il fallback deve reagire ai resize dell’editor',
);

console.log('Map provider fallback guards: tutte le asserzioni passate');
