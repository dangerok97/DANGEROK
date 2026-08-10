/**
 * Generic Contesti mapping — novel situations need no FE taxonomy.
 * Run: node --experimental-strip-types src/components/contexts/quiet/mapFromLifeMapApi.test.ts
 */
import assert from 'node:assert/strict';
import { mapFromLifeMapApi } from './mapFromLifeMapApi.ts';

const mapped = mapFromLifeMapApi({
  ok: true,
  areas: [],
  situations: [
    {
      id: 'inferred:abc',
      kind: 'inferred',
      title: 'Palestra con Marco',
      temporal: 'Da settembre',
      summary: null,
      href: '',
    },
    {
      id: 'study:1',
      kind: 'study',
      title: 'Psicologia',
      temporal: 'Esame tra 5 giorni',
      href: '/study-plan/1',
    },
  ],
});

assert.equal(mapped.situations.length, 2);
assert.equal(mapped.situations[0].kind, 'inferred');
assert.equal(mapped.situations[0].title, 'Palestra con Marco');
assert.equal(mapped.situations[0].href, null);
assert.equal(mapped.situations[1].href, '/study-plan/1');
// No gym enum / DOMAIN_GYM required
assert.ok(!('gym' in (mapped.situations[0] as object)));

console.log('mapFromLifeMapApi.test.ts OK');
