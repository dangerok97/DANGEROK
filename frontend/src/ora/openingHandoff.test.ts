import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import * as navigation from './oraNav.ts';
import { createOpeningSession } from '../components/ora/presence/openingSession.ts';
import { COMPLETED_FOCUS_MS } from '../components/ora/presence/state.ts';

// Execute the production handoff and Expo route with only their external
// boundaries replaced. No API request, login or copied navigation logic.
function load(path: string, modules: Record<string, unknown>) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  } });
  const module = { exports: {} as any };
  new Function('require', 'module', 'exports', outputText)((id: string) => {
    assert.ok(id in modules, `unexpected boundary ${id}`);
    return modules[id];
  }, module, module.exports);
  return module.exports;
}

function harness() {
  const routes: string[] = [];
  const calls: string[] = [];
  const router = { push: (href: string) => routes.push(href) };
  let number = 0;
  const api = {
    aiCoreStart: async () => { calls.push('start'); return { session_id: `session_${++number}` }; },
    aiCoreMessage: async () => { calls.push('message'); },
    lifeOsSessionFocus: async () => { calls.push('focus'); },
  };
  const { startOraConversation } = load('./startOraConversation.ts', {
    '@/src/api/client': { api }, '@/src/ora/oraNav': navigation,
  });
  function arrive(href: string) {
    const url = new URL(href, 'https://ora.example');
    const params = { sessionId: url.pathname.split('/').pop(), ...Object.fromEntries(url.searchParams) };
    const { default: Route } = load('../../app/ora/[sessionId].tsx', {
      'expo-router': { useLocalSearchParams: () => params },
      '@/src/ora/oraNav': navigation,
      '@/src/components/ora/OraConversationScreen': { OraConversationScreen: 'conversation' },
      'react/jsx-runtime': { jsx: (type: unknown, props: unknown) => ({ type, props }) },
    });
    return Route().props;
  }
  return { routes, calls, api, arrive, send: (options: Record<string, unknown>) => startOraConversation(router, options) };
}

test('each first Home message reaches the real session route with an entrance', async () => {
  const h = harness();
  const opened = createOpeningSession(() => undefined);
  for (let i = 1; i <= 2; i++) {
    await h.send({ text: 'Test sintetico', entryPoint: 'home' });
    const props = h.arrive(h.routes.at(-1)!);
    assert.equal(props.sessionId, `session_${i}`);
    assert.equal(props.openingKey, props.sessionId, 'Home already sent the first message; the map must still open');
    assert.equal(opened.claim('test-owner', props.openingKey), true);
    assert.equal(opened.claim('test-owner', h.arrive(h.routes.at(-1)!).openingKey), false, 'returning to this URL must not replay');
  }
  assert.deepEqual(h.calls, ['start', 'start'], 'the handoff never repeats the first message');
});

test('continuing an existing session never advertises a new entrance', async () => {
  const h = harness();
  for (const text of ['', 'Un altro messaggio']) {
    await h.send({ text, sessionId: 'session_existing', entryPoint: 'goal_workspace', planId: 'plan_context' });
    const props = h.arrive(h.routes.at(-1)!);
    assert.equal(props.openingKey, undefined);
    assert.equal(props.planId, 'plan_context');
  }
  assert.deepEqual(h.calls, ['focus', 'focus', 'message']);
});

test('failed starts never navigate or consume an entrance', async () => {
  const h = harness();
  h.api.aiCoreStart = async () => { throw new Error('offline'); };
  await assert.rejects(h.send({ text: 'Test', entryPoint: 'home' }), /offline/);
  assert.deepEqual(h.routes, []);
});

test('opening is a fixed flag, only valid with an opaque session id', () => {
  assert.equal(navigation.buildOraConversationHref({ opening: true }), '/ora');
  assert.equal(navigation.buildOraConversationHref({ sessionId: '../bad', opening: true }), '/ora');
  const h = harness();
  assert.equal(h.arrive('/ora/session_existing?opening=anything').openingKey, undefined);
});

test('production URL handoff preserves the first reply focus, including replies after the entrance', () => {
  const source = readFileSync(new URL('../components/ora/OraConversationScreen.tsx', import.meta.url), 'utf8');
  const tree = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let callback = '';
  function visit(node: ts.Node) {
    if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useEffect'
      && node.arguments[0]?.getText(tree).includes('openingStartedAt.current')) callback = node.arguments[0].getText(tree);
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(callback, 'execute the real navigation effect');
  const compiled = ts.transpileModule(`module.exports = ${callback}`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  let timer: { callback: () => void; delay: number } | null = null;
  const routes: string[] = [];
  const context = {
    sessionId: 'new-session', paramId: null as string | null, busy: false, live: { on: false },
    planId: null, objectId: null, planItemId: null, documentId: null,
    opportunityId: null, needId: null, goalId: null, entryPoint: 'ora',
    openingStartedAt: { current: 1000 }, focusCompletedAt: { current: 9000 }, COMPLETED_FOCUS_MS,
    Date: { now: () => 9000 }, router: { replace: (url: string) => routes.push(url) },
    setTimeout: (callback: () => void, delay: number) => { timer = { callback, delay }; return 1; },
    clearTimeout: () => { timer = null; },
  };
  function run() {
    const module = { exports: null as unknown as () => (() => void) | undefined };
    new Function('module', ...Object.keys(context), compiled)(module, ...Object.values(context));
    return module.exports();
  }
  const cleanup = run();
  assert.equal(timer!.delay, COMPLETED_FOCUS_MS, 'a slow reply must not remount immediately');
  assert.deepEqual(routes, []);
  cleanup?.();
  assert.equal(timer, null, 'another turn cancels pending navigation');
  context.busy = true; run(); assert.equal(timer, null);
  context.busy = false; context.live.on = true; run(); assert.equal(timer, null);
  context.live.on = false; context.focusCompletedAt.current = 0;
  context.Date.now = () => 1500;
  run(); assert.equal(timer!.delay, 2300, 'without a topic, finish the entrance only');
  context.focusCompletedAt.current = 1200;
  run(); assert.equal(timer!.delay, 3700, 'fast reply focus also survives');
  context.Date.now = () => 10000;
  run(); assert.equal(timer!.delay, 0, 'do not hold navigation after expiry');
  timer!.callback(); assert.deepEqual(routes, ['/ora/new-session?entry=ora']);
});
