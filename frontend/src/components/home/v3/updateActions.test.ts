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
