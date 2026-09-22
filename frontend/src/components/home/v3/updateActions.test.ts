import assert from 'node:assert/strict';
// @ts-ignore Node runs TypeScript directly.
import { elencoAggiornamenti } from './aggiornamenti.ts';
const data: any = {
 opportunities: [{ id: 'op', title: 'Da verificare', what_ora_can_do: 'Controlla', sources: ['Calendario'], work_status: 'running' }],
 ora_ti_consiglia: [{ id: 's', title: 'Consiglio', action: { label: 'Apri', route: '/agenda', params: { day: '25' } } }],
 insights: [{ id: 'i', text: 'Informazione' }],
 agent_work: [{ id: 'g', what: 'Lavoro', needs_you: 'Conferma', state: 'In attesa' }],
};
const rows = elencoAggiornamenti(data);
assert.equal(rows.find(x => x.id === 'op')?.azione?.kind, 'verify');
assert.equal(rows.find(x => x.id === 'op')?.cosa_sta_facendo, '');
assert.equal(rows.find(x => x.id === 'op')?.fonte, 'Calendario');
assert.equal(rows.find(x => x.id === 'op')?.stato, 'Verifica avviata');
assert.equal(rows.find(x => x.id === 's')?.azione?.kind, 'suggestion');
assert.equal(rows.find(x => x.id === 's')?.azione?.params?.day, '25');
assert.equal(rows.find(x => x.id === 'i')?.azione, undefined);
assert.equal(rows.find(x => x.id === 'g')?.azione, undefined);
console.log('Update action contracts: PASS');

const prepared: any = { ora_ti_consiglia: [{ id: 'psug_test', title: 'Conflitto', status: 'active', action: { kind: 'prepare_change', label: 'Prepara' }, meta: { preparation: { summary: 'Orari confrontati', question: 'Quale puoi spostare?', options: [] } } }] };
assert.equal(elencoAggiornamenti(prepared)[0].azione?.kind, 'prepare');
assert.equal(elencoAggiornamenti(prepared)[0].cosa_sta_facendo, 'Orari confrontati');
assert.equal(elencoAggiornamenti(prepared)[0].cosa_serve, 'Quale puoi spostare?');
prepared.ora_ti_consiglia[0].status = 'expired';
assert.equal(elencoAggiornamenti(prepared)[0].azione, undefined);
