/** A reminder the person asked for reads as a reminder, not «una cosa che ho notato». */
import assert from 'node:assert/strict';
// @ts-ignore Node runs TypeScript directly.
import { comeSiChiamaQuesto, elencoAggiornamenti } from './aggiornamenti.ts';
// @ts-ignore Node runs TypeScript directly.
import { gruppoDi } from './gruppiAggiornamenti.ts';

const home = (reminder: { kind: 'reminder' | 'phone_call' } | null): any => ({
  opportunities: [{
    id: 'opp_1', title: "Bere un bicchiere d'acqua", why_now: "È il momento: Bere un bicchiere d'acqua",
    what_ora_can_do: 'Ricordartelo adesso.', created_at: '2026-10-27T06:59:00Z',
    valid_until: '2099-10-27T12:59:00Z', reminder,
  }],
});

const [promemoria] = elencoAggiornamenti(home({ kind: 'reminder' }));
assert.equal(promemoria.promemoria, 'reminder');
assert.equal(promemoria.azione, undefined);
assert.equal(comeSiChiamaQuesto(promemoria), 'Il promemoria che mi hai chiesto');
assert.equal(gruppoDi(promemoria), 'adesso');

const [telefonata] = elencoAggiornamenti(home({ kind: 'phone_call' }));
assert.equal(comeSiChiamaQuesto(telefonata), 'La telefonata che mi hai chiesto');
assert.equal(gruppoDi(telefonata), 'da_sapere');

const [normale] = elencoAggiornamenti(home(null));
assert.equal(normale.promemoria, undefined);
assert.equal(comeSiChiamaQuesto(normale), 'Una cosa che ho notato');
console.log('Reminder updates: PASS');

const [brief] = elencoAggiornamenti(home({ kind: 'morning_brief' } as any));
assert.equal(comeSiChiamaQuesto(brief), 'La tua giornata in breve');
assert.equal(gruppoDi(brief), 'da_sapere');
console.log('Morning brief update: PASS');

const [habit] = elencoAggiornamenti(home({ kind: 'habit' } as any));
assert.equal(comeSiChiamaQuesto(habit), 'Una proposta di ORA');
assert.equal(gruppoDi(habit), 'per_te');
console.log('Habit proposal update: PASS');

const [leave] = elencoAggiornamenti(home({ kind: 'reminder', route_url: 'https://www.google.com/maps/dir/?api=1&destination=42.35,11.61&travelmode=driving' } as any));
assert.match(String(leave.percorso), /^https:\/\/www\.google\.com\/maps\/dir\//);
const [bad] = elencoAggiornamenti(home({ kind: 'reminder', route_url: 'javascript:alert(1)' } as any));
assert.equal(bad.percorso, undefined);
console.log('Leave route: PASS');
