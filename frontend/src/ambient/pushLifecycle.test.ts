import test from 'node:test';
import assert from 'node:assert/strict';
import { createPushLifecycle, pushRecovery, type PushPermission, type PushSession } from './pushLifecycle.ts';

const first = { ownerId: 'synthetic-first', token: 'synthetic-session-first' };
const second = { ownerId: 'synthetic-second', token: 'synthetic-session-second' };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function setup() {
  const calls: { action: string; owner?: string; session?: string; token?: string; consent?: boolean }[] = [];
  const state = { permission: { status: 'granted', canAskAgain: true } as PushPermission, project: 'synthetic-project', fail: '', deliveryAllowed: true, deliveryAvailable: true };
  const deps = {
    native: true, projectId: () => state.project || undefined,
    permission: async () => { if (state.fail === 'permission') throw Error('permission unavailable'); return state.permission; },
    requestPermission: async () => { calls.push({ action: 'prompt' }); return state.permission = { status: 'granted', canAskAgain: true }; },
    prepareChannel: async () => { calls.push({ action: 'channel' }); },
    device: async () => 'synthetic-installation',
    token: async (_: string) => { if (state.fail === 'token') throw Error('offline'); return 'ExponentPushToken[synthetic]'; },
    register: async (session: PushSession, token: string, _device: string, consent: boolean) => {
      calls.push({ action: 'register', owner: session.ownerId, session: session.token, token, consent });
      if (state.fail === 'register') throw Error('503');
      return { ok: true, delivery_allowed: state.deliveryAllowed, delivery_available: state.deliveryAvailable };
    },
    release: async (session: PushSession, _device: string) => {
      calls.push({ action: 'release', owner: session.ownerId, session: session.token });
      return { ok: true };
    },
    stopNative: async () => { calls.push({ action: 'stop' }); },
  };
  return { calls, state, deps, lifecycle: createPushLifecycle(deps) };
}

test('login and foreground register already-granted permission, without an OS prompt', async () => {
  const { lifecycle, calls } = setup();
  lifecycle.setSession(first);
  assert.equal((await lifecycle.reconcile()).ok, true);
  assert.equal((await lifecycle.reconcile()).ok, true);
  assert.deepEqual(calls.map(row => row.action), ['register', 'register']);
  assert.ok(calls.every(row => row.owner === first.ownerId && row.session === first.token));
  assert.ok(calls.every(row => row.consent === false));
});

test('undetermined or denied permissions never prompt during reconciliation', async () => {
  for (const status of ['undetermined', 'denied'] as const) {
    const { lifecycle, state, calls } = setup();
    state.permission = { status, canAskAgain: false };
    lifecycle.setSession(first);
    assert.equal((await lifecycle.reconcile()).state, status);
    assert.deepEqual(calls.map(row => row.action).sort(), ['release', 'stop']);
  }
});

test('only explicit enable prepares the Android channel then asks and registers', async () => {
  const { lifecycle, state, calls } = setup();
  state.permission = { status: 'undetermined', canAskAgain: true };
  lifecycle.setSession(first);
  assert.equal((await lifecycle.reconcile(true)).state, 'granted');
  assert.deepEqual(calls.map(row => row.action), ['channel', 'prompt', 'register']);
  assert.equal(calls.at(-1)?.consent, true);
});

test('an endpoint without account delivery consent stays actionable; only an explicit enable requests consent', async () => {
  const { lifecycle, state, calls } = setup(); state.deliveryAllowed = false;
  lifecycle.setSession(first);
  assert.equal((await lifecycle.reconcile()).state, 'needs_consent');
  assert.equal(pushRecovery(lifecycle.getSnapshot())?.actionLabel, 'Attiva notifiche');
  assert.equal(calls.at(-1)?.consent, false);
  state.deliveryAllowed = true;
  assert.equal((await lifecycle.reconcile(true)).ok, true);
  assert.equal(calls.at(-1)?.consent, true);
  assert.equal(calls.some(row => row.action === 'prompt'), false);
});

test('disabled delivery is not reported as granted and offers no unusable retry', async () => {
  const { lifecycle, state } = setup(); state.deliveryAvailable = false;
  lifecycle.setSession(first);
  assert.deepEqual(await lifecycle.reconcile(true), { ok: false, state: 'delivery_unavailable' });
  assert.equal(pushRecovery(lifecycle.getSnapshot())?.action, null);
});

test('a build without a project ID does not ask for unusable permission', async () => {
  const { lifecycle, state, calls } = setup();
  state.permission.status = 'undetermined'; state.project = '';
  lifecycle.setSession(first);
  assert.equal((await lifecycle.reconcile(true)).state, 'no_project');
  assert.deepEqual(calls, []);
  assert.equal(pushRecovery(lifecycle.getSnapshot())?.action, null);
});

