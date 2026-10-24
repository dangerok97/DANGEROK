import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldShowGlobalBar } from './globalBar.ts';

test('the bar follows the person outside the tabs (owner request 24/10)', () => {
  for (const page of ['vita', 'life-setup', 'aggiornamenti', 'luoghi', 'account', 'situazione', 'document']) {
    assert.equal(shouldShowGlobalBar(page, true, false), true, page);
  }
});

test('never twice, never over a bottom input, never before sign-in, never on desktop', () => {
  assert.equal(shouldShowGlobalBar('(tabs)', true, false), false);
  for (const page of ['ora', 'conversation', 'ora-ai', 'login', 'notifica', 'vision-xray', 'chiamate']) {
    assert.equal(shouldShowGlobalBar(page, true, false), false, page);
  }
  assert.equal(shouldShowGlobalBar('vita', false, false), false);
  assert.equal(shouldShowGlobalBar('vita', true, true), false);
  assert.equal(shouldShowGlobalBar(undefined, true, false), false);
});
