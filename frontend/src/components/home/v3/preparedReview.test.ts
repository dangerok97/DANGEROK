import assert from 'node:assert/strict';
import { test } from 'node:test';
import { elencoAggiornamenti } from './aggiornamenti.ts';

const draft = 'Confronto sintetico sulle condizioni annotate, con i limiti della fonte.';
const partial = {
  outcome: 'partial',
  what_is_missing: 'Il confronto non esplicita il periodo considerato.',
  reasoning: 'Una premessa necessaria resta implicita.',
  reviewed_at: '2026-10-12T03:00:00+00:00',
};

function normalize(overrides: Record<string, unknown> = {}) {
  return elencoAggiornamenti({ agent_work: [{
    id: 'gol_synthetic_prepared_review', what: 'Confrontare la nota sintetica',
    state: 'Il lavoro è in corso', outcome: 'Un confronto con premesse esplicite',
    prepared_text: draft, prepared_review: partial,
    ...overrides,
  }] } as any)[0];
}

test('a current partial review follows the same prepared text without marking completion', () => {
  const row = normalize();
  assert.deepEqual(row.revisione_preparazione, partial);
  assert.equal(row.testo_preparato, draft);
  assert.equal(row.stato, 'Il lavoro è in corso');
  assert.equal(row.cosa_serve, '');
  assert.equal(row.azione, undefined);
});

test('an uncertain review retains its reason when no specific missing item was supplied', () => {
  const review = { ...partial, outcome: 'uncertain', what_is_missing: '' };
  const row = normalize({ prepared_review: review });
  assert.deepEqual(row.revisione_preparazione, review);
  assert.equal(row.testo_preparato, draft);
});

test('a draft needed for approval stays reviewable when no negative review exists', () => {
  const action = { label: 'Rivedi e conferma', route: '/ora', params: { goalId: 'gol_synthetic_prepared_review' } };
  for (const prepared_review of [null, undefined]) {
    const row = normalize({ prepared_review, needs_you: 'Serve il tuo via libera.', action });
    assert.equal(row.revisione_preparazione, null);
    assert.equal(row.testo_preparato, draft);
    assert.equal(row.cosa_serve, 'Serve il tuo via libera.');
    assert.deepEqual(row.azione, { kind: 'route', ...action });
  }
});

test('malformed reviews never become a displayed judgement or stringify objects', () => {
  for (const prepared_review of [
    'partial', 7, [], {},
    { ...partial, outcome: 'achieved' },
    { ...partial, outcome: 'partially_achieved' },
    { ...partial, what_is_missing: { instruction: 'not a string' } },
    { ...partial, reasoning: ['not a string'] },
    { ...partial, reviewed_at: 'not-a-date' },
    { ...partial, reviewed_at: 123 },
  ]) {
    const row = normalize({ prepared_review });
    assert.equal(row.revisione_preparazione, null);
    assert.equal(row.testo_preparato, draft);
  }
});

test('an absent or malformed draft cannot acquire a review banner', () => {
  for (const prepared_text of [null, undefined, '', '   ', 0, { text: draft }]) {
    const row = normalize({ prepared_text });
    assert.equal(typeof row.testo_preparato, 'string');
    assert.equal(row.testo_preparato?.trim(), '');
    assert.equal(row.revisione_preparazione, null);
  }
});

test('an explicit negative verdict survives missing detail without inventing a diagnosis', () => {
  const review = { ...partial, what_is_missing: ' ', reasoning: '' };
  assert.deepEqual(normalize({ prepared_review: review }).revisione_preparazione,
    { ...review, what_is_missing: '' });
});

test('normalization keeps only the public review fields and does not mutate its input', () => {
  const review = Object.freeze({ ...partial, extra: { claim: 'not part of the public review' } });
  assert.deepEqual(normalize({ prepared_review: review }).revisione_preparazione, partial);
  assert.equal(review.extra.claim, 'not part of the public review');
});
