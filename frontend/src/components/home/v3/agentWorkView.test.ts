import assert from 'node:assert/strict';
import { test } from 'node:test';
import { agentWorkBadge, isAgentUpdate } from './agentWorkView.ts';
import { elencoAggiornamenti } from './aggiornamenti.ts';

test('autonomous origin alone never means work was done', () => {
  assert.equal(agentWorkBadge({ autonomous: true } as any), 'Da verificare');
  assert.equal(agentWorkBadge({ progress_kind: 'scheduled' }), 'Controllo programmato');
  assert.equal(agentWorkBadge({ progress_kind: 'update' }), 'Aggiornamento');
  assert.equal(agentWorkBadge({ progress_kind: 'problem' }), 'Controllo da verificare');
  assert.equal(agentWorkBadge({ needs_you: 'Una risposta' }), 'Serve una risposta');
});
test('Home and expanded list exclude the same scheduled-only work before applying limits', () => {
  const pending = { id: 'scheduled', what: 'Panni stesi', outcome: 'asciutti', state: 'Controllo programmato.', show_in_updates: false };
  const update = { id: 'actual', what: 'Panni stesi', state: 'Risultato di prova', outcome: 'obiettivo',
    source_kind: 'situation_followup', show_in_updates: true, progress_kind: 'update', next_step: 'Prossimo controllo: 17:00.' };
  const work = [pending, {...pending, id: 'second'}, {...pending, id: 'third'}, update];
  assert.equal(work.filter(isAgentUpdate).length, 1);
  const items = elencoAggiornamenti({ agent_work: work } as any);
  assert.deepEqual(items.map(x => x.id), ['actual']);
  assert.equal(items[0].prossimo_passo, 'Prossimo controllo: 17:00.');
  assert.equal(elencoAggiornamenti({agent_work: [pending]} as any).length, 0);
});
test('a desired outcome is never reported as the next executed step of a Situation', () => {
  const items = elencoAggiornamenti({agent_work: [{id: 'x', what: 'Panni', state: 'Un risultato', outcome: 'I panni sono asciutti', source_kind: 'situation_followup', show_in_updates: true}]} as any);
  assert.equal(items[0].prossimo_passo, '');
});
