import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

type Element = { type: unknown; props: Record<string, any> };
function harness() {
  let index = 0;
  const state: any[] = [];
  const react = {
    useState: (initial: any) => {
      const id = index++;
      if (!(id in state)) state[id] = typeof initial === 'function' ? initial() : initial;
      return [state[id], (value: any) => { state[id] = typeof value === 'function' ? value(state[id]) : value; }];
    },
    useCallback: (fn: unknown) => fn, useMemo: (fn: () => unknown) => fn(),
    useEffect: () => {}, useRef: (value: unknown) => ({ current: value }),
  };
  const primitive = (type: unknown, props: Element['props']) => ({ type, props });
  const colors = { textPrimary: 'white', textSecondary: 'gray', accent: 'blue' };
  const typography = { title: { fontSize: 24 }, headline: { fontSize: 20 }, caption: { fontSize: 14 } };
  const tokens = { radius: { full: 20 }, responsive: { tabletMax: 1023 }, spacing: {}, typography: { title: {}, button: {}, footnote: {}, bodySmall: {} }, touch: { min: 44 }, motion: { fadeIn: { duration: 100 } } };
  const modules: Record<string, unknown> = {
    react, 'react/jsx-runtime': { jsx: primitive, jsxs: primitive, Fragment: 'Fragment' },
    'react-native': { View: 'View', Text: 'Text', Pressable: 'Pressable', ScrollView: 'ScrollView', KeyboardAvoidingView: 'KeyboardAvoidingView', Platform: { OS: 'web' }, useWindowDimensions: () => ({ width: 1200 }), AppState: { currentState: 'active' }, StyleSheet: { create: (value: unknown) => value } },
    '@/src/components/ora/presence/PresenceCanvas': { PresenceCanvas: 'Canvas' },
    '@/src/theme/presence': { presencePalette: {} },
    '@/src/theme/ThemeProvider': { useTheme: () => ({ colors, typography }) },
    '@/src/theme/tokens': { tokens }, '@/src/shell': { useReducedMotion: () => true, ImmersiveScreen: 'ImmersiveScreen', safeNextTarget: () => null },
    '@/src/components/ui/AppInput': { AppInput: 'Input' }, '@/src/components/ui/AppButton': { AppButton: 'Button' },
  };
  const load = (path: string) => {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    const module = { exports: {} as any };
    new Function('require', 'module', 'exports', compiled)((id: string) => {
      assert.ok(id in modules, `unexpected boundary ${id}`);
      return modules[id];
    }, module, module.exports);
    return module.exports;
  };
  const intro = load('./RegistrationIntro.tsx');
  return { modules, intro, load, render: (component: (props: any) => Element, props: any) => { index = 0; return component(props); } };
}
function find(tree: any, predicate: (element: Element) => boolean): Element | undefined {
  if (Array.isArray(tree)) return tree.map(item => find(item, predicate)).find(Boolean);
  if (!tree || typeof tree !== 'object') return undefined;
  return predicate(tree) ? tree : find(tree.props?.children, predicate);
}
const button = (tree: Element, label: string) => {
  const found = find(tree, e => e.props?.label === label);
  assert.ok(found, `button ${label}`); return found;
};

test('registration adds a star only after each separate name step is confirmed', () => {
  const h = harness(); let completed = 0;
  const props = { first: '', last: '', onFirstChange: (v: string) => { props.first = v; }, onLastChange: (v: string) => { props.last = v; }, onComplete: () => completed++, onExit: () => {} };
  const render = () => h.render(h.intro.RegistrationIntro, props);
  assert.deepEqual(find(render(), e => e.type === h.intro.RegistrationMap)!.props, { first: '', last: '', example: null, firstStepComplete: false, reveal: true });
  button(render(), 'Fammi vedere').props.onPress();
  assert.equal(find(render(), e => e.type === h.intro.RegistrationMap)!.props.firstStepComplete, true);
  button(render(), 'Conferma nome').props.onPress();
  assert.ok(find(render(), e => e.props?.accessibilityRole === 'alert'));
  button(render(), 'Nome').props.onChangeText('Giulia');
  assert.equal(find(render(), e => e.type === h.intro.RegistrationMap)!.props.first, '', 'typing alone does not earn the star');
  button(render(), 'Conferma nome').props.onPress();
  assert.equal(find(render(), e => e.type === h.intro.RegistrationMap)!.props.first, 'Giulia');
  button(render(), 'Conferma cognome').props.onPress();
  assert.ok(find(render(), e => e.props?.accessibilityRole === 'alert'));
  assert.equal(completed, 0);
  button(render(), 'Cognome').props.onChangeText('De Luca');
  assert.equal(find(render(), e => e.type === h.intro.RegistrationMap)!.props.last, '', 'surname star waits for confirmation');
  button(render(), 'Conferma cognome').props.onPress();
  let tree = render();
  assert.equal(find(tree, e => e.type === h.intro.RegistrationMap)!.props.last, 'De Luca');
  assert.equal(find(tree, e => e.type === h.intro.RegistrationMap)!.props.example, null, 'examples wait for the choice');
  find(tree, e => e.props?.accessibilityState?.selected === false && find(e, child => child.props?.children === 'Persone') !== undefined)!.props.onPress();
  assert.equal(find(render(), e => e.type === h.intro.RegistrationMap)!.props.example, 'people');
  find(render(), e => e.type === 'Pressable' && find(e, child => child.props?.children === '← Indietro') !== undefined)!.props.onPress();
  assert.equal(button(render(), 'Cognome').props.value, 'De Luca');
  button(render(), 'Conferma cognome').props.onPress();
  button(render(), 'Continua con la registrazione').props.onPress();
  assert.equal(completed, 1);
});

