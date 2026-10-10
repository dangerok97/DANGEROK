import assert from 'node:assert/strict';
import { localDayKey, monthCells, monthHeading, selectSource } from './nativeMonth.ts';

const october = monthCells('2026-10');
assert.equal(october.length % 7, 0);
assert.equal(october.filter(Boolean).length, 31);
assert.equal(october[0], null);
assert.equal(october[3], '2026-10-01');
assert.equal(october[33], '2026-10-31');
assert.equal(monthHeading('2026-10'), 'ottobre 2026');
assert.equal(monthCells('2026-13').length, 0);
assert.equal(monthCells('2026-00').length, 0);
assert.equal(monthCells('2026-02').filter(Boolean).length, 28);
assert.equal(monthCells('2028-02').filter(Boolean).length, 29);
assert.equal(localDayKey(new Date(2026, 9, 10)), '2026-10-10');

const rows = [
  { id: 'own', source_type: 'ora' },
  { id: 'g', source_type: 'google' },
  { id: 'a', source_type: 'apple' },
  { id: 'third', source_type: 'other' },
];
assert.deepEqual(selectSource(rows, 'all').map(x => x.id), ['own', 'g', 'a', 'third']);
for (const source of ['ora', 'google', 'apple', 'other'] as const) {
  assert.deepEqual(selectSource(rows, source).map(x => x.source_type), [source]);
}
console.log('ORA native calendar month helpers: passed');
