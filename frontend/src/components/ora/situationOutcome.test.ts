import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { SituationOutcome } from '@/src/api/client';
import { situationOutcomeView } from './situationOutcome.ts';

const now = Date.parse('2026-10-12T10:00:00+02:00');
const desiredOutcome = 'Sapere quando è utile ritirare i panni.';
function assessment(overrides: Partial<SituationOutcome> = {}): SituationOutcome {
  return {
    status: 'estimated',
    headline: 'Ritiro stimato nel pomeriggio',
    action_summary: 'Le condizioni disponibili indicano una finestra utile per il ritiro.',
    window_start: '2026-10-12T15:00:00+02:00',
    window_end: '2026-10-12T16:00:00+02:00',
    window_label: '12 ott 2026, 15:00–16:00',
    assessed_at: '2026-10-12T09:50:00+02:00',
    valid_until: '2026-10-12T12:00:00+02:00',
    situation_revision: 7,
    evidence_ids: ['ev_synthetic_weather'],
    basis: 'estimate',
    action_reason: null,
    timezone: 'Europe/Rome',
    ...overrides,
  };
}

test('the useful estimate and the internal checkpoint remain different facts', () => {
  const input = {
    outcome: assessment(), desiredOutcome, situationRevision: 7, followupStatus: 'scheduled',
    next_check_at: '2026-10-12T10:30:00+02:00', next_check_label: '12 ott 2026, 10:30',
  };
  const view = situationOutcomeView(input, now);
  assert.equal(view.status, 'estimated');
  assert.equal(view.headline, input.outcome.headline);
  assert.equal(view.window, '12 ott 2026, 15:00–16:00');
  assert.equal(view.needsAttention, false);
  assert.ok(!JSON.stringify(view).includes('10:30'));
  assert.match(view.basis, /stimata/);
});

test('a scheduled check, temporal scope and research log do not manufacture an estimate', () => {
  const input = {
    desiredOutcome, followupStatus: 'scheduled',
    temporal_scope: 'oggi', expected_outcome_summary: 'Verso le 14:00',
    next_check_label: '12 ott 2026, 12:30', last_result: 'Ho cercato: condizioni meteo…',
  };
  const view = situationOutcomeView(input, now);
  assert.equal(view.status, 'pending');
  assert.equal(view.window, null);
  assert.equal(view.detail, desiredOutcome);
  assert.ok(!JSON.stringify(view).includes('14:00'));
  assert.ok(!JSON.stringify(view).includes('12:30'));
  assert.ok(!JSON.stringify(view).includes('Ho cercato'));
});

test('action_now based on an estimate is actionable without claiming a direct observation', () => {
  const outcome = assessment({
    status: 'action_now', action_reason: 'outcome_ready',
    headline: 'Puoi ritirarli adesso secondo la stima aggiornata',
  });
  const view = situationOutcomeView({ outcome }, now);
  assert.equal(view.status, 'action_now');
  assert.equal(view.needsAttention, true);
  assert.equal(view.headline, outcome.headline);
  assert.equal(view.window, null);
  assert.match(view.basis, /stimata/);
  assert.ok(!view.basis.includes('osservazione diretta'));
});

test('early risk recommends intervention without presenting a drying window', () => {
  const outcome = assessment({
    status: 'action_now', action_reason: 'early_risk',
    headline: 'Ritira adesso: è prevista pioggia',
    action_summary: 'Il ritiro è consigliato per evitare che si bagnino.',
  });
  const view = situationOutcomeView({ outcome }, now);
  assert.equal(view.headline, outcome.headline);
  assert.equal(view.detail, outcome.action_summary);
  assert.equal(view.window, null);
  assert.match(view.label, /rischio/);
  assert.ok(!JSON.stringify(view).includes('asciutti'));
});

test('a concrete missing datum is a question, with no fabricated time', () => {
  const outcome = assessment({
    status: 'needs_input', basis: 'missing_information',
    headline: 'A che ora hai steso i panni?',
    action_summary: 'Mi serve l’orario di inizio per stimare il ritiro.',
  });
  const view = situationOutcomeView({ outcome }, now);
  assert.equal(view.status, 'needs_input');
  assert.equal(view.headline, 'A che ora hai steso i panni?');
  assert.equal(view.window, null);
  assert.equal(view.basis, '');
  assert.equal(view.needsAttention, true);
});

