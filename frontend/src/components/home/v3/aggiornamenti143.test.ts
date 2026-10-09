import { test } from 'node:test';
import assert from 'node:assert/strict';
import { elencoAggiornamenti } from './aggiornamenti.ts';

const sid = 'sit_temporanea';
const situation = {
  id: 'su_1234567890',
  situation_id: sid,
  headline: 'Metti al riparo ciò che hai lasciato fuori: è prevista pioggia a breve.',
  summary: 'Attività temporanea avviata due giorni fa',
  evidence_summary: 'Previsione aggiornata: probabilità di pioggia all’80%.',
  evidence_at: '2026-10-09T07:00:00+02:00',
  source_label: 'Previsioni meteorologiche',
  created_at: '2026-10-07T08:00:00+02:00',
  revision: 2,
};

test('one Situation is counted once across watcher, opportunity and its outcome', () => {
  const home = {
    situation_updates: [situation],
    agent_work: [{
      id: 'gol_internal', situation_id: sid,
      what: 'Capire quando la situazione raggiunge l’esito utile',
      source: 'originale non disponibile',
      state: 'Mi manca un’informazione che sai solo tu',
      outcome: 'aspetta', has_real_activity: true,
    }],
    opportunities: [{
      id: 'opp_old', situation_id: sid,
      title: 'Controllare una situazione temporanea',
      why_now: 'Guardare il meteo',
    }],
  };
  const updates = elencoAggiornamenti(home);
  assert.equal(updates.length, 1);
  assert.equal(updates[0].genere, 'situazione');
  assert.equal(updates[0].cosa, situation.headline);
  assert.equal(updates[0].situazione_id, sid);
  assert.equal(updates[0].situazione_revisione, 2);
  assert.equal(updates[0].quando, situation.created_at);
  assert.ok(!updates[0].cosa.includes('Capire quando'));
});

test('another unrelated verified update remains visible', () => {
  const rows = elencoAggiornamenti({
    situation_updates: [situation],
    opportunities: [{
      id: 'opp_other',
      title: 'Verifica un appuntamento spostato.',
      why_now: 'Il calendario ha una variazione.',
    }],
  });
  assert.deepEqual(rows.map(x => x.id), ['su_1234567890', 'opp_other']);
});

test('old monitored activity never appears as an extra Home card without a new result', () => {
  const rows = elencoAggiornamenti({
    agent_work: [{
      id: 'gol_background', situation_id: sid,
      what: 'Capire quando la situazione raggiunge esito utile',
      has_real_activity: true,
      state: 'Mi manca una cosa che sai solo tu',
      outcome: 'Attendo',
    }],
    opportunities: [{
      id: 'opp_background', situation_id: sid,
      title: 'Controllare le condizioni di questa situazione',
      why_now: 'Va verificata',
    }],
    situation_updates: [],
  });
  assert.equal(rows.length, 0);
});

test('without verified evidence there is no invented Situation advice', () => {
  const rows = elencoAggiornamenti({ situation_updates: [] });
  assert.equal(rows.length, 0);
});

test('the list uses an evidence snippet, not fabricated workflow progress', () => {
  const rows = elencoAggiornamenti({ situation_updates: [situation] });
  assert.equal(rows[0].perche, situation.evidence_summary);
  assert.equal(rows[0].fonte, situation.source_label);
  assert.equal(rows[0].cosa_serve, '');
  assert.equal(rows[0].cosa_sta_facendo, '');
});
