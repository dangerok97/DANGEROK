import assert from 'node:assert/strict';
import { isGuidedAction } from './homeRoute.ts';

const action = (kind: string, label: string, route?: string) =>
  ({ id: 'test', kind, label, route });

assert.equal(isGuidedAction(action('navigate', 'Apri', '/calendar-event/ing_test')), false);
assert.equal(isGuidedAction(action('open', 'Apri', '/document/doc_test')), false);
assert.equal(isGuidedAction(action('guide', 'Organizza', '/action/open')), true);
assert.equal(isGuidedAction(action('open', 'Apri')), true);