test('at expiry a displayed estimate loses its old action and window', () => {
  const outcome = assessment();
  const view = situationOutcomeView({ outcome, desiredOutcome }, Date.parse(outcome.valid_until));
  assert.equal(view.status, 'outdated');
  assert.equal(view.window, null);
  assert.equal(view.detail, desiredOutcome);
  assert.ok(!JSON.stringify(view).includes(outcome.headline));
  assert.ok(!JSON.stringify(view).includes('15:00'));
});

test('expired action_now cannot continue recommending action on an open page', () => {
  const outcome = assessment({ status: 'action_now', action_reason: 'early_risk', headline: 'Ritira subito' });
  const view = situationOutcomeView({ outcome }, Date.parse(outcome.valid_until) + 1);
  assert.equal(view.status, 'outdated');
  assert.equal(view.needsAttention, false);
  assert.ok(!JSON.stringify(view).includes('Ritira subito'));
});

test('missing or malformed validity never keeps an assessment actionable', () => {
  for (const valid_until of ['', 'not-a-date']) {
    const view = situationOutcomeView({ outcome: assessment({ valid_until }) }, now);
    assert.equal(view.status, 'outdated');
    assert.equal(view.window, null);
  }
});

test('a changed Situation cannot reuse a previous revision’s estimate', () => {
  const view = situationOutcomeView({ outcome: assessment(), situationRevision: 8, desiredOutcome }, now);
  assert.equal(view.status, 'outdated');
  assert.equal(view.window, null);
  assert.equal(view.detail, desiredOutcome);
});

test('stopping alerts is not presented as proof the physical result happened', () => {
  const view = situationOutcomeView({ outcome: null, desiredOutcome, followupStatus: 'stopped' }, now);
  assert.equal(view.status, 'stopped');
  assert.equal(view.window, null);
  assert.equal(view.needsAttention, false);
  assert.ok(!view.headline.includes('asciutti'));
  assert.ok(!view.headline.includes('risolta'));
});

test('a finished watch keeps its verified final action visible until expiry', () => {
  const outcome = assessment({
    status: 'action_now', action_reason: 'outcome_ready',
    headline: 'Puoi ritirarli adesso secondo la stima aggiornata',
  });
  const view = situationOutcomeView({ outcome, situationRevision: 7, followupStatus: 'stopped' }, now);
  assert.equal(view.status, 'action_now');
  assert.equal(view.headline, outcome.headline);
  assert.equal(view.needsAttention, true);
  const expired = situationOutcomeView({ outcome, followupStatus: 'stopped' }, Date.parse(outcome.valid_until));
  assert.equal(expired.status, 'stopped');
  assert.equal(expired.needsAttention, false);
});

test('plain waiting does not manufacture a question for the user', () => {
  for (const followupStatus of ['waiting_for_user', 'review_pending', 'running', 'not_scheduled']) {
    const view = situationOutcomeView({ desiredOutcome, followupStatus }, now);
    assert.equal(view.status, 'pending');
    assert.equal(view.needsAttention, false);
    assert.ok(!JSON.stringify(view).includes('Serve una risposta'));
  }
});

test('only an explicit direct-observation basis is presented as such', () => {
  const observed = situationOutcomeView({ outcome: assessment({ basis: 'direct_observation' }) }, now);
  assert.match(observed.basis, /osservazione diretta/);
  const malformed = situationOutcomeView({ outcome: assessment({ basis: 'missing_information' }) }, now);
  assert.ok(!malformed.basis.includes('osservazione diretta'));
});

test('the server’s local window is preserved across midnight and client timezones', () => {
  const window_label = 'tra il 12 ott, 23:30 e il 13 ott, 00:30 (Europe/Rome)';
  const view = situationOutcomeView({ outcome: assessment({
    window_start: '2026-10-12T23:30:00+02:00',
    window_end: '2026-10-13T00:30:00+02:00', window_label,
  }) }, now);
  assert.equal(view.window, window_label);
});

test('identical recommendation text is not duplicated below the headline', () => {
  const headline = 'Ritiro stimato nel pomeriggio';
  const view = situationOutcomeView({ outcome: assessment({ headline, action_summary: headline }) }, now);
  assert.equal(view.headline, headline);
  assert.equal(view.detail, '');
});

test('an absent estimate is explicit even when no target has been saved', () => {
  const view = situationOutcomeView({}, now);
  assert.equal(view.status, 'pending');
  assert.equal(view.window, null);
  assert.equal(view.detail, '');
  assert.match(view.headline, /non ancora disponibile/);
});
