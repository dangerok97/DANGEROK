import assert from 'node:assert/strict';
import test from 'node:test';

import { minimalContact, permissionFromResponse } from './contract.ts';

test('minimalContact strips non-callable private contact fields', () => {
  const raw = {
    id: 'CNContact-native-private-id',
    name: 'Asia Rossi',
    firstName: 'Asia',
    lastName: 'Rossi',
    nickname: 'Asi',
    company: '',
    phoneNumbers: [
      { number: '+39 327 1234567', label: 'mobile' },
      { number: '+39 327 1234567', label: 'duplicate' },
    ],
    emails: [{ email: 'asia@example.test' }],
    addresses: [{ street: 'Via privata 1' }],
    note: 'nota privata',
    birthday: { year: 2000, month: 1, day: 1 },
    image: { uri: 'private://photo' },
  };

  const mapped = minimalContact(raw);
  assert.ok(mapped);
  assert.deepEqual(mapped, {
    device_contact_id: 'CNContact-native-private-id',
    name: 'Asia Rossi',
    organization: '',
    aliases: ['Asi', 'Asia'],
    phones: [{ number: '+39 327 1234567' }],
  });

  const serialized = JSON.stringify(mapped);
  assert.equal(serialized.includes('asia@example.test'), false);
  assert.equal(serialized.includes('Via privata'), false);
  assert.equal(serialized.includes('nota privata'), false);
  assert.equal(serialized.includes('2000'), false);
  assert.equal(serialized.includes('private://photo'), false);
});

test('contacts without a callable number are not synced', () => {
  assert.equal(
    minimalContact({
      id: 'contact-no-phone',
      name: 'Luca',
      emails: [{ email: 'luca@example.test' }],
      phoneNumbers: [],
    }),
    null,
  );
});

test('permission mapping preserves iOS limited access', () => {
  assert.equal(permissionFromResponse({ status: 'granted', accessPrivileges: 'limited' }), 'limited');
  assert.equal(permissionFromResponse({ status: 'granted', accessPrivileges: 'all' }), 'granted');
  assert.equal(permissionFromResponse({ status: 'denied' }), 'denied');
  assert.equal(permissionFromResponse({ status: 'undetermined' }), 'not_requested');
});
