import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseNotificationHandoff,
  canonicalNotificationRoute,
} from './notificationHandoff.ts';

const plan = 'dlv_1234567890abcdef';
const route = '/aggiornamento/opp_12345';
const envelope = { plan_id: plan, deep_link: route };

test('one known relative notification destination is accepted', () => {
  const parsed = parseNotificationHandoff(envelope);
  assert.deepEqual(parsed, { planId: plan, route });
  assert.equal(canonicalNotificationRoute(parsed!, {
    ok: true, outcome: 'opened', route,
  }), route);
});

test('backend must verify delivery and exactly match canonical route', () => {
  const parsed = parseNotificationHandoff(envelope)!;
  assert.equal(canonicalNotificationRoute(parsed, { ok: false }), null);
  assert.equal(canonicalNotificationRoute(parsed, {
    ok: true, outcome: 'held', route,
  }), null);
  assert.equal(canonicalNotificationRoute(parsed, {
    ok: true, outcome: 'opened', route: '/aggiornamento/other123',
  }), null);
  assert.equal(canonicalNotificationRoute(parsed, {
    ok: true, outcome: 'opened', route: 'https://evil.example',
  }), null);
});

test('unknown schemes, navigation actions and malformed IDs cannot be opened', () => {
  for (const suspect of [
    'https://evil.example/approve',
    'javascript:alert(1)',
    '//evil.example',
    '/goal/abc/authorise',
    '/aggiornamento/abc?approve=true',
    '/ora?sessionId=hello&entry=notification&action=approve',
    '/ora?needId=need1&goalId=goal1&entry=agent_need&allow=always',
    '/aggiornamento/%2e%2e',
    '/aggiornamento/a b',
    '///',
    '',
  ]) {
    assert.equal(parseNotificationHandoff({
      plan_id: plan, deep_link: suspect,
    }), null, suspect);
  }
  for (const p of [null, undefined, {}, [], 'dlv_bad!', 'unknown_12345']) {
    assert.equal(parseNotificationHandoff({
      plan_id: p, deep_link: route,
    }), null);
  }
});

test('agent-need destination lands on the blocker, never approving work', () => {
  const payload = {
    plan_id: plan,
    deep_link: '/ora?needId=need_synthetic&goalId=goal_synthetic&entry=agent_need',
  };
  assert.deepEqual(parseNotificationHandoff(payload), {
    planId: plan, route: payload.deep_link,
  });
  assert.equal(canonicalNotificationRoute(
    parseNotificationHandoff(payload)!,
    { ok: true, outcome: 'opened', route: payload.deep_link },
  ), payload.deep_link);
});

test('cross-owner acknowledgements cannot open a notification', () => {
  const valid = parseNotificationHandoff(envelope)!;
  assert.equal(canonicalNotificationRoute(valid, {
    ok: false, reason: 'unknown_plan',
  }), null);
  assert.equal(canonicalNotificationRoute(valid, {
    ok: false, reason: 'not_delivered',
  }), null);
});
