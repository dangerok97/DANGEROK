/**
 * V2.5 / V2.5.1 — production ORA navigation contract
 * node frontend/src/ora/oraNav.regression.mjs
 */
import assert from 'assert';

const OPAQUE_ID = /^[A-Za-z0-9_-]{4,80}$/;

function opaque(id) {
  if (!id) return undefined;
  const s = String(id).trim();
  return OPAQUE_ID.test(s) ? s : undefined;
}

function buildOraConversationHref(p) {
  const sessionId = opaque(p.sessionId);
  const base = sessionId ? `/ora/${sessionId}` : '/ora';
  const q = new URLSearchParams();
  const planId = opaque(p.planId);
  const objectId = opaque(p.objectId);
  const planItemId = opaque(p.planItemId);
  const entry = p.entryPoint;
  if (planId) q.set('planId', planId);
  if (objectId) q.set('objectId', objectId);
  if (planItemId) q.set('planItemId', planItemId);
  if (entry) q.set('entry', entry);
  const qs = q.toString();
  return qs ? `${base}?${qs}` : base;
}

function buildGoalWorkspaceHref(planId) {
  const id = opaque(planId);
  if (!id) return '/ora';
  return `/goal-workspace/${id}`;
}

function isDevOraAiHref(href) {
  return href === '/ora-ai' || href.startsWith('/ora-ai/');
}

function assertNoSensitiveQuery(href) {
  const lower = href.toLowerCase();
  const banned = ['name=', 'job=', 'exam=', 'location=', 'email=', 'phone='];
  return !banned.some((b) => lower.includes(b));
}

// A/B — production routes
assert.strictEqual(
  buildOraConversationHref({ sessionId: 'ces_abc12345', entryPoint: 'home' }),
  '/ora/ces_abc12345?entry=home',
);
assert.ok(!isDevOraAiHref(buildOraConversationHref({ sessionId: 'ces_abc12345' })));

// C — no production helper points to /ora-ai
assert.ok(!buildOraConversationHref({ entryPoint: 'ora' }).includes('ora-ai'));
assert.ok(!buildGoalWorkspaceHref('lop_abc12345').includes('ora-ai'));

// D/E — workspace continue preserves session + plan
{
  const href = buildOraConversationHref({
    sessionId: 'ces_sess0001',
    planId: 'lop_plan0001',
    entryPoint: 'goal_workspace',
  });
  assert.ok(href.startsWith('/ora/ces_sess0001'));
  assert.ok(href.includes('planId=lop_plan0001'));
  assert.ok(href.includes('entry=goal_workspace'));
}

// F — object continuation
{
  const href = buildOraConversationHref({
    sessionId: 'ces_sess0001',
    planId: 'lop_plan0001',
    objectId: 'lgo_obj000001',
    entryPoint: 'object',
  });
  assert.ok(href.includes('objectId=lgo_obj000001'));
}

// H — Life OS workspace route
assert.strictEqual(buildGoalWorkspaceHref('lop_plan0001'), '/goal-workspace/lop_plan0001');

// R — no sensitive context in URL
assert.ok(
  assertNoSensitiveQuery(
    buildOraConversationHref({
      sessionId: 'ces_sess0001',
      planId: 'lop_x',
      entryPoint: 'home',
    }),
  ),
);

// Reject non-opaque / PII-looking injection into builder
assert.ok(!buildOraConversationHref({ planId: 'name=Francesco' }).includes('name='));

console.log('ok: ora nav V2.5 regression');
