import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createInstallationHandle, PUSH_DEVICE_KEY } from './installationHandle.ts';

function memoryStore(rows = new Map<string, string>()) {
  return {
    getItemAsync: async (key: string) => rows.get(key) || null,
    setItemAsync: async (key: string, value: string) => { rows.set(key, value); },
  };
}

test('one installation remains identifiable across users and app restarts', async () => {
  const stored = new Map<string, string>();
  let generated = 0;
  const randomId = () => {
    generated += 1;
    return 'synthetic-opaque-installation';
  };
  const handle = createInstallationHandle('ios', memoryStore(stored), randomId);
  assert.equal(await handle(), 'ios:synthetic-opaque-installation');
  assert.equal(await handle(), 'ios:synthetic-opaque-installation');
  const restarted = createInstallationHandle('ios', memoryStore(stored), randomId);
  assert.equal(await restarted(), 'ios:synthetic-opaque-installation');
  assert.equal(generated, 1);
  assert.equal(stored.get(PUSH_DEVICE_KEY), 'synthetic-opaque-installation');
});

test('two installations cannot share a slug-derived push device identity', async () => {
  const first = createInstallationHandle('ios', memoryStore(), () => 'first-device');
  const second = createInstallationHandle('ios', memoryStore(), () => 'second-device');
  assert.notEqual(await first(), await second());
});

test('concurrent requests do not generate two installation identities', async () => {
  const stored = memoryStore();
  let generated = 0;
  const handle = createInstallationHandle('android', stored, () => {
    generated += 1;
    return 'one-id';
  });
  const values = await Promise.all([handle(), handle(), handle()]);
  assert.deepEqual(values, ['android:one-id', 'android:one-id', 'android:one-id']);
  assert.equal(generated, 1);
});

test('storage failure is visible and next call can retry safely', async () => {
  let attempts = 0;
  const stored = memoryStore();
  const store = {
    getItemAsync: async (key: string) => {
      attempts += 1;
      if (attempts === 1) throw new Error('keychain inaccessible');
      return stored.getItemAsync(key);
    },
    setItemAsync: stored.setItemAsync,
  };
  const handle = createInstallationHandle('ios', store, () => 'retried');
  await assert.rejects(handle, /keychain inaccessible/);
  assert.equal(await handle(), 'ios:retried');
  assert.equal(attempts, 2);
});
