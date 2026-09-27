import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

// Run the screen's actual effect with deferred network boundaries. An unresolved
// secondary request reproduces the production spinner without timing assertions.
const source = readFileSync(new URL('./GuidedSetupScreen.tsx', import.meta.url), 'utf8');
const tree = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let effect = '';
function visit(node: ts.Node) {
  if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useEffect'
      && node.arguments[0]?.getText(tree).includes('api.guidedSetupState()')) {
    effect = node.arguments[0].getText(tree);
  }
  ts.forEachChild(node, visit);
}
visit(tree);
assert.ok(effect, 'exercise the real Vita loading effect');
const compiled = ts.transpileModule(`module.exports = ${effect}`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness() {
  const profile = deferred();
  const situations = deferred();
  const calls: string[] = [];
  const view = { loading: true, state: null as unknown, error: null as unknown, situations: [] as unknown };
  const context = {
    api: {
      guidedSetupState: () => { calls.push('profile'); return profile.promise; },
      getLifeMap: (options: unknown) => {
        assert.deepEqual(options, { enrich: false });
        calls.push('situations'); return situations.promise;
      },
    },
    setState: (value: unknown) => { view.state = value; },
    setError: (value: unknown) => { view.error = value; },
    setLoading: (value: boolean) => { view.loading = value; },
    setSituations: (value: unknown) => { view.situations = value; },
    humanizeError: () => 'Riprova più tardi',
  };
  const module = { exports: null as unknown as () => () => void };
  new Function('module', ...Object.keys(context), compiled)(module, ...Object.values(context));
  const dispose = module.exports();
  return { profile, situations, calls, view, dispose };
}
const flush = () => new Promise<void>(resolve => setImmediate(resolve));

test('profile and secondary overview start together; unresolved overview never blocks Vita', async () => {
  const h = harness();
  assert.deepEqual(h.calls, ['profile', 'situations']);
  const state = { percent: 4, objective: { ref: 'casa.situazione' } };
  h.profile.resolve(state);
  await flush();
  assert.equal(h.view.loading, false);
  assert.deepEqual(h.view.state, state);
  assert.deepEqual(h.view.situations, []);
  h.situations.resolve({ situations: [{ id: 'synthetic-situation' }] });
  await flush();
  assert.deepEqual(h.view.situations, [{ id: 'synthetic-situation' }]);
  assert.equal(h.view.loading, false);
  h.dispose();
});

test('secondary failure does not hide the profile or report a profile error', async () => {
  const h = harness();
  h.situations.reject(new Error('secondary timeout'));
  h.profile.resolve({ percent: 4 });
  await flush();
  assert.equal(h.view.loading, false);
  assert.equal(h.view.error, null);
  assert.deepEqual(h.view.state, { percent: 4 });
  h.dispose();
});

test('profile failure exits the spinner even while secondary data is pending', async () => {
  const h = harness();
  h.profile.reject(new Error('offline'));
  await flush();
  assert.equal(h.view.loading, false);
  assert.equal(h.view.error, 'Riprova più tardi');
  assert.equal(h.view.state, null);
  h.dispose();
});

test('secondary data arriving first cannot prematurely declare the profile ready', async () => {
  const h = harness();
  h.situations.resolve({ situations: [{ id: 'synthetic-situation' }] });
  await flush();
  assert.equal(h.view.loading, true);
  h.profile.resolve({ percent: 4 });
  await flush();
  assert.equal(h.view.loading, false);
  h.dispose();
});

test('late responses after leaving the page cannot update its state', async () => {
  const h = harness();
  h.dispose();
  h.profile.resolve({ percent: 99 });
  h.situations.resolve({ situations: [{ id: 'stale' }] });
  await flush();
  assert.deepEqual(h.view, { loading: true, state: null, error: null, situations: [] });
});
