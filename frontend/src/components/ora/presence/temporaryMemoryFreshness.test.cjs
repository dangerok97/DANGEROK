const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

// The real hook and components are transpiled. Only React scheduling, native
// views and API I/O are deterministic adapters; this is not a browser test.
function compile(file, requireModule, globals = {}) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    },
  }).outputText;
  vm.runInNewContext(code, {
    module, exports: module.exports, require: requireModule,
    console, setTimeout, clearTimeout, ...globals,
  }, { filename: file });
  return module.exports;
}
const now = Date.parse('2026-10-12T16:00:00Z');
class Clock extends Date { static now() { return now; } }
const outcomeView = compile(path.join(__dirname, '../situationOutcome.ts'), name => { throw Error(name); }, { Date: Clock }).situationOutcomeView;
function sampleStar(overrides = {}) {
  return {
    id: 'temporary-synthetic', temporary: true, situation_id: 'sit_synthetic',
    situation_revision: 7, updated_at: '2026-10-12T15:55:00Z',
    title: 'Bucato sintetico', statement: 'Dichiarazione sintetica registrata.',
    current_state_summary: 'Intervento dalla precedente lettura',
    expected_outcome_summary: 'Vecchia finestra registrata',
    follow_up: {
      status: 'scheduled', next_check_at: '2026-10-12T16:30:00Z',
      next_check_label: 'Prossimo controllo sintetico alle 18:30',
      completion_when: 'Avviso secondo la precedente valutazione',
      notify_when: 'Rischio della precedente valutazione',
      outcome: {
        status: 'action_now', headline: 'Ritira secondo la stima disponibile',
        action_summary: 'Indicazione sintetica della precedente lettura.',
        valid_until: '2026-10-12T18:00:00Z', situation_revision: 7,
        basis: 'estimate', action_reason: 'outcome_ready',
      },
    },
    ...overrides,
  };
}

function temporaryHookHarness(compileHook) {
  let owner = 'owner-a', props = [true, 0], position = 0, pending = [];
  const slots = [], requests = [], listeners = new Set(), timers = new Map();
  let timerId = 0, value, stateWrites = 0;
  const equal = (a, b) => !!a && !!b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const react = {
    useState(initial) {
      const id = position++;
      if (!slots[id]) slots[id] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[id].value, next => {
        stateWrites++;
        slots[id].value = typeof next === 'function' ? next(slots[id].value) : next;
      }];
    },
    useRef(initial) {
      const id = position++;
      if (!slots[id]) slots[id] = { ref: { current: initial } };
      return slots[id].ref;
    },
    useMemo(make, deps) {
      const id = position++;
      if (!slots[id] || !equal(slots[id].deps, deps)) slots[id] = { deps, value: make() };
      return slots[id].value;
    },
    useCallback(fn, deps) { return react.useMemo(() => fn, deps); },
    useEffect(effect, deps) {
      const id = position++, previous = slots[id];
      if (!previous || !equal(previous.deps, deps)) {
        slots[id] = { deps, cleanup: previous?.cleanup };
        pending.push(() => {
          slots[id].cleanup?.();
          slots[id].cleanup = effect();
        });
      }
    },
  };
  const appState = {
    currentState: 'active',
    addEventListener(_event, listener) { listeners.add(listener); return { remove: () => listeners.delete(listener) }; },
  };
  const api = {
    knowledgeMap() {
      let resolve, reject;
      const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
      requests.push({ owner, resolve, reject });
      return promise;
    },
  };
  const hook = compileHook({
    react, AppState: appState, api, useAuth: () => ({ user: owner ? { user_id: owner } : null }),
    setInterval: (fn, ms) => { const id = ++timerId; timers.set(id, { fn, ms }); return id; },
    clearInterval: id => timers.delete(id),
  });
  const render = () => {
    position = 0;
    value = hook(...props);
    const effects = pending; pending = [];
    effects.forEach(effect => effect());
    return value;
  };
  return {
    requests, timers, listeners, render,
    get value() { return value; }, get stateWrites() { return stateWrites; },
    async settle() {
      // The API Promise and the vm async function have different realms.
      // Drain adoption and continuations before taking the render snapshot.
      await new Promise(resolve => setImmediate(resolve));
      return render();
    },
    async succeed(index, stars) { requests[index].resolve({ stars }); return this.settle(); },
    async fail(index) { requests[index].reject(new Error('synthetic-unavailable')); return this.settle(); },
    setOwner(next) { owner = next; return render(); },
    setActive(next) { props = [next, props[1]]; return render(); },
    setRefreshKey(next) { props = [props[0], next]; return render(); },
    foreground() { for (const listener of [...listeners]) listener('active'); },
    unmount() { for (const slot of slots) slot?.cleanup?.(); },
  };
}

