/**
 * Bacheca Aggiornamenti approvata il 23/10/2026: Adesso → Serve te →
 * ORA ci sta pensando → Da sapere. Una sola regola per Home e pagina.
 */
import assert from 'node:assert/strict';
import { gruppoDi, raggruppa, sintesiAggiornamenti } from './gruppiAggiornamenti.ts';

const base = {
  id: 'x', genere: 'lavoro', cosa: 'Sintetico', perche: '', fonte: '', stato: '',
  cosa_sta_facendo: '', cosa_serve: '', non_so: '', prossimo_passo: '', quando: '',
} as any;
const outcome = (status: string) => ({ situazione: { id: 's', revision: 1, summary: 'S', outcome: { status } } });

assert.equal(gruppoDi({ ...base, ...outcome('action_now') }), 'adesso', 'act-now estimate goes on top');
assert.equal(gruppoDi({ ...base, ...outcome('needs_input') }), 'per_te');
assert.equal(gruppoDi({ ...base, ...outcome('estimated') }), 'in_corso', 'an estimated Situation is followed by ORA');
assert.equal(gruppoDi({ ...base, cosa_serve: 'Quale preferisci?' }), 'per_te');
assert.equal(gruppoDi({ ...base, genere: 'occasione' }), 'per_te', 'an actionable observation asks the person');
assert.equal(gruppoDi({ ...base, genere: 'occasione', solo_informazione: true }), 'da_sapere');
assert.equal(gruppoDi({ ...base, genere: 'suggerimento' }), 'per_te');
assert.equal(gruppoDi({ ...base, genere: 'spunto' }), 'da_sapere');
assert.equal(gruppoDi(base), 'in_corso');

const rows = [
  { ...base, id: 'a', ...outcome('action_now') },
  { ...base, id: 'b', genere: 'suggerimento' },
  { ...base, id: 'c' },
  { ...base, id: 'd' },
];
const g = raggruppa(rows);
assert.deepEqual([g.adesso.length, g.per_te.length, g.in_corso.length, g.da_sapere.length], [1, 1, 2, 0]);
assert.equal(sintesiAggiornamenti(rows), '1 cosa urgente · 1 cosa per te · 2 le segue ORA');
assert.equal(sintesiAggiornamenti([]), '');

console.log('gruppiAggiornamenti: all assertions passed');
