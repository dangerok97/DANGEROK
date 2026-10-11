import assert from 'node:assert/strict';
import test from 'node:test';
import {
  connectionLabel, connectionStateOf, connectionUnavailableReason, preferredConnectionInstance,
} from './accountModel.ts';

test('only connected and syncing states claim a usable calendar', () => {
  for (const status of ['connected', 'syncing']) {
    assert.equal(connectionStateOf({ status }), 'connected');
  }
  for (const status of ['reauthorization_required', 'degraded', 'pending', 'unknown', 'active']) {
    assert.equal(connectionStateOf({ status }), 'unavailable');
  }
  for (const status of ['revoked', 'disabled']) {
    assert.equal(connectionStateOf({ status }), 'disconnected');
  }
  assert.equal(connectionStateOf(null), 'absent');
  assert.equal(connectionLabel('unavailable'), 'Non disponibile');
  assert.match(connectionUnavailableReason({ status: 'reauthorization_required' }), /autorizzazione.*scaduta/i);
  assert.match(connectionUnavailableReason({ status: 'degraded' }), /riprova automaticamente/i);
});

test('the selected account is usable even when a newer account is revoked', () => {
  const revoked = { id: 'newer_account', status: 'revoked' };
  const expired = { id: 'expired_account', status: 'reauthorization_required' };
  const healthy = { id: 'working_account', status: 'connected' };
  assert.equal(preferredConnectionInstance([revoked, expired, healthy]), healthy);
  assert.equal(preferredConnectionInstance([revoked, expired]), expired);
  assert.equal(preferredConnectionInstance([revoked]), revoked);
  assert.equal(preferredConnectionInstance([]), null);
});
