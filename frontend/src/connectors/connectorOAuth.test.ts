import test from 'node:test';
import assert from 'node:assert/strict';
import { runConnectorOAuth, connectorReturnUrl, type ConnectorOAuthPorts } from './connectorOAuth.ts';

const authUrl = 'https://accounts.google.com/o/oauth2/v2/auth?state=synthetic';
function setup(callback = 'ora://account/permessi?gmail=connected&instance_id=synthetic-new') {
  const calls: unknown[][] = [];
  const ports: ConnectorOAuthPorts = {
    platform: 'native',
    start: async options => { calls.push(['start', options]); return { authorize_url: authUrl }; },
    openAuthSession: async (url, redirect) => { calls.push(['open', url, redirect]); return { type: 'success', url: callback }; },
    navigate: url => { calls.push(['navigate', url]); },
    instances: async () => { calls.push(['read']); return { items: [{ id: 'synthetic-new', status: 'syncing' }] }; },
  };
  return { calls, ports };
}

test('native Gmail opens the actual auth session and verifies the returned account', async () => {
  const { calls, ports } = setup();
  assert.deepEqual(await runConnectorOAuth('gmail', '/account/permessi', ports), { state: 'connected', instanceId: 'synthetic-new' });
  assert.deepEqual(calls, [
    ['start', { redirect_after: 'ora://account/permessi' }],
    ['open', authUrl, 'ora://account/permessi'], ['read'],
  ]);
});

test('Google Calendar uses its own callback and the settings destination', async () => {
  const { ports } = setup('ora://settings?google_calendar=connected&instance_id=synthetic-new');
  assert.equal((await runConnectorOAuth('google_calendar', '/settings', ports)).state, 'connected');
  assert.equal(connectorReturnUrl('/settings'), 'ora://settings');
});

for (const type of ['cancel', 'dismiss']) test(`closing Google (${type}) is retryable and never claims a connection`, async () => {
  const { ports, calls } = setup(); ports.openAuthSession = async () => ({ type });
  assert.deepEqual(await runConnectorOAuth('gmail', '/account/permessi', ports), { state: 'cancelled' });
  assert.equal(calls.some(call => call[0] === 'read'), false);
});

test('a declined consent returns to ORA without a false success', async () => {
  const { ports, calls } = setup('ora://account/permessi?gmail=cancelled');
  assert.equal((await runConnectorOAuth('gmail', '/account/permessi', ports)).state, 'cancelled');
  assert.equal(calls.some(call => call[0] === 'read'), false);
});

for (const callback of [
  'another://account/permessi?gmail=connected&instance_id=synthetic-new',
  'ora://settings?gmail=connected&instance_id=synthetic-new',
  'ora://account/permessi?google_calendar=connected&instance_id=synthetic-new',
  'ora://account/permessi?gmail=connected',
  'ora://account/permessi?gmail=connected&gmail=cancelled&instance_id=synthetic-new',
  'ora://account/permessi?gmail=connected&instance_id=synthetic-new#unexpected',
]) test(`a mismatched or ambiguous return is rejected: ${callback}`, async () => {
  const { ports, calls } = setup(callback);
  await assert.rejects(runConnectorOAuth('gmail', '/account/permessi', ports));
  assert.equal(calls.some(call => call[0] === 'read'), false);
});

for (const items of [
  [{ id: 'synthetic-old', status: 'connected' }],
  [{ id: 'synthetic-new', status: 'revoked' }],
  [{ id: 'synthetic-new', status: 'connected', consent_active: false }],
  [{ id: 'synthetic-new', status: 'connected', provider_mode: 'fake' }],
]) test(`callback success cannot replace current authenticated evidence: ${JSON.stringify(items)}`, async () => {
  const { ports } = setup(); ports.instances = async () => ({ items });
  await assert.rejects(runConnectorOAuth('gmail', '/account/permessi', ports));
});

test('provider read failure remains a failure even after a success callback', async () => {
  const { ports } = setup(); ports.instances = async () => { throw Error('synthetic offline'); };
  await assert.rejects(runConnectorOAuth('gmail', '/account/permessi', ports), /offline/);
});

test('web keeps the browser round-trip without attempting a native session', async () => {
  const { ports, calls } = setup(); ports.platform = 'web'; ports.webOrigin = 'https://ora.example.test';
  assert.equal((await runConnectorOAuth('gmail', '/settings', ports)).state, 'redirecting');
  assert.deepEqual(calls, [['start', { redirect_after: 'https://ora.example.test/settings' }], ['navigate', authUrl]]);
});

test('an unrelated authorization host is never opened', async () => {
  const { ports, calls } = setup(); ports.start = async () => ({ authorize_url: 'https://unrelated.example.test/oauth' });
  await assert.rejects(runConnectorOAuth('gmail', '/account/permessi', ports));
  assert.equal(calls.length, 0);
});
