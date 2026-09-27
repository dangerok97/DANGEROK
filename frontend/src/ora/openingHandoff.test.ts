import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import * as navigation from './oraNav.ts';
import { createOpeningSession } from '../components/ora/presence/openingSession.ts';

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
