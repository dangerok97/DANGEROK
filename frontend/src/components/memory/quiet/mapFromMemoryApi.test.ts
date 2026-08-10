import { mapFromMemoryApi } from './mapFromMemoryApi.ts';

const res = mapFromMemoryApi({
  ok: true,
  partial: false,
  memories: [
    {
      id: 'memory:1',
      statement: 'Lavori nella Guardia di Finanza.',
      status: 'known',
      provenance_label: 'Da Life Setup',
      domain: 'lavoro',
    },
    {
      id: 'memory:2',
      statement: 'Vivi a Tarquinia.',
      status: 'known',
      domain: 'casa',
    },
    {
      id: 'memory:bad',
      statement: 'Tipo: employment',
      status: 'superseded',
      domain: 'lavoro',
    },
  ],
  groups: [
    { id: 'group:lavoro', label: 'Lavoro', domain: 'lavoro', memory_ids: ['memory:1'] },
    { id: 'group:casa', label: 'Casa', domain: 'casa', memory_ids: ['memory:2'] },
  ],
});

if (res.groups.length !== 2) throw new Error(`expected 2 groups, got ${res.groups.length}`);
if (res.groups[0].items[0].statement.includes('Tipo:')) {
  throw new Error('enum leakage');
}
if (res.groups.some((g) => g.items.some((i) => i.id === 'memory:bad'))) {
  throw new Error('superseded should be dropped');
}
console.log('mapFromMemoryApi.test.ts OK');
