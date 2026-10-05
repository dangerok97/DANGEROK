import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const picker = readFileSync(resolve(FRONTEND, 'src/components/vita/MapPicker.tsx'), 'utf8');
const maps = readFileSync(resolve(FRONTEND, 'src/config/maps.ts'), 'utf8');

assert.ok(
  picker.includes('loadMaps()'),
  'Luoghi deve montare Google Maps',
);
assert.ok(
  picker.includes('(globalThis as any).google.maps'),
  'MapPicker deve usare Google Maps JavaScript API',
);
assert.ok(
  !picker.includes('OpenStreetMap') && !picker.includes('tile.openstreetmap.org') && !picker.includes('loadLeaflet'),
  'Luoghi non deve sostituire Google Maps con un altro provider',
);
assert.ok(
  maps.includes("EXPO_PUBLIC_MAPS_WEB_KEY"),
  'Google Maps deve ricevere la browser API key da Railway/build env',
);
assert.ok(
  picker.includes('Google Maps non riesce a caricarsi'),
  'un errore Maps deve essere esplicito e non mascherato da un provider diverso',
);

console.log('Google Maps-only guards: tutte le asserzioni passate');