function setup() {
  return temporaryHookHarness(deps => compile(path.join(__dirname, 'useTemporaryMemory.ts'), name => {
    if (name === 'react') return deps.react;
    if (name === 'react-native') return { AppState: deps.AppState };
    if (name === '@/src/api/client') return { api: deps.api };
    if (name === '@/src/contexts/AuthContext') return { useAuth: deps.useAuth };
    throw Error('unexpected import: ' + name);
  }, { setInterval: deps.setInterval, clearInterval: deps.clearInterval }).useTemporaryMemory);
}
function currentView(memory) {
  const star = memory.latest;
  return outcomeView({
    outcome: star?.follow_up?.outcome, situationRevision: star?.situation_revision,
    followupStatus: star?.follow_up?.status, readUnavailable: memory.error,
  }, now);
}

test('failure after action_now preserves context but withdraws action until a successful read', async () => {
  const h = setup(), star = sampleStar(); h.render();
  await h.succeed(0, [star]);
  assert.equal(currentView(h.value).status, 'action_now');
  const pending = h.value.refresh(); await h.fail(1); await pending;
  assert.equal(h.value.latest, star);
  assert.equal(h.value.error, true);
  assert.equal(currentView(h.value).status, 'unavailable');
  assert.equal(currentView(h.value).needsAttention, false);
  const retry = h.value.refresh(); h.render();
  assert.equal(h.value.error, true);
  await h.succeed(2, [star]); await retry;
  assert.equal(h.value.error, false);
  assert.equal(currentView(h.value).status, 'action_now');
  assert.equal(h.requests.length, 3);
});

test('a late success cannot restore a Situation removed by a newer current read', async () => {
  const h = setup(), star = sampleStar(); h.render(); await h.succeed(0, [star]);
  const older = h.value.refresh(), newer = h.value.refresh();
  await h.succeed(2, []); await newer;
  await h.succeed(1, [star]); await older; h.render();
  assert.equal(h.value.count, 0);
  assert.equal(h.value.latest, null);
  assert.equal(h.value.error, false);
});

test('a late success cannot erase a newer failed read', async () => {
  const h = setup(), star = sampleStar(); h.render(); await h.succeed(0, [star]);
  const older = h.value.refresh(), newer = h.value.refresh();
  await h.fail(2); await newer;
  await h.succeed(1, [sampleStar({ id: 'old-response' })]); await older; h.render();
  assert.equal(h.value.error, true);
  assert.equal(h.value.latest.id, star.id);
  assert.equal(currentView(h.value).status, 'unavailable');
});

test('a late failure cannot invalidate newer successful data', async () => {
  const h = setup(); h.render(); await h.succeed(0, [sampleStar()]);
  const older = h.value.refresh(), newer = h.value.refresh();
  await h.succeed(2, [sampleStar({ id: 'current-response' })]); await newer;
  await h.fail(1); await older; h.render();
  assert.equal(h.value.error, false);
  assert.equal(h.value.latest.id, 'current-response');
});

test('changing owner hides cached data immediately and ignores previous owner completion', async () => {
  const h = setup(); h.render(); await h.succeed(0, [sampleStar()]);
  const older = h.value.refresh();
  h.setOwner('owner-b');
  assert.equal(h.value.latest, null);
  assert.equal(h.value.count, 0);
  await h.succeed(2, [sampleStar({ id: 'owner-b-star' })]);
  await h.succeed(1, [sampleStar({ id: 'owner-a-late' })]); await older; h.render();
  assert.equal(h.value.latest.id, 'owner-b-star');
  assert.equal(h.value.error, false);
});

test('logout neither retains temporary memory nor accepts an in-flight reply', async () => {
  const h = setup(); h.render(); await h.succeed(0, [sampleStar()]);
  const older = h.value.refresh();
  h.setOwner(null);
  assert.equal(h.value.latest, null);
  await h.succeed(1, [sampleStar()]); await older; h.render();
  await h.value.refresh();
  assert.equal(h.value.latest, null);
  assert.equal(h.requests.length, 2);
  assert.equal(h.timers.size, 0);
});

test('a refresh-key generation rejects a previous read without changing the cadence', async () => {
  const h = setup(); h.render();
  h.setRefreshKey(1);
  await h.succeed(1, [sampleStar({ id: 'new-generation' })]);
  await h.fail(0);
  assert.equal(h.value.latest.id, 'new-generation');
  assert.equal(h.value.error, false);
  assert.equal(h.timers.size, 1);
  assert.equal([...h.timers.values()][0].ms, 15000);
  h.foreground();
  assert.equal(h.requests.length, 3);
  await h.succeed(2, []);
});

test('inactive and unmounted readers have no late publications or new reads', async () => {
  const h = setup(); h.render(); await h.succeed(0, [sampleStar()]);
  h.setActive(false);
  assert.equal(h.value.latest, null);
  await h.value.refresh();
  assert.equal(h.requests.length, 1);
  h.setActive(true);
  const writes = h.stateWrites;
  h.unmount();
  await h.succeed(1, [sampleStar()]);
  await h.value.refresh();
  assert.equal(h.stateWrites, writes);
  assert.equal(h.requests.length, 2);
  assert.equal(h.timers.size, 0);
  assert.equal(h.listeners.size, 0);
});

test('the first failed read is explicit rather than a successful empty map', async () => {
  const h = setup(); h.render(); await h.fail(0);
  assert.equal(h.value.error, true);
  assert.equal(h.value.count, 0);
  assert.equal(currentView(h.value).status, 'unavailable');
});

