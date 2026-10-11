import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync(new URL('../../../../app/situazione.tsx', import.meta.url), 'utf8');
const map = readFileSync(new URL('../../../../src/components/ora/presence/knowledge.ts', import.meta.url), 'utf8');

test('full Situation page reads the same active canonical temporary Situations as VITA map', () => {
  assert.match(page, /api\.knowledgeMap\(\)/);
  assert.match(page, /\.filter\(\(item\) => item\.temporary\)/);
  assert.match(page, /Situazioni temporanee/);
  assert.match(page, /followup\?\.diagnosis/);
  assert.match(page, /followup\?\.next_check_label/);
  assert.match(page, /Ultima verifica registrata/);
  assert.match(page, /Esito dell’ultima verifica/);
  assert.match(page, /situazione-temporary-section/);
  assert.match(map, /admission_state\?: string/);
});
test('temporary status is read-only, never invented or persisted from a UI guess', () => {
  assert.doesNotMatch(page, /schedule_situation_check|createHomeEvent|dismissTemporarySituation|sendEmail/);
  assert.match(page, /realAlarm && followup\?\.next_check_label/);
  assert.match(page, /Controllo automatico non confermato/);
  assert.match(page, /Nessuna situazione temporanea attiva/);
});
