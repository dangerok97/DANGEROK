/**
 * Final hardening — the things a phone build would discover the hard way.
 *
 * Everything guarded here was found by measuring, not by reading: a sixth slot
 * in a five-destination bar, one address rendering two different screens, a
 * signed-out link ending on "your session expired", a keyboard offset that
 * counted the notch twice, a library that kept polling from behind whichever
 * tab you were actually looking at.
 *
 * The common shape of all of them is that they are invisible on a desktop
 * browser with a warm session and a fast network, and unmissable on a phone.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { AMBIENT_ACCOUNT_ITEM, AMBIENT_NAV_ITEMS } from './navItems.ts';
import { loginHrefFor, safeNextTarget } from './nextTarget.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

/* -------------------------------------------------------------------------- */
/* A — five destinations, and account is not one of them                      */
/* -------------------------------------------------------------------------- */
{
  assert.equal(AMBIENT_NAV_ITEMS.length, 5, 'the product has five destinations');
  assert.deepEqual(
    AMBIENT_NAV_ITEMS.map((i) => i.route),
    ['index', 'contesti', 'ora', 'attivita', 'documenti'],
    'order is the order people move through them',
  );
  assert.equal(AMBIENT_NAV_ITEMS.filter((i) => i.center).length, 1, 'ORA anchors the centre');
  assert.equal(AMBIENT_NAV_ITEMS.find((i) => i.center)?.route, 'ora');
  assert.ok(
    !AMBIENT_NAV_ITEMS.some((i) => i.route === AMBIENT_ACCOUNT_ITEM.route),
    'account must not sit among the destinations',
  );

  // The bar renders the five and nothing else. It used to append the account
  // item, which is precisely what made Profilo read as a sixth place to go.
  const bar = readCode('src/shell/AmbientTabBar.tsx');
  const phone = bar.slice(bar.indexOf('GlassContainer glassRole="tabBar"'));
  assert.ok(phone.includes('{primaryItems}'), 'the bar renders the destinations');
  assert.ok(
    !phone.includes('renderItem(AMBIENT_ACCOUNT_ITEM)'),
    'the phone bar must not carry a sixth slot for the account',
  );
}

