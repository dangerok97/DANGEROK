import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');

const picker = read('src/components/vita/MapPicker.tsx');
const editor = read('src/components/vita/PlaceEditor.tsx');

assert.ok(
  picker.includes('ResizeObserver'),
  'MapPicker deve reagire ai cambi di dimensione del contenitore',
);
assert.ok(
  picker.includes("trigger(map.current, 'resize')"),
  'Google Maps deve ricevere un resize esplicito dopo il layout',
);
assert.ok(
  picker.includes('invalidateSize'),
  'Leaflet deve ricalcolare il viewport dopo i cambi di layout',
);
assert.ok(
  picker.includes('requestAnimationFrame(() => requestAnimationFrame(keepCentreOnResize))'),
  'il primo render deve essere riallineato dopo il paint',
);
assert.ok(
  picker.includes('map.current.setCenter({ lat: point.latitude, lng: point.longitude })')
    && picker.includes('map.current.setView('),
  'un resize non deve spostare il punto geografico scelto con nessun provider',
);
assert.ok(
  editor.includes('height={compact ? 290 : 320}'),
  'la mappa compatta deve avere un viewport abbastanza alto da essere usabile',
);

console.log('Place map viewport guards: tutte le asserzioni passate');
