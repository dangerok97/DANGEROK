import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createOpeningSession } from './openingSession.ts';

test('entrance belongs to the conversation, survives navigation/reload, and resets on login', () => {
  const rows = new Map<string, string>();
  const storage = () => ({ getItem: (key: string) => rows.get(key) || null,
    setItem: (key: string, value: string) => { rows.set(key, value); }, removeItem: (key: string) => { rows.delete(key); } });
  const session = createOpeningSession(storage);
  assert.equal(session.claim('', 's1'), false);
  assert.equal(session.claim('alice', 's1'), true);
  assert.equal(session.claim('alice', 's1'), false, 'return to chat/voice/session URL replace');
  assert.equal(createOpeningSession(storage).claim('alice', 's1'), false, 'tab reload');
  assert.equal(session.claim('alice', 's2'), true, 'every new conversation has its own entrance');
  assert.equal(session.claim('alice', 's2'), false);
  assert.equal(session.claim('bob', 's1'), true, 'account switch');
  session.reset();
  assert.equal(session.claim('bob', 's1'), true, 'new login');
  assert.equal(createOpeningSession(() => undefined).claim('bob', 's1'), true, 'native cold start');
});

test('denied storage still plays only once and cannot break chat', () => {
  const session = createOpeningSession(() => { throw new Error('blocked'); });
  assert.equal(session.claim('alice', 's1'), true);
  assert.equal(session.claim('alice', 's1'), false);
  session.reset();
  assert.equal(session.claim('alice', 's1'), true);
});
