import test from 'node:test';
import assert from 'node:assert/strict';
import { createSessionCleanup, type PendingSessionCleanup } from './sessionCleanup.ts';

const first = { token: 'synthetic-old-session', device: 'synthetic-phone', expiresAt: 10000 };
const second = { token: 'synthetic-other-session', device: 'synthetic-phone', expiresAt: 10000 };
function setup() {
  const state = { saved: [] as PendingSessionCleanup[], offline: false, readFailed: false, writeFailed: false };
  const revoked: string[] = [];
  const deps = {
    read: async () => { if (state.readFailed) throw Error('keychain unavailable'); return structuredClone(state.saved); },
    write: async (rows: PendingSessionCleanup[]) => { if (state.writeFailed) throw Error('keychain unavailable'); state.saved = structuredClone(rows); },
    revoke: async (job: PendingSessionCleanup) => { if (state.offline) throw Error('offline'); revoked.push(job.token); },
    now: () => 1000,
  };
  return { state, revoked, deps, queue: createSessionCleanup(deps) };
}

test('offline logout persists only its own revocation and finishes after a cold restart', async () => {
  const { queue, deps, state, revoked } = setup(); state.offline = true;
  await queue.add(first); await queue.flush();
  assert.equal(queue.getSnapshot().pending, true); assert.deepEqual(state.saved, [first]);
  state.offline = false; const restarted = createSessionCleanup(deps); await restarted.flush();
  assert.deepEqual(revoked, [first.token]); assert.deepEqual(state.saved, []); assert.equal(restarted.getSnapshot().pending, false);
});

test('expired credentials are removed without retrying an invalid session', async () => {
  const { queue, state, revoked } = setup(); await queue.add({ ...first, expiresAt: 900 }); await queue.flush();
  assert.deepEqual(revoked, []); assert.deepEqual(state.saved, []);
});

test('logout added while another server retry waits is persisted immediately and cannot be lost', async () => {
  const { deps, state } = setup(); let done!: () => void; let started!: () => void;
  const wait = new Promise<void>(resolve => { done = resolve; }); const sent = new Promise<void>(resolve => { started = resolve; });
  deps.revoke = async () => { started(); await wait; };
  const queue = createSessionCleanup(deps); await queue.add(first);
  const flush = queue.flush(); await sent;
  await queue.add(second); assert.deepEqual(state.saved, [first, second]);
  done(); await flush; assert.deepEqual(state.saved, [second]);
  await queue.flush(); assert.deepEqual(state.saved, []);
});

test('a failed keychain read never overwrites an older queued logout', async () => {
  const { queue, state, revoked } = setup(); state.saved = [first]; state.readFailed = true;
  await queue.add(second);
  assert.deepEqual(state.saved, [first]); assert.equal(queue.getSnapshot().storageError, true);
  state.readFailed = false; await queue.flush();
  assert.deepEqual(new Set(revoked), new Set([first.token, second.token])); assert.deepEqual(state.saved, []);
});

test('a failed secure write is visible and can be recovered without dropping the pending job', async () => {
  const { queue, state } = setup(); state.writeFailed = true; state.offline = true;
  await queue.add(first); assert.equal(queue.getSnapshot().storageError, true);
  state.writeFailed = false; await queue.flush(); assert.deepEqual(state.saved, [first]);
  assert.equal(queue.getSnapshot().storageError, false); assert.equal(queue.getSnapshot().pending, true);
});