test('draft geometry contains no personal text, no blank stars and no duplicate stars while typing', () => {
  const h = harness();
  assert.deepEqual(h.intro.registrationStars(' ', ''), []);
  const first = h.intro.registrationStars('Giulia', '');
  const both = h.intro.registrationStars('Giulia', 'De Luca');
  assert.equal(first.length, 1); assert.equal(both.length, 2);
  assert.equal(first[0].id, both[0].id);
  assert.equal(JSON.stringify(both).includes('Giulia'), false);
  assert.equal(JSON.stringify(both).includes('De Luca'), false);
  assert.deepEqual(both, h.intro.registrationStars('Anna', 'D’Angelo'));
});

test('review can finish without personal data and exposes no persistence boundary', () => {
  const h = harness(); let completed = 0;
  const props = { first: '', last: '', onFirstChange: () => {}, onLastChange: () => {}, onComplete: () => completed++, onExit: () => {}, preview: true };
  const render = () => h.render(h.intro.RegistrationIntro, props);
  button(render(), 'Fammi vedere').props.onPress(); button(render(), 'Conferma nome').props.onPress(); button(render(), 'Conferma cognome').props.onPress();
  button(render(), 'Torna a VITA').props.onPress(); assert.equal(completed, 1);
});

test('a failed first-access save keeps the form available; pending save cannot submit twice', () => {
  const h = harness(); let completed = 0;
  const props = { first: 'Giulia', last: 'De Luca', onFirstChange: () => {}, onLastChange: () => {}, onComplete: () => completed++, onExit: () => {}, savedIdentity: true, busy: false, submitError: '' };
  const render = () => h.render(h.intro.RegistrationIntro, props);
  button(render(), 'Fammi vedere').props.onPress(); button(render(), 'Conferma nome').props.onPress(); button(render(), 'Conferma cognome').props.onPress();
  props.busy = true; button(render(), 'Iniziamo dalla mia vita').props.onPress(); assert.equal(completed, 0);
  props.busy = false; props.submitError = 'Non ho salvato il nome';
  assert.ok(find(render(), e => e.props?.children === props.submitError));
  button(render(), 'Iniziamo dalla mia vita').props.onPress(); assert.equal(completed, 1);
});

test('actual login mounts introduction before credentials and sends completed tutorial with the names', async () => {
  const h = harness(); const calls: any[] = [];
  Object.assign(h.modules, {
    'react-native-reanimated': { default: { View: 'AnimatedView' } },
    'expo-router': { useRouter: () => ({}), useLocalSearchParams: () => ({}) },
    '@/src/api/client': { api: { register: async (...args: any[]) => { calls.push(args); return { token: 'synthetic', user: { user_id: 'test' } }; } } },
    '@/src/contexts/AuthContext': { useAuth: () => ({ user: null, loading: false, signIn: async () => {} }) },
    '@/src/auth/providersConfig': {
      googleConfiguredForPlatform: () => false,
      appleConfiguredForPlatform: () => false,
      appleProviderReady: () => false,
      notConfiguredMessage: () => 'Integrazione non configurata in questo ambiente',
    },
    '@/src/auth/googleAuth': { useGoogleAuth: () => ({ availability: { status: 'unavailable' } }) },
    '@/src/auth/appleSignIn': {}, '@/src/life-setup/routeAfterAuth': { routeAfterAuth: async () => {} },
    '@/src/life-setup/RegistrationIntro': h.intro, '@/src/utils/errors': { humanizeError: () => 'error' },
  });
  const Login = h.load('../../app/login.tsx').default;
  const render = () => h.render(Login, {});
  find(render(), e => e.props?.testID === 'login-create-account-cta')!.props.onPress();
  const introduction = find(render(), e => e.type === h.intro.RegistrationIntro)!;
  assert.ok(introduction);
  assert.equal(find(render(), e => e.props?.testID === 'login-email-input'), undefined);
  introduction.props.onFirstChange('Giulia'); introduction.props.onLastChange('De Luca'); introduction.props.onComplete();
  assert.equal(find(render(), e => e.props?.testID === 'login-name-input')!.props.value, 'Giulia');
  find(render(), e => e.props?.testID === 'login-email-input')!.props.onChangeText('synthetic@example.com');
  find(render(), e => e.props?.testID === 'login-password-input')!.props.onChangeText('synthetic-only');
  await find(render(), e => e.props?.testID === 'login-submit-button')!.props.onPress();
  assert.deepEqual(calls, [['synthetic@example.com', 'synthetic-only', 'Giulia', 'De Luca', true]]);
});