test('permanently denied permission offers Settings and never repeats the OS prompt', async () => {
  const { lifecycle, state, calls } = setup();
  state.permission = { status: 'denied', canAskAgain: false };
  lifecycle.setSession(first);
  await lifecycle.reconcile(true);
  assert.equal(pushRecovery(lifecycle.getSnapshot())?.action, 'settings');
  assert.equal(calls.some(row => row.action === 'prompt'), false);
});

for (const failure of ['permission', 'token', 'register']) test(`${failure} failure remains visible and a later retry completes registration`, async () => {
  const { lifecycle, state } = setup();
  state.fail = failure;
  lifecycle.setSession(first);
  assert.equal((await lifecycle.reconcile(true)).ok, false);
  assert.equal(pushRecovery(lifecycle.getSnapshot())?.actionLabel, 'Riprova');
  assert.equal(lifecycle.getSnapshot().busy, false);
  state.fail = '';
  assert.equal((await lifecycle.reconcile()).ok, true);
  assert.equal(pushRecovery(lifecycle.getSnapshot()), null);
});

test('revocation in OS settings retires the old endpoint on the next foreground', async () => {
  const { lifecycle, state, calls } = setup();
  lifecycle.setSession(first);
  await lifecycle.reconcile();
  state.permission = { status: 'denied', canAskAgain: false };
  await lifecycle.reconcile();
  assert.equal(lifecycle.getSnapshot().state, 'denied');
  assert.deepEqual(calls.filter(row => row.action === 'release').map(row => row.owner), [first.ownerId]);
  assert.equal(calls.some(row => row.action === 'prompt'), false);
});

test('a token arriving after logout cannot register the old account or borrow the new credential', async () => {
  const { deps, calls } = setup();
  const token = deferred<string>(); const started = deferred<void>();
  let tokens = 0;
  deps.token = async () => { tokens++; if (tokens === 1) { started.resolve(); return token.promise; } return 'ExponentPushToken[new]'; };
  const lifecycle = createPushLifecycle(deps);
  lifecycle.setSession(first);
  const oldWork = lifecycle.reconcile(); await started.promise;
  const release = lifecycle.release();
  lifecycle.setSession(second);
  const newWork = lifecycle.reconcile();
  token.resolve('ExponentPushToken[old]');
  await Promise.all([oldWork, release, newWork]);
  assert.deepEqual(calls.filter(row => row.action === 'register'), [{ action: 'register', owner: second.ownerId, session: second.token, token: 'ExponentPushToken[new]', consent: false }]);
  assert.equal(calls.findIndex(row => row.action === 'release') < calls.findIndex(row => row.action === 'register'), true);
  assert.equal(lifecycle.getSnapshot().ownerId, second.ownerId);
});

test('an already-started old registration is released before the next account registers', async () => {
  const { deps, calls } = setup();
  const sent = deferred<void>(); const acknowledged = deferred<{ ok: boolean; delivery_allowed: boolean; delivery_available: boolean }>();
  const register = deps.register;
  deps.register = async (...args) => { const result = await register(...args); if (args[0].ownerId === first.ownerId) { sent.resolve(); return acknowledged.promise; } return result; };
  const lifecycle = createPushLifecycle(deps);
  lifecycle.setSession(first);
  const work = lifecycle.reconcile(); await sent.promise;
  const release = lifecycle.release(); lifecycle.setSession(second);
  const next = lifecycle.reconcile(); acknowledged.resolve({ ok: true, delivery_allowed: true, delivery_available: true });
  await Promise.all([work, release, next]);
  assert.deepEqual(calls.filter(row => row.action !== 'stop').map(row => [row.action, row.owner]), [
    ['register', first.ownerId], ['release', first.ownerId], ['register', second.ownerId],
  ]);
  assert.equal(lifecycle.getSnapshot().state, 'granted');
});

test('simultaneous foreground/token events share one registration attempt', async () => {
  const { lifecycle, calls } = setup(); lifecycle.setSession(first);
  const one = lifecycle.reconcile(); const two = lifecycle.reconcile();
  assert.equal(one, two); await one;
  assert.equal(calls.filter(row => row.action === 'register').length, 1);
});

test('web never calls native permission, token, registration or unregistration effects', async () => {
  const { deps, calls } = setup(); deps.native = false;
  const lifecycle = createPushLifecycle(deps); lifecycle.setSession(first);
  assert.equal((await lifecycle.reconcile(true)).state, 'unsupported');
  await lifecycle.release();
  assert.deepEqual(calls, []);
});
