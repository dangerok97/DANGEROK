import test from 'node:test';
import assert from 'node:assert/strict';
import { createTokenStore } from './tokenStore.ts';

function setup() {
  const state = { token: 'synthetic-old-token' as string | null, signedOut: false, removeFails: true, markerFails: false, pendingTokens: [] as string[] };
  const deps = {
    readToken: async () => state.token,
    writeToken: async (token: string) => { state.token = token; },
    removeToken: async () => { if (state.removeFails) throw Error('locked keychain'); state.token = null; },
    readSignedOut: async () => state.signedOut,
    writeSignedOut: async (value: boolean) => { if (state.markerFails) throw Error('unavailable'); state.signedOut = value; },
    isRevocationPending: async (token: string) => state.pendingTokens.includes(token),
  };
  return { state, deps, store: createTokenStore(deps) };
}

test('failed keychain deletion cannot restore the old session on foreground or cold restart', async () => {
  const { store, state, deps } = setup(); await store.clear();
  assert.equal(state.token, 'synthetic-old-token');
  assert.equal(await store.get(), null);
  assert.equal(await createTokenStore(deps).get(), null);
  assert.equal(state.signedOut, true);
});

test('explicit new login replaces the token and clears the tombstone only after persistence', async () => {
  const { store, state, deps } = setup(); await store.clear();
  assert.equal(await store.set('synthetic-new-token'), true);
  assert.equal(state.signedOut, false);
  assert.equal(await createTokenStore(deps).get(), 'synthetic-new-token');
});

test('failed removal and tombstone write still end the current in-memory session', async () => {
  const { store, state } = setup(); state.markerFails = true; await store.clear();
  assert.equal(await store.get(), null);
});

test('a durable pending revocation fences cold-start login even when both local logout stores fail', async () => {
  const { store, state, deps } = setup();
  state.pendingTokens = ['synthetic-old-token'];
  state.markerFails = true;
  await store.clear();
  assert.equal(state.signedOut, false);
  assert.equal(state.token, 'synthetic-old-token');
  const restarted = createTokenStore(deps);
  assert.equal(await restarted.get(), null);
  // The queued old credential must not prevent a different explicit login.
  state.markerFails = false;
  assert.equal(await restarted.set('synthetic-new-token'), true);
  assert.equal(await createTokenStore(deps).get(), 'synthetic-new-token');
});

test('a keychain read error remains a recoverable error, not an anonymous session', async () => {
  const { deps } = setup(); deps.readToken = async () => { throw Error('locked'); };
  await assert.rejects(createTokenStore(deps).get(), /locked/);
});

test('failed tombstone reset never reports a persisted new login', async () => {
  const { state, store } = setup(); await store.clear(); state.markerFails = true;
  assert.equal(await store.set('synthetic-new-token'), false);
  assert.equal(await store.get(), null);
});
