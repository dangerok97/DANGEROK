/**
 * Shell action label helpers.
 * Run: node --experimental-strip-types src/shell/actionLabels.test.ts
 */
import assert from 'node:assert/strict';
import { actionProgressLabel, flowContextLabel } from './actionLabels.ts';

assert.equal(flowContextLabel('study'), 'Studio');
assert.equal(flowContextLabel('travel'), 'Viaggio');
assert.equal(flowContextLabel('casa'), 'Casa');
assert.equal(flowContextLabel('work'), 'Lavoro');
assert.equal(flowContextLabel('mystery'), null);

assert.equal(
  actionProgressLabel({ progress: 0, answers: {} }),
  null,
  'hides fake 0%',
);

assert.equal(
  actionProgressLabel({
    meta: { step_index: 2, step_count: 5 },
    progress: 0.4,
  }),
  '2 di 5',
);

const derived = actionProgressLabel({
  answers: { a: 1, b: 2 },
  progress: 0.5,
});
assert.match(derived || '', /^\d+ di \d+$/);

console.log('actionLabels.test.ts: passed');
