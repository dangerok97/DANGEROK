/**
 * PX1.9 — the polish that is easy to lose again.
 *
 * None of what this sprint fixed was a feature, which is exactly why it will
 * come back if nothing watches it. A colour token drifts one step lighter, a
 * new row lands with a 36px button because that is what the neighbouring file
 * did, a dialog is added without a way to press Escape, a heading is written
 * with `accessibilityRole="header"` and no level and quietly becomes the
 * page's second <h1>. Each of those is invisible in review and obvious to
 * someone using a keyboard, a screen reader, or a phone in the sun.
 *
 * So the assertions here are about properties, not appearances: contrast is
 * recomputed from the palette rather than compared to a hex string, and the
 * tap-target floor is checked as "reads the token" rather than "equals 44".
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { QUIET_MOTION } from './motionTokens.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

/* -------------------------------------------------------------------------- */
/* A — text can be read on the surfaces it sits on                            */
/* -------------------------------------------------------------------------- */
{
  const palette = read('src/theme/palettes.ts');
  const light = palette.slice(palette.indexOf('export const lightColors'));
  const hex = (key: string): string => {
    const m = new RegExp(`\\n\\s*${key}: '(#[0-9A-Fa-f]{6})'`).exec(light);
    assert.ok(m, `light palette must define ${key}`);
    return m![1];
  };

  const lin = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const lum = (h: string) => {
    const n = h.replace('#', '');
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  };
  const ratio = (a: string, b: string) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };

  // Every surface a person reads body text on.
  const backgrounds = ['surface', 'backgroundPrimary', 'backgroundSecondary', 'surfaceWarm'].map(hex);
  // Every token that carries words rather than decoration.
  const texts = ['textPrimary', 'textSecondary', 'textTertiary', 'placeholder', 'warning', 'success', 'error'];

  for (const t of texts) {
    for (const bg of backgrounds) {
      const got = ratio(hex(t), bg);
      assert.ok(
        got >= 4.5,
        `${t} on ${bg} is ${got.toFixed(2)}:1 — body text needs 4.5:1`,
      );
    }
  }

  // Tertiary must still read as a step below secondary, or the hierarchy the
  // whole product leans on collapses into one grey.
  assert.ok(
    ratio(hex('textSecondary'), hex('surface')) > ratio(hex('textTertiary'), hex('surface')),
    'secondary must stay darker than tertiary',
  );
}