/* -------------------------------------------------------------------------- */
/* B — one address, one screen                                                */
/* -------------------------------------------------------------------------- */
{
  const layout = readCode('app/(tabs)/_layout.tsx');
  // One declaration at a time: a window of characters after the name would
  // spill into the next screen and read its `href` instead of this one's.
  const screens = layout.split('<Tabs.Screen').slice(1);
  const declOf = (name: string) => {
    const d = screens.find((x) => x.includes(`name="${name}"`));
    assert.ok(d, `no screen declared for ${name}`);
    const stop = d!.indexOf('/>');
    return stop >= 0 ? d!.slice(0, stop) : d!;
  };
  const hidden = (name: string) => declOf(name).includes('href: null');

  // Profilo keeps its route and leaves the navigation.
  assert.ok(hidden('profilo'), 'Profilo must not be a tab');
  // `app/ora/index.tsx` owns `/ora`; the tab screen shared the address and
  // rendered a different, thinner page depending on how you arrived.
  assert.ok(hidden('ora'), 'the shadowed ORA tab screen must stay out of the navigation');
  assert.ok(hidden('memoria'), 'Memoria is a trust surface, not a destination');
  assert.ok(hidden('aggiungi'), 'Aggiungi is not a destination');

  // ...and the bar sends people to the real one.
  const bar = readCode('src/shell/AmbientTabBar.tsx');
  assert.ok(
    /routeName === 'ora'[\s\S]{0,120}router\.push\('\/ora'/.test(bar),
    'pressing ORA must open the conversation, not a second entry page',
  );

  // The four that remain are navigable.
  for (const name of ['index', 'contesti', 'attivita', 'documenti']) {
    assert.ok(!hidden(name), `${name} must remain a destination`);
  }
}

/* -------------------------------------------------------------------------- */
/* C — the account is always reachable, without a tab                         */
/* -------------------------------------------------------------------------- */
{
  const entry = readCode('src/shell/AccountEntry.tsx');
  assert.ok(
    /bp === 'desktop'[\s\S]{0,40}return null/.test(entry),
    'the rail already answers this on desktop; do not ask twice',
  );
  assert.ok(entry.includes("router.push('/(tabs)/profilo'"), 'it must lead to the account');
  assert.ok(/tokens\.touch\.min/.test(entry), 'and be reachable with a thumb');

  // Every ambient surface a phone can be on carries it.
  for (const file of [
    'src/components/home/v3/HomeChrome.tsx',
    'src/components/vita/VitaChrome.tsx',
    'src/components/activity/ActivityParts.tsx',
    'src/components/documents/LibraryParts.tsx',
  ]) {
    assert.ok(readCode(file).includes('<AccountEntry'), `${file} must offer the account`);
  }
}

/* -------------------------------------------------------------------------- */
/* D — "I don't know yet" is not "no"                                         */
/* -------------------------------------------------------------------------- */
{
  const gate = readCode('src/shell/AuthGate.tsx');
  // Hydrating must never be treated as signed out — that is the whole bug.
  assert.ok(
    /const anonymous = !loading && !user/.test(gate),
    'anonymous may only be concluded once hydration has finished',
  );
  assert.ok(/if \(loading \|\| anonymous\)/.test(gate), 'hydration shows a holding state');
  assert.ok(gate.includes('loginHrefFor'), 'a signed-out visitor is sent to sign in');
  // Login itself cannot be gated, or nobody could ever sign in.
  assert.ok(/PUBLIC_PREFIXES[\s\S]{0,80}'\/login'/.test(gate), 'login must stay public');
  // One redirect per destination, or the replace stacks on every render.
  assert.ok(/sent\.current === pathname/.test(gate), 'the redirect must fire once');

  const root = readCode('app/_layout.tsx');
  assert.ok(/<AuthGate>[\s\S]*<Stack/.test(root), 'the gate must wrap the whole stack');
}

/* -------------------------------------------------------------------------- */
/* E — where you were going survives the detour                               */
/* -------------------------------------------------------------------------- */
{
  assert.equal(safeNextTarget('/document/doc_1'), '/document/doc_1');
  assert.equal(safeNextTarget('/goal-workspace/lop_1'), '/goal-workspace/lop_1');
  assert.equal(safeNextTarget('/account/privacy'), '/account/privacy');
  assert.equal(safeNextTarget('%2Fdocument%2Fdoc_1'), '/document/doc_1');

  // Anything that could leave the app, or send someone in a circle.
  for (const hostile of [
    '//evil.example.com',
    '/\\evil.example.com',
    'https://evil.example.com',
    'javascript:alert(1)',
    '%2F%2Fevil.example.com',
    '/etc/passwd',
    '/login',
    '/login?next=/login',
    '/life-setup',
    'document/doc_1',
    null,
    '',
  ]) {
    assert.equal(safeNextTarget(hostile), null, `must refuse: ${hostile}`);
  }
  // Double-encoding must not smuggle a host through.
  assert.equal(safeNextTarget(encodeURIComponent('%2F%2Fevil.example.com')), null);

  assert.equal(loginHrefFor('/document/doc_1'), '/login?next=%2Fdocument%2Fdoc_1');
  assert.equal(loginHrefFor('//evil.example.com'), '/login');
  assert.equal(loginHrefFor(null), '/login');

  // Life Setup still wins: a destination is honoured only after the gate.
  const gate = readCode('src/life-setup/gate.ts');
  const fn = gate.slice(gate.indexOf('export async function routeByLifeSetupGate'));
  assert.ok(
    fn.indexOf("'/life-setup'") < fn.indexOf('safeNextTarget'),
    'an incomplete Life Setup must still take precedence over any next target',
  );
  assert.ok(fn.includes('safeNextTarget(next)'), 'the target is validated again on the way out');
}

/* -------------------------------------------------------------------------- */
/* F — nothing dead-ends when there is no history                             */
/* -------------------------------------------------------------------------- */
{
  // A page opened from a link has nothing behind it; every back must name a
  // destination of its own rather than trusting the stack.
  const fallbacks: Array<[string, RegExp]> = [
    ['src/components/account/AccountParts.tsx', /canGoBack\(\)[\s\S]{0,120}replace\('\/\(tabs\)\/profilo'/],
    ['app/document/[id].tsx', /canGoBack\(\)[\s\S]{0,120}replace\('\/\(tabs\)\/documenti'/],
  ];
  for (const [file, re] of fallbacks) {
    assert.ok(re.test(readCode(file)), `${file}: back must have somewhere to go`);
  }
}

/* -------------------------------------------------------------------------- */
/* G — the notch is counted once                                              */
/* -------------------------------------------------------------------------- */
{
  const ora = readCode('src/components/ora/OraConversationScreen.tsx');
  assert.ok(ora.includes('KeyboardAvoidingView'), 'the composer must stay above the keyboard');
  assert.ok(
    !/keyboardVerticalOffset=\{insets\.top/.test(ora),
    'FocusScreen already consumes the top inset — adding it again pushes the composer off',
  );
  // The product's three conversation-shaped surfaces agree with each other.
  for (const file of [
    'src/components/ora/OraConversationScreen.tsx',
    'src/life-setup/LifeSetupConversationScreen.tsx',
    'app/login.tsx',
  ]) {
    // Raw, not comment-stripped: one of these files contains a `/*` inside a
    // string that makes naive stripping swallow half the module.
    assert.ok(
      /behavior=\{Platform\.OS === 'ios' \? 'padding' : undefined\}/.test(read(file)),
      `${file}: keyboard avoidance must be the iOS-only padding behaviour`,
    );
  }
}

/* -------------------------------------------------------------------------- */
/* H — a phone does not poll from behind another screen                       */
/* -------------------------------------------------------------------------- */
{
  const docs = readCode('app/(tabs)/documenti.tsx');
  assert.ok(/if \(!focused\) return;/.test(docs), 'polling must stop when the tab is not focused');
  assert.ok(/polls\.current >= MAX_POLLS/.test(docs), 'a stuck document must not poll forever');
  assert.ok(/const MAX_POLLS = \d+/.test(docs), 'the ceiling must be a named number');
  // Coming back, or pulling to refresh, starts the watch over.
  assert.ok(/polls\.current = 0;/.test(docs), 'refreshing must reset the watch');
}

/* -------------------------------------------------------------------------- */
/* I — the app opens as itself                                                */
/* -------------------------------------------------------------------------- */
{
  const app = JSON.parse(read('app.json')).expo;
  // Light-only product: "automatic" hands iOS's native chrome — keyboard,
  // action sheets, alerts — a dark appearance over a warm light app.
  assert.equal(app.userInterfaceStyle, 'light', 'the product is light-only');
  const splash = (app.plugins || []).find(
    (p: unknown) => Array.isArray(p) && String(p[0]).includes('splash'),
  ) as [string, { backgroundColor?: string }] | undefined;
  assert.ok(splash, 'the splash screen must be configured');
  assert.notEqual(
    splash![1].backgroundColor,
    '#000000',
    'a black splash flashes before a warm light first screen',
  );
  assert.equal(app.orientation, 'portrait');
  assert.ok(app.ios?.bundleIdentifier && app.android?.package, 'identifiers must survive');
}

/* -------------------------------------------------------------------------- */
/* J — the accessibility work of PX1.9 is still standing                      */
/* -------------------------------------------------------------------------- */
{
  // The new mobile surfaces obey the same floors as everything else.
  for (const file of ['src/shell/AccountEntry.tsx', 'src/shell/AmbientTabBar.tsx']) {
    const src = read(file);
    assert.ok(/tokens\.touch\.min/.test(src), `${file} must use the shared tap floor`);
  }
  const bar = read('src/shell/AmbientTabBar.tsx');
  assert.ok(bar.includes('accessibilityRole="tab"'), 'destinations announce themselves as tabs');
  assert.ok(bar.includes('accessibilityState={{ selected: focused }}'), 'and say which one is current');
  // The guards PX1.9 installed must still exist to be run.
  readFileSync(resolve(FRONTEND, 'src/shell/px19.test.ts'), 'utf8');
}

console.log('Mobile hardening guards: all assertions passed');
