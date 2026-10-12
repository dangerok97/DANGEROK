const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '../..');

function compile(file, requireModule, globals = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(code, { exports, require: requireModule, console, setTimeout, clearTimeout, AbortController, atob, ...globals }, { filename: file });
  return exports;
}
function setup(platform = 'ios') {
  const secret = new Map(), ordinary = new Map(), nativeCalls = [], apiCalls = [], writes = [];
  const state = { offline: false, canAskAgain: true, permission: 'granted', expoToken: 'ExponentPushToken[synthetic-sdk-fixture]' };
  const nativeStore = {
    getValueWithKeyAsync: async key => { nativeCalls.push('secure-read'); return secret.get(key) ?? null; },
    setValueWithKeyAsync: async (value, key) => { nativeCalls.push('secure-write'); writes.push({ storage: 'secure', key, value }); secret.set(key, value); },
    deleteValueWithKeyAsync: async key => { nativeCalls.push('secure-delete'); secret.delete(key); },
  };
  const bytes = compile(path.join(root, 'node_modules/expo-secure-store/src/byteCounter.ts'), () => { throw Error('unexpected import'); });
  // This is the installed SDK's real key validator and JS API, with only the
  // native keychain I/O replaced. It reproduces the historical ':' failure.
  const secureStore = compile(path.join(root, 'node_modules/expo-secure-store/src/SecureStore.ts'), name => {
    if (name === './ExpoSecureStore') return nativeStore;
    if (name === './byteCounter') return bytes;
    throw Error(name);
  });
  const notifications = {
    IosAuthorizationStatus: { PROVISIONAL: 3, EPHEMERAL: 4 }, AndroidImportance: { DEFAULT: 3 },
    getPermissionsAsync: async () => { nativeCalls.push('permission-read'); return { status: state.permission, granted: state.permission === 'granted', canAskAgain: state.canAskAgain }; },
    requestPermissionsAsync: async () => { nativeCalls.push('permission-prompt'); return { status: 'granted', granted: true, canAskAgain: true }; },
    setNotificationChannelAsync: async () => { nativeCalls.push('channel'); },
    getExpoPushTokenAsync: async () => { nativeCalls.push('expo-token'); return { data: state.expoToken }; },
    setAutoServerRegistrationEnabledAsync: async value => { nativeCalls.push(['auto-registration', value]); },
    unregisterForNotificationsAsync: async () => { nativeCalls.push('unregister'); },
    dismissAllNotificationsAsync: async () => { nativeCalls.push('dismiss'); },
    clearLastNotificationResponseAsync: async () => { nativeCalls.push('clear-response'); },
  };
  const api = {
    registerPushDevice: async (body, session) => { apiCalls.push(['register', session, body]); if (state.offline) throw Error('offline'); return { ok: true, delivery_allowed: true, delivery_available: true }; },
    releasePushDevice: async (device, session) => { apiCalls.push(['release', session, device]); if (state.offline) throw Error('offline'); return { ok: true, released: 1 }; },
    logout: async session => { apiCalls.push(['logout', session]); if (state.offline) throw Error('offline'); return { ok: true }; },
  };
  const cache = new Map();
  const load = file => {
    file = path.resolve(file);
    if (cache.has(file)) return cache.get(file);
    const result = compile(file, name => {
      if (name === 'react-native') return { Platform: { OS: platform } };
      if (name === 'expo-notifications') return notifications;
      if (name === 'expo-constants') return { expoConfig: { extra: { eas: { projectId: 'synthetic-project-id' } } } };
      if (name === 'expo-crypto') return { randomUUID: () => { nativeCalls.push('installation-id'); return 'synthetic-installation-id'; } };
      if (name === 'expo-secure-store') return secureStore;
      if (name.includes('api/client')) return { api };
      if (name === '@react-native-async-storage/async-storage') return {
        getItem: async key => ordinary.get(key) ?? null,
        setItem: async (key, value) => { writes.push({ storage: 'ordinary', key, value }); ordinary.set(key, value); },
        removeItem: async key => { ordinary.delete(key); },
      };
      if (name.includes('utils/storage')) return { storage: new Proxy({}, { get: () => () => { throw Error('native cleanup must use protected storage'); } }) };
      if (name.startsWith('.')) return load(path.resolve(path.dirname(file), name + '.ts'));
      throw Error('unexpected import ' + name);
    });
    cache.set(file, result); return result;
  };
  return { secret, ordinary, nativeCalls, apiCalls, writes, state, secureStore, load, runtime: load(path.join(root, 'src/ambient/pushRegistration.ts')) };
}
const credential = owner => 'synthetic.' + Buffer.from(JSON.stringify({ sub: owner, exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url') + '.not-a-credential';

test('the real web adapter reports unsupported without native effects, registration or token storage', async () => {
  const f = setup('web');
  f.runtime.activatePushSession({ ownerId: 'synthetic-web', token: credential('web') });
  assert.equal(f.runtime.capability(), 'unsupported');
  for (const operation of [f.runtime.reconcilePush, f.runtime.enablePush]) {
    const result = await operation();
    assert.equal(result.ok, false);
    assert.equal(result.state, 'unsupported');
  }
  await f.runtime.releasePush();
  assert.deepEqual(f.nativeCalls, []);
  assert.deepEqual(f.apiCalls, []);
  assert.deepEqual(f.writes, []);
  assert.equal(f.secret.size, 0);
  assert.equal(f.ordinary.size, 0);
});

for (const platform of ['ios', 'android']) test(`${platform} never persists an Expo token, while offline revocation keeps only its protected session credential`, async () => {
  const f = setup(platform); const sessionToken = credential(platform);
  const store = f.load(path.join(root, 'src/auth/tokenStorage.ts')).authToken;
  assert.equal(await store.set(sessionToken), true);
  f.runtime.activatePushSession({ ownerId: `synthetic-${platform}`, token: sessionToken });
  assert.equal((await f.runtime.enablePush()).ok, true);
  const firstPushToken = f.state.expoToken;
  f.state.expoToken = 'ExponentPushToken[synthetic-rotated-sdk-fixture]';
  assert.equal((await f.runtime.reconcilePush()).ok, true);
  assert.deepEqual(f.apiCalls.filter(row => row[0] === 'register').map(row => row[2].token), [firstPushToken, f.state.expoToken]);

  f.state.offline = true;
  await f.runtime.endPushSession(sessionToken);
  await f.runtime.sessionCleanup.flush();
  assert.equal(f.runtime.sessionCleanup.getSnapshot().pending, true);
  const key = f.load(path.join(root, 'src/auth/sessionCleanup.ts')).PENDING_SESSION_CLEANUP_KEY;
  assert.equal(JSON.parse(f.secret.get(key))[0].token, sessionToken);
  // Check the entire write history, including values later removed, so a
  // transient local copy of either Expo token cannot escape this assertion.
  assert.ok(f.writes.length > 0);
  assert.ok(f.writes.every(row => !row.value.includes(firstPushToken) && !row.value.includes(f.state.expoToken)));
  assert.ok(f.writes.filter(row => row.storage === 'ordinary').every(row => ['0', '1'].includes(row.value)));

  f.state.offline = false;
  await f.runtime.sessionCleanup.flush();
  assert.equal(f.runtime.sessionCleanup.getSnapshot().pending, false);
  assert.equal(f.secret.has(key), false);
});

test('the real installed SecureStore rejects the previous key; current handle and revision persist correctly', async () => {
  const f = setup();
  await assert.rejects(f.secureStore.getItemAsync('ora:push:installation-handle:v2'), /Invalid key/);
  const handles = f.load(path.join(root, 'src/ambient/installationHandle.ts'));
  const handle = handles.createInstallationHandle('ios', f.secureStore, () => 'synthetic-new-handle');
  assert.equal(await handle(), 'ios:synthetic-new-handle');
  const revision = handles.createRegistrationRevision(f.secureStore);
  assert.deepEqual(await Promise.all([revision(), revision(), revision()]), [1, 2, 3]);
  assert.equal(await handles.createRegistrationRevision(f.secureStore)(), 4);
});

test('the native adapter registers the actual installation, monotonic revision and captured account', async () => {
  const f = setup(); const token = credential('first');
  f.runtime.activatePushSession({ ownerId: 'synthetic-first', token });
  assert.equal((await f.runtime.reconcilePush()).ok, true);
  assert.equal((await f.runtime.reconcilePush()).ok, true);
  const registered = f.apiCalls.filter(row => row[0] === 'register');
  assert.deepEqual(registered.map(row => row[2].device_revision), [1, 2]);
  assert.ok(registered.every(row => row[1] === token && row[2].device === 'ios:synthetic-installation-id'));
  assert.ok(registered.every(row => row[2].request_delivery_permission === false));
  await f.runtime.enablePush();
  assert.equal(f.apiCalls.at(-1)[2].request_delivery_permission, true);
  assert.equal(f.nativeCalls.includes('permission-prompt'), false);
});

test('offline exit stages only a protected old-session revocation and retry cannot unregister the new account', async () => {
  const f = setup(); const oldToken = credential('first'); const newToken = credential('second');
  f.runtime.activatePushSession({ ownerId: 'synthetic-first', token: oldToken });
  await f.runtime.reconcilePush(); f.state.offline = true;
  await f.runtime.endPushSession(oldToken); await f.runtime.sessionCleanup.flush();
  assert.equal(f.runtime.sessionCleanup.getSnapshot().pending, true);
  assert.ok([...f.secret.values()].some(value => value.includes(oldToken)));
  assert.equal([...f.ordinary.values()].some(value => value.includes(oldToken)), false);
  f.runtime.activatePushSession({ ownerId: 'synthetic-second', token: newToken });
  f.state.offline = false; await f.runtime.reconcilePush();
  const nativeStops = f.nativeCalls.filter(row => row === 'unregister').length;
  await f.runtime.sessionCleanup.flush();
  assert.equal(f.runtime.sessionCleanup.getSnapshot().pending, false);
  assert.equal(f.nativeCalls.filter(row => row === 'unregister').length, nativeStops);
  assert.ok(f.apiCalls.filter(row => row[0] === 'logout').every(row => row[1] === oldToken));
  assert.equal([...f.secret.values()].some(value => value.includes(oldToken)), false);
});

test('native auth storage never writes a credential to AsyncStorage; its tombstone is only a boolean', async () => {
  const f = setup(); const token = credential('auth');
  const store = f.load(path.join(root, 'src/auth/tokenStorage.ts')).authToken;
  assert.equal(await store.set(token), true); assert.equal(await store.get(), token);
  assert.equal(f.secret.get('ora_auth_token'), JSON.stringify(token));
  assert.deepEqual([...f.ordinary.values()], ['0']);
  await store.clear(); assert.equal(await store.get(), null);
  assert.deepEqual([...f.ordinary.values()], ['1']);
});

test('the native credential reader cannot use a token retained only for pending revocation', async () => {
  const f = setup(); const oldToken = credential('exited');
  f.secret.set('ora_auth_token', JSON.stringify(oldToken));
  f.ordinary.set('ora_auth_signed_out_v1', '0');
  const key = f.load(path.join(root, 'src/auth/sessionCleanup.ts')).PENDING_SESSION_CLEANUP_KEY;
  f.secret.set(key, JSON.stringify([{ token: oldToken, device: 'ios:synthetic-installation-id', expiresAt: Date.now() + 3600000 }]));
  const store = f.load(path.join(root, 'src/auth/tokenStorage.ts')).authToken;
  assert.equal(await store.get(), null);
  const newToken = credential('new-account');
  assert.equal(await store.set(newToken), true);
  assert.equal(await store.get(), newToken);
  assert.ok(f.secret.get(key).includes(oldToken));
});

test('real API lifecycle writes use the captured session header, never the current account', async () => {
  const requests = []; let currentTokenReads = 0;
  const client = compile(path.join(root, 'src/api/client.ts'), name => {
    if (name === 'react-native') return { Platform: { OS: 'ios' } };
    if (name.includes('auth/tokenStorage')) return { authToken: { get: async () => { currentTokenReads++; return 'synthetic-new-account'; } } };
    throw Error(name);
  }, {
    process: { env: { EXPO_PUBLIC_BACKEND_URL: 'https://synthetic.invalid' } },
    fetch: async (url, init) => { requests.push({ url, init }); return { ok: true, json: async () => ({ ok: true }) }; },
  });
  await client.api.registerPushDevice({ token: 'ExponentPushToken[synthetic]', device_revision: 3 }, 'synthetic-old-account');
  await client.api.releasePushDevice('synthetic-device', 'synthetic-old-account');
  await client.api.logout('synthetic-old-account');
  await client.api.me('synthetic-old-account');
  assert.equal(currentTokenReads, 0);
  assert.ok(requests.every(row => row.init.headers.Authorization === 'Bearer synthetic-old-account'));
});