/* -------------------------------------------------------------------------- */
/* B — the tap-target floor is a token, not a number someone remembered       */
/* -------------------------------------------------------------------------- */
{
  // The exact controls PX1.9 found under the floor. Each must now read the
  // token, so raising the floor once raises all of them.
  const cases: Array<[string, RegExp]> = [
    ['src/components/home/v3/HomeChrome.tsx', /whyBtn: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/vita/VitaChrome.tsx', /whyBtn: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/activity/ActivityParts.tsx', /whyBtn: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/activity/ActivityParts.tsx', /panelFooter: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/home/v3/HomeSections.tsx', /rowCta: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/home/v3/HomeSections.tsx', /dismiss: \{[\s\S]*?height: tokens\.touch\.min/],
    ['src/components/home/v3/HomeSections.tsx', /footer: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/home/v3/ContextRail.tsx', /navBtn: \{[\s\S]*?height: tokens\.touch\.min/],
    ['src/components/home/v3/ContextRail.tsx', /cell: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/vita/VitaCards.tsx', /openBtn: \{[\s\S]*?minHeight: tokens\.touch\.min/],
    ['src/components/ora/OraComposer.tsx', /iconBtn: \{[\s\S]*?width: tokens\.touch\.min/],
  ];
  for (const [file, re] of cases) {
    assert.ok(re.test(read(file)), `${file}: a control fell back below the tap floor`);
  }

  // The composer's icon controls are controls, not labelled decoration.
  const composer = readCode('src/components/ora/OraComposer.tsx');
  const attach = composer.slice(composer.indexOf('Allega file') - 200, composer.indexOf('Allega file') + 60);
  assert.ok(/accessibilityRole="button"/.test(attach), 'the attach control needs a button role');
}

/* -------------------------------------------------------------------------- */
/* C — motion explains a change, it does not perform one                      */
/* -------------------------------------------------------------------------- */
{
  assert.ok(QUIET_MOTION.micro >= 100 && QUIET_MOTION.micro <= 160, 'micro feedback band');
  assert.ok(QUIET_MOTION.standard >= 180 && QUIET_MOTION.standard <= 240, 'standard transition band');
  assert.ok(QUIET_MOTION.surface >= 200 && QUIET_MOTION.surface <= 280, 'dialog/sheet band');
  assert.ok(QUIET_MOTION.micro < QUIET_MOTION.standard && QUIET_MOTION.standard <= QUIET_MOTION.surface);

  const motion = readCode('src/shell/quietMotion.tsx') + readCode('src/shell/motionTokens.ts');
  for (const banned of ['withSpring', 'springify', 'bounce', 'Easing.elastic', 'Easing.bounce', 'scale']) {
    assert.ok(!motion.includes(banned), `quiet motion must not reach for ${banned}`);
  }
  // Opacity only: nothing may describe a displacement that did not happen.
  assert.ok(!/translate|SlideIn|Zoom/.test(motion), 'the arrival fade must not move anything');

  // Reduce-motion is answered with "already there", never with a faster fade.
  assert.ok(
    /reduced \? 0 :/.test(motion) && /standard === 0/.test(motion),
    'reduce-motion must resolve to no animation at all',
  );

  // The surfaces that swap a skeleton for content all use the same primitive.
  for (const surface of [
    'app/(tabs)/index.tsx',
    'app/(tabs)/contesti.tsx',
    'app/(tabs)/attivita.tsx',
    'app/(tabs)/documenti.tsx',
    'app/(tabs)/profilo.tsx',
  ]) {
    const src = read(surface);
    const usesAppear = src.includes('<Appear>');
    const isHome = surface.endsWith('index.tsx');
    // Home keeps its own arrival; the four dashboards share the fade.
    if (!isHome) assert.ok(usesAppear, `${surface} must fade its content in`);
  }
}

/* -------------------------------------------------------------------------- */
/* D — one level-one heading per page                                         */
/* -------------------------------------------------------------------------- */
{
  // A header without a level renders as <h1> on web. Every page title declares
  // level 1 explicitly; everything under it declares its own level.
  const titled = [
    'src/components/home/v3/HomeChrome.tsx',
    'src/components/vita/VitaChrome.tsx',
    'src/components/activity/ActivityParts.tsx',
    'src/components/documents/LibraryParts.tsx',
    'src/components/account/AccountParts.tsx',
  ];

  for (const file of titled) {
    // Comments stripped, so a sentence about `accessibilityRole` in a doc
    // comment cannot be mistaken for a heading.
    const src = readCode(file);

    // Every heading states its level. Left to itself, React Native Web renders
    // any `accessibilityRole="header"` as <h1>, which is how Home ended up
    // announcing five page titles at once.
    const headers = (src.match(/accessibilityRole="header"/g) || []).length;
    const levels = (src.match(/aria-level=\{\d\}/g) || []).length;
    assert.equal(levels, headers, `${file}: a heading is missing its level`);

    // At most one level-1 per component: a file may hold the page header and
    // the subpage shell, and each of those is one page's title.
    const parts = src.split(/^export function /m).slice(1);
    for (const part of parts) {
      const name = part.slice(0, part.indexOf('(')).trim();
      const ones = (part.match(/aria-level=\{1\}/g) || []).length;
      assert.ok(ones <= 1, `${file}: ${name} declares ${ones} level-1 headings`);
    }
    assert.ok(
      (src.match(/aria-level=\{1\}/g) || []).length >= 1,
      `${file} must name its page`,
    );
  }

  // The logo is a logo. As a header it made every page announce two titles.
  const brand = readCode('src/shell/OraBrand.tsx');
  assert.ok(
    !/accessibilityRole="header"/.test(brand),
    'the brand mark must not compete with the page title',
  );
  assert.ok(brand.includes('accessibilityLabel="ORA"'), 'the mark must still name itself');
}

/* -------------------------------------------------------------------------- */
/* E — the two things the web needs told explicitly                           */
/* -------------------------------------------------------------------------- */
{
  const globals = readCode('src/theme/webGlobals.ts');
  assert.ok(/document\.documentElement\.lang = 'it'/.test(globals), 'the document must declare Italian');
  assert.ok(/:focus-visible/.test(globals), 'a focus ring must exist');
  // Removed without replacement is worse than the browser default.
  assert.ok(
    globals.indexOf(':focus { outline: none; }') < globals.indexOf(':focus-visible'),
    'the outline may be replaced, never simply removed',
  );
  assert.ok(/outline: 2px solid/.test(globals), 'the ring must be thicker than a hairline');

  const layout = readCode('app/_layout.tsx');
  assert.ok(layout.includes('installWebGlobals'), 'the globals must actually be installed');
}

/* -------------------------------------------------------------------------- */
/* F — nothing irreversible happens on one press                              */
/* -------------------------------------------------------------------------- */
{
  const detail = readCode('app/document/[id].tsx');
  assert.ok(detail.includes('ConfirmDialog'), 'deleting a document must ask first');
  // The button opens the question; only the dialog calls the endpoint.
  assert.ok(
    /label="Elimina"[\s\S]{0,160}setConfirmDelete\(true\)/.test(detail),
    'the delete button must open the confirmation, not the deletion',
  );
  assert.ok(
    /onConfirm=\{onDelete\}/.test(detail),
    'the deletion must hang off the confirmation',
  );
  // Archiving is reversible and stays a single press.
  assert.ok(/label="Archivia"/.test(detail) && !/setConfirmArchive/.test(detail));

  const dialog = readCode('src/components/ui/ConfirmDialog.tsx');
  assert.ok(dialog.includes('onRequestClose={onCancel}'), 'Escape must cancel, never confirm');
  assert.ok(/destructive \? 'danger'/.test(dialog), 'a destructive confirm must read as one');
}

/* -------------------------------------------------------------------------- */
/* G — every dialog can be left                                               */
/* -------------------------------------------------------------------------- */
{
  const dialogs = [
    'src/components/account/AccountParts.tsx',
    'src/components/account/PhotoDialog.tsx',
    'src/components/activity/ActivityParts.tsx',
    'src/components/documents/LibraryParts.tsx',
    'src/components/vita/VitaChrome.tsx',
    'src/components/home/quiet/CorrectPriorityModal.tsx',
    'src/components/home/quiet/SnoozeModal.tsx',
    'src/components/ora/LocationPermissionSheet.tsx',
    'src/components/ui/ConfirmDialog.tsx',
  ];
  for (const file of dialogs) {
    const src = read(file);
    const opens = (src.match(/<Modal/g) || []).length;
    const closes = (src.match(/onRequestClose=/g) || []).length;
    assert.ok(opens > 0, `${file} should still hold a dialog`);
    assert.equal(closes, opens, `${file}: a dialog cannot be dismissed with Escape`);
  }
}

/* -------------------------------------------------------------------------- */
/* H — a big surface loads as its own shape                                   */
/* -------------------------------------------------------------------------- */
{
  const detail = readCode('app/document/[id].tsx');
  assert.ok(detail.includes('<DetailSkeleton />'), 'the document detail must load as a skeleton');
  assert.ok(
    !/if \(loading\) return \([\s\S]{0,200}ActivityIndicator/.test(detail),
    'a full page must not load behind a lone spinner',
  );

  const connections = readCode('app/settings.tsx');
  assert.ok(connections.includes('connections-skeleton'), 'connections must load as a skeleton');
  assert.ok(!connections.includes('ActivityIndicator'), 'no lone spinner on a full page');
}

/* -------------------------------------------------------------------------- */
/* I — one press, one request                                                 */
/* -------------------------------------------------------------------------- */
{
  // `setBusy(true)` lands on the next render, so a visible busy state cannot
  // stop the second tap of a double-tap. Measured before the fix: three
  // presses on the documents switch inside one tick sent three PATCHes.
  const guarded = [
    'app/account/preferenze.tsx',
    'app/account/permessi.tsx',
    'app/settings.tsx',
    'src/components/profile/ProfilePhotoSection.tsx',
  ];
  for (const file of guarded) {
    const src = readCode(file);
    assert.ok(src.includes('useInflight'), `${file}: a write is unguarded against double-submit`);
    assert.ok(/guard\(async \(\) =>/.test(src), `${file}: the guard must wrap the write itself`);
  }

  const hook = readCode('src/shell/useInflight.ts');
  // A ref, because it is the only thing that changes fast enough.
  assert.ok(/useRef\(false\)/.test(hook), 'the guard must be a ref, not state');
  assert.ok(/finally \{[\s\S]{0,80}running\.current = false/.test(hook), 'the guard must always release');

  // Home already worked this way; it must keep working this way.
  const home = readCode('app/(tabs)/index.tsx');
  assert.ok(/if \(inflight\.current\) return;/.test(home), 'Home must keep its inflight guard');
}

console.log('PX1.9 polish guards: all assertions passed');