function cockpitText(props, local = {}) {
  const temporary = { stars: [], latest: null, count: 0, error: false, refresh: async () => {}, ...local };
  const react = {
    useState: initial => [initial, () => {}], useEffect: () => {},
    useReducer: (_reducer, initial) => [initial, () => {}],
    useCallback: fn => fn,
  };
  const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: 'Fragment' };
  const native = {
    View: 'View', Text: 'Text', Pressable: 'Pressable', ActivityIndicator: 'ActivityIndicator',
    StyleSheet: { create: value => value, hairlineWidth: 1 },
    AppState: { addEventListener: () => ({ remove() {} }) },
  };
  const readModule = name => {
    if (name === 'react') return react;
    if (name === 'react/jsx-runtime') return jsx;
    if (name === 'react-native') return native;
    if (name === '@expo/vector-icons') return { Ionicons: 'Icon' };
    if (name === 'expo-router') return { useRouter: () => ({ push() { throw Error('unexpected navigation'); } }) };
    if (name === '@/src/theme/oraSurface') return { ora: {}, oraType: {} };
    if (name === '@/src/theme/presence') return { presencePalette: {}, presenceColors: {} };
    if (name === '@/src/theme/tokens') return { tokens: {} };
    if (name === '@/src/api/client') return { api: { getHome: async () => null } };
    if (name === './presence/useTemporaryMemory') return { useTemporaryMemory: () => temporary };
    if (name === './situationVisual') return {
      firstSituationState: star => star?.current_state_summary || null,
      situationIcon: () => 'sparkles', situationTitle: star => star.title,
    };
    if (name === './situationOutcome') return { situationOutcomeView: outcomeView };
    if (name === './SituationOutcomeSummary') return {
      ...summary,
      // Open only the existing collapsible wrapper to inspect every detail row.
      SituationDetails: ({ children }) => children,
    };
    throw Error('unexpected import: ' + name);
  };
  const summary = compile(path.join(__dirname, '../SituationOutcomeSummary.tsx'), readModule, { Date: Clock });
  const { OraCockpitContext } = compile(path.join(__dirname, '../OraCockpitContext.tsx'), readModule);
  const text = node => {
    if (node === null || node === undefined || typeof node === 'boolean') return '';
    if (Array.isArray(node)) return node.map(text).join(' ');
    if (typeof node !== 'object') return String(node);
    if (typeof node.type === 'function') return text(node.type(node.props));
    return text(node.props?.children);
  };
  return text(OraCockpitContext({ standalone: true, ...props }));
}

test('a failed selected-map read hides action, window and next-check promises', () => {
  const star = sampleStar();
  const text = cockpitText({ star, readError: true }, { latest: star, error: false });
  assert.match(text, /Stato non verificabile/);
  for (const prior of [
    star.follow_up.outcome.headline, 'Prossimo controllo', 'Ti avviso quando', 'Ti avviso prima se',
    star.current_state_summary, star.expected_outcome_summary,
  ]) assert.ok(!text.includes(prior), prior);
  assert.ok(!text.includes('Stima non ancora disponibile'));
});

test('an unrelated local-hook error cannot invalidate a fresh supplied map star', () => {
  const star = sampleStar();
  const text = cockpitText({ star, readError: false }, { error: true, latest: sampleStar({ id: 'other' }) });
  assert.ok(text.includes(star.follow_up.outcome.headline));
  assert.ok(text.includes(star.follow_up.next_check_label));
  assert.ok(!text.includes('Stato non verificabile'));
});

test('a local panel uses its local read failure and ignores an unrelated map error', () => {
  const star = sampleStar();
  const stale = cockpitText({ readError: false }, { stars: [star], latest: star, count: 1, error: true });
  assert.match(stale, /Stato non verificabile/);
  assert.ok(!stale.includes(star.follow_up.outcome.headline));
  assert.ok(!stale.includes(star.follow_up.next_check_label));
  const fresh = cockpitText({ readError: true }, { stars: [star], latest: star, count: 1, error: false });
  assert.ok(fresh.includes(star.follow_up.outcome.headline));
  assert.ok(fresh.includes(star.follow_up.next_check_label));
  assert.ok(!fresh.includes('Stato non verificabile'));
});

test('a failed first read cannot claim there are no temporary Situations', () => {
  const text = cockpitText({}, { error: true });
  assert.match(text, /STATO NON VERIFICABILE/);
  assert.ok(!text.includes('NESSUNA SITUAZIONE TEMPORANEA'));
  assert.ok(!text.includes('La mappa non ha stati momentanei aperti'));
});

test('a current cancelled map star cannot fall back to another cached local Situation', () => {
  const star = sampleStar();
  const text = cockpitText({ star: null, readError: false }, { latest: star, stars: [star], error: true });
  assert.ok(text.includes('NESSUNA SITUAZIONE TEMPORANEA'));
  assert.ok(!text.includes(star.follow_up.outcome.headline));
  assert.ok(!text.includes(star.follow_up.next_check_label));
});
