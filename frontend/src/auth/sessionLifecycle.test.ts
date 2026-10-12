import test from 'node:test';
import assert from 'node:assert/strict';
import { loginHrefFor, safeNextTarget } from '../shell/nextTarget.ts';
import { createSessionLifecycle } from './sessionLifecycle.ts';

const first = { user_id: 'synthetic-first' }; const second = { user_id: 'synthetic-second' };
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function setup() {
  const state = { token: 'synthetic-first-session' as string | null, error: null as unknown };
  const effects: unknown[][] = [];
  const deps = {
    readToken: async () => state.token,
    writeToken: async (token: string) => { state.token = token; effects.push(['write', token]); return true; },
    clearToken: async () => { state.token = null; effects.push(['clear']); },
    me: async (_: string) => { if (state.error) throw state.error; return first; },
    activate: (token: string, user: typeof first) => { effects.push(['activate', token, user.user_id]); },
    end: async (token: string | null, invalid: boolean) => { effects.push(['end', token, invalid]); },
    resetOpening: () => {},
  };
  return { state, effects, deps, lifecycle: createSessionLifecycle(deps) };
}

for (const status of [undefined, 503]) test(`cold-start ${status ?? 'network'} failure preserves credentials and allows retry`, async () => {
  const { state, effects, lifecycle } = setup();
  state.error = Object.assign(Error('synthetic offline'), { status });
  await lifecycle.refresh();
  assert.equal(state.token, 'synthetic-first-session');
  assert.equal(lifecycle.getSnapshot().recovery, true);
  assert.equal(lifecycle.getSnapshot().loading, false);
  assert.equal(effects.length, 0);
  state.error = null; await lifecycle.refresh();
  assert.equal(lifecycle.getSnapshot().user?.user_id, first.user_id);
  assert.equal(lifecycle.getSnapshot().recovery, false);
});

test('an already-known user remains authenticated while a refresh is offline', async () => {
  const { state, lifecycle } = setup(); await lifecycle.refresh();
  state.error = Error('offline'); await lifecycle.refresh();
  assert.equal(lifecycle.getSnapshot().user?.user_id, first.user_id);
  assert.equal(lifecycle.getSnapshot().recovery, true);
});

for (const status of [401, 403]) test(`confirmed ${status} ends the exact session and disassociates the device`, async () => {
  const { state, effects, lifecycle } = setup(); state.error = Object.assign(Error('rejected'), { status });
  await lifecycle.refresh();
  assert.equal(state.token, null); assert.equal(lifecycle.getSnapshot().user, null);
  assert.deepEqual(effects, [['end', 'synthetic-first-session', true], ['clear']]);
});

test('local logout always completes even when deferred server cleanup is offline', async () => {
  const { deps, state } = setup(); deps.end = async () => { throw Error('offline'); };
  const lifecycle = createSessionLifecycle(deps); await lifecycle.refresh(); await lifecycle.signOut();
  assert.equal(state.token, null); assert.equal(lifecycle.getSnapshot().user, null);
  assert.equal(lifecycle.getSnapshot().loading, false);
});

test('a silently failed delete cannot reactivate the exited session on refresh', async () => {
  const { deps } = setup(); deps.clearToken = async () => {};
  deps.end = async () => { throw Error('offline'); };
  const lifecycle = createSessionLifecycle(deps);
  await lifecycle.refresh(); await lifecycle.signOut(); await lifecycle.refresh();
  assert.equal(lifecycle.getSnapshot().user, null);
});

test('changing account ends the old session before storing/activating the new one', async () => {
  const { lifecycle, effects, state } = setup(); await lifecycle.refresh(); effects.length = 0;
  await lifecycle.signIn('synthetic-second-session', second);
  assert.deepEqual(effects, [
    ['end', 'synthetic-first-session', false], ['clear'], ['write', 'synthetic-second-session'],
    ['activate', 'synthetic-second-session', second.user_id],
  ]);
  assert.equal(state.token, 'synthetic-second-session');
});

for (const reject of [false, true]) test(`late old-account refresh ${reject ? '401' : 'success'} cannot undo the new login`, async () => {
  const { deps, state } = setup(); const answer = deferred<typeof first>(); const started = deferred<void>();
  deps.me = async () => { started.resolve(); return answer.promise; };
  const lifecycle = createSessionLifecycle(deps); const refresh = lifecycle.refresh(); await started.promise;
  await lifecycle.signIn('synthetic-second-session', second);
  if (reject) answer.reject(Object.assign(Error('old session'), { status: 401 })); else answer.resolve(first);
  await refresh;
  assert.equal(state.token, 'synthetic-second-session'); assert.equal(lifecycle.getSnapshot().user?.user_id, second.user_id);
});

test('a delayed storage write cannot restore credentials after logout', async () => {
  const { deps, state } = setup(); state.token = null;
  const written = deferred<void>(); const started = deferred<void>();
  deps.writeToken = async token => { started.resolve(); await written.promise; state.token = token; return true; };
  const lifecycle = createSessionLifecycle(deps); const login = lifecycle.signIn('synthetic-first-session', first); await started.promise;
  const logout = lifecycle.signOut(); written.resolve(); await Promise.all([login, logout]);
  assert.equal(state.token, null); assert.equal(lifecycle.getSnapshot().user, null);
});

test('overlapping account logins persist only the final account', async () => {
  const { deps, state } = setup(); state.token = null;
  const written = deferred<void>(); const started = deferred<void>();
  deps.writeToken = async token => { if (token === 'synthetic-first-session') { started.resolve(); await written.promise; } state.token = token; return true; };
  const lifecycle = createSessionLifecycle(deps); const oldLogin = lifecycle.signIn('synthetic-first-session', first); await started.promise;
  const newLogin = lifecycle.signIn('synthetic-second-session', second); written.resolve(); await Promise.all([oldLogin, newLogin]);
  assert.equal(state.token, 'synthetic-second-session'); assert.equal(lifecycle.getSnapshot().user?.user_id, second.user_id);
});
test('a signed-out result or call preparation preserves its real destination through login', () => {
  for (const route of ['/aggiornamento/gol_synthetic', '/prepara-chiamata']) {
    assert.equal(safeNextTarget(route), route);
    assert.equal(safeNextTarget(encodeURIComponent(route)), route);
    assert.equal(loginHrefFor(route), `/login?next=${encodeURIComponent(route)}`);
  }
});

test('login destinations still reject external URLs, lookalike routes and encoded hosts', () => {
  for (const route of ['//synthetic.invalid', 'https://synthetic.invalid', '/\\synthetic.invalid',
    '%2F%2Fsynthetic.invalid', '%252F%252Fsynthetic.invalid', '/aggiornamento-evil/a', '/prepara-chiamata-evil', '/login']) {
    assert.equal(safeNextTarget(route), null);
    assert.equal(loginHrefFor(route), '/login');
  }
});
