import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { minimalContactsPayload } from './payload.ts';

test('device contacts payload keeps only resolution fields', () => {
  const out = minimalContactsPayload([{
    id: 'ios-1',
    name: 'Asia Rossi',
    firstName: 'Asia',
    lastName: 'Rossi',
    company: '',
    phoneNumbers: [
      { number: '+39 327 1234567', label: 'mobile' },
      { number: '+39 327 7654321', label: 'work' },
    ],
    emails: [{ email: 'private@example.test' }],
    addresses: [{ street: 'Via privata' }],
    birthday: { day: 1, month: 1, year: 2000 },
    note: 'non deve uscire',
  }]);

  assert.equal(out.length, 1);
  assert.deepEqual(out[0], {
    id: 'ios-1',
    name: 'Asia Rossi',
    organization: '',
    aliases: ['Asia', 'Rossi', 'Asia Rossi'],
    phones: ['+39 327 1234567', '+39 327 7654321'],
    kind: 'person',
  });
  const serialized = JSON.stringify(out);
  assert.equal(serialized.includes('private@example.test'), false);
  assert.equal(serialized.includes('Via privata'), false);
  assert.equal(serialized.includes('2000'), false);
  assert.equal(serialized.includes('non deve uscire'), false);
});

test('contacts native dependency and permission stay configured', () => {
  const pkg = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8'));
  const app = JSON.parse(readFileSync(new URL('../../app.json', import.meta.url), 'utf8'));

  assert.equal(pkg.dependencies['expo-contacts'], '~15.0.11');
  assert.match(app.expo.ios.infoPlist.NSContactsUsageDescription, /contatti/i);
  const plugin = app.expo.plugins.find((p: any) =>
    Array.isArray(p) ? p[0] === 'expo-contacts' : p === 'expo-contacts'
  );
  assert.ok(plugin);
});

test('device sync is authenticated, permission-aware and never requests private extra fields', () => {
  const source = readFileSync(new URL('./deviceContacts.ts', import.meta.url), 'utf8');
  const layout = readFileSync(new URL('../../app/_layout.tsx', import.meta.url), 'utf8');

  assert.match(source, /getPermissionsAsync/);
  assert.match(source, /requestPermissionsAsync/);
  assert.match(source, /getContactsAsync/);
  assert.match(source, /Fields\.PhoneNumbers/);
  assert.match(source, /Fields\.Company/);
  assert.doesNotMatch(source, /Fields\.Emails/);
  assert.doesNotMatch(source, /Fields\.Addresses/);
  assert.doesNotMatch(source, /Fields\.Birthday/);
  assert.match(source, /contactsDeviceSync\('denied', \[\]\)/);
  assert.match(layout, /useDeviceContactsReconciliation/);
  assert.match(layout, /requestIfUndetermined/);
});
