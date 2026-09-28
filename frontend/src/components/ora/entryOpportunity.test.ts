import assert from 'node:assert/strict';
import { test } from 'node:test';

import { pickOraOpportunity } from './entryOpportunity.ts';

test('empty ORA uses the first open concern in Home order', () => {
  const found = pickOraOpportunity([
    { id: 'opp_closed001', title: 'Vecchia', why_now: '', status: 'resolved' },
    { id: 'opp_open0001', title: 'Conflitto tra impegni', why_now: 'Due eventi si sovrappongono' },
    { id: 'opp_later001', title: 'Più tardi', why_now: '' },
  ]);
  assert.equal(found?.id, 'opp_open0001');
});

test('no card when there is no open and addressable concern', () => {
  assert.equal(pickOraOpportunity(), null);
  assert.equal(pickOraOpportunity([
    { id: '../../admin', title: 'Non apribile', why_now: '' },
    { id: 'opp_missing01', title: '  ', why_now: '' },
    { id: 'opp_dismissed', title: 'Chiusa', why_now: '', status: 'dismissed' },
  ]), null);
});
