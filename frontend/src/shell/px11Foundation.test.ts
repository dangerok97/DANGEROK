/**
 * PX1.1 — Product Experience Foundation contract guards.
 *
 * Run: node --experimental-strip-types src/shell/px11Foundation.test.ts
 *
 * Two kinds of assertion live here:
 *
 *  - real behaviour, imported and executed (navigation model, human-time
 *    resolution, token resolution);
 *  - source guards, which read a file and assert on what it does NOT contain.
 *
 * The second kind exists because the regressions PX1.1 fixes are all things
 * *reappearing*: a dark colour hardcoded into one screen, a provider name
 * creeping back into consumer settings, another "Prossimamente" row. Those
 * cannot be caught by rendering one component in isolation — the same
 * technique the V2.9.x backend suites use for their hardcoding audits.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { AMBIENT_ACCOUNT_ITEM, AMBIENT_NAV_ITEMS } from './navItems.ts';
import { DECISION_COLUMN_MAX_WIDTH, CONTEXT_RAIL_WIDTH } from './constants.ts';
import {
  HUMAN_SNOOZE_QUICK_CHOICES,
  HUMAN_SNOOZE_CHOICES,
  laterToday,
  thisWeekend,
  tomorrowMorning,
} from '../components/ui/humanTime.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');

/**
 * Source with comments removed — the guards below judge what the product
 * *renders*, not what a comment says about it. Without this, a comment
 * explaining "the Prossimamente group is gone" fails the assertion that
 * Prossimamente is gone. Same correction the V2.9.x backend audits needed.
 */
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

// ---------------------------------------------------------------------------
// D / E / F / G — Information Architecture 2.0
// ---------------------------------------------------------------------------
{
  const labels = AMBIENT_NAV_ITEMS.map((i) => i.label);
  assert.deepEqual(
    labels,
    ['Home', 'Vita', 'ORA', 'Attività', 'Documenti'],
    'primary navigation must be exactly the five cognitive destinations, in order',
  );

  // G — Documenti is a destination, not a row inside the account screen.
  assert.ok(
    AMBIENT_NAV_ITEMS.some((i) => i.route === 'documenti'),
    'Documenti must be a primary destination',
  );

  // E — Memoria is deliberately NOT primary.
  assert.ok(
    !AMBIENT_NAV_ITEMS.some((i) => i.route === 'memoria'),
    'Memoria must not be a primary destination — it is a trust surface',
  );
  // ...but must still be reachable, from Profilo.
  const profilo = read('app/(tabs)/profilo.tsx');
  assert.ok(
    profilo.includes("router.push('/(tabs)/memoria')"),
    'Memoria must remain reachable from Profilo',
  );

  // F — account is separate from the five, and reachable.
  assert.equal(AMBIENT_ACCOUNT_ITEM.route, 'profilo');
  assert.ok(
    !AMBIENT_NAV_ITEMS.some((i) => i.route === 'profilo'),
    'Profilo must not sit among the primary destinations',
  );
  const bar = read('src/shell/AmbientTabBar.tsx');
  assert.ok(
    bar.includes('railAccount') && bar.includes('AMBIENT_ACCOUNT_ITEM'),
    'the desktop rail must render the account item in its own bottom area',
  );

  // Every destination needs an accessible label and a distinct icon pair.
  for (const item of [...AMBIENT_NAV_ITEMS, AMBIENT_ACCOUNT_ITEM]) {
    assert.ok(item.accessibilityLabel?.length, `${item.key} needs an accessibility label`);
    assert.ok(item.icon && item.iconActive, `${item.key} needs both icon states`);
  }
}

// ---------------------------------------------------------------------------
// A / N — one theme, no dark leak
// ---------------------------------------------------------------------------
{
  const tokensSrc = read('src/theme/tokens.ts');
  assert.ok(
    /color:\s*colorsFromPalette\(lightColors\)/.test(tokensSrc),
    'the static token export must resolve light — ~40 screens read it at module load',
  );
  assert.ok(
    /shadow:\s*getShadows\('light'\)/.test(tokensSrc),
    'static shadows must match the static palette',
  );

  const provider = read('src/theme/ThemeProvider.tsx');
  assert.ok(
    provider.includes('CONSUMER_LIGHT_ONLY'),
    'the light-only decision must be one explicit, reversible constant',
  );
  assert.ok(
    /if\s*\(CONSUMER_LIGHT_ONLY\)\s*return\s*'light';/.test(provider),
    'scheme resolution must short-circuit to light while consumer V1 is light-only',
  );

  // N — the surfaces that used to flip dark must not hardcode a dark colour.
  // (#0E0E12 / #16161C / #1A1A22 are the dark palette's own values.)
  const darkLiteral = /#0[Ee]0[Ee]12|#16161[Cc]|#1[Aa]1[Aa]22|#000\b|#111\b/;
  for (const file of [
    'app/(tabs)/profilo.tsx',
    'app/(tabs)/documenti.tsx',
    'app/settings.tsx',
    'app/(tabs)/attivita.tsx',
  ]) {
    assert.ok(!darkLiteral.test(readCode(file)), `${file} must not hardcode a dark surface colour`);
  }
}

// ---------------------------------------------------------------------------
// B / C — provider diagnostics are not consumer surface
// ---------------------------------------------------------------------------
{
  const settings = readCode('app/settings.tsx');
  for (const name of ['Gemini', 'OpenAI', 'Ollama', 'Emergent']) {
    assert.ok(
      !settings.includes(name),
      `consumer settings must not name the model provider "${name}"`,
    );
  }
  assert.ok(
    !/AI Provider/i.test(settings),
    'consumer settings must not present an "AI Provider" section',
  );

  // C — the diagnostics still exist, but only where __DEV__ is true.
  const dev = read('src/components/dev/DevDiagnostics.tsx');
  assert.ok(
    /if\s*\(!__DEV__\)\s*return null;/.test(dev),
    'dev diagnostics must be gated so they are not built into a consumer bundle',
  );
  assert.ok(dev.includes('Gemini'), 'the diagnostics themselves are kept, not deleted');
}

// ---------------------------------------------------------------------------
// H — no product roadmap inside the account screen
// ---------------------------------------------------------------------------
{
  const profilo = readCode('app/(tabs)/profilo.tsx');
  assert.ok(!/PROSSIMAMENTE/i.test(profilo), '"Prossimamente" must not appear in Profilo');
  assert.ok(!/In arrivo/i.test(profilo), 'no "In arrivo" placeholder rows');
  for (const gone of ['Dashboard spese', 'Banche & Wallet', 'Email & Messaggi']) {
    assert.ok(!profilo.includes(gone), `${gone} must not be advertised as a future capability`);
  }
}

// ---------------------------------------------------------------------------
// I / J — snooze speaks human time, and still speaks ISO to the backend
// ---------------------------------------------------------------------------
{
  const modal = readCode('src/components/home/quiet/SnoozeModal.tsx');
  assert.ok(!/Rimanda \(ore\)/.test(modal), 'the "(ore)" label must be gone');
  assert.ok(!modal.includes('snooze-hours'), 'the raw hours input must be gone');
  assert.ok(!/keyboardType="number-pad"/.test(modal), 'no numeric keypad for a moment in time');

  // J — every quick choice resolves to a real future instant, and the payload
  // stays exactly what the backend already accepted: an ISO string.
  const now = new Date('2026-08-24T10:00:00+02:00');
  assert.equal(HUMAN_SNOOZE_CHOICES.length, 4);
  assert.equal(HUMAN_SNOOZE_QUICK_CHOICES.length, 3, 'three quick choices plus a custom picker');
  for (const choice of HUMAN_SNOOZE_QUICK_CHOICES) {
    const target = choice.resolve(now);
    assert.ok(target instanceof Date, `${choice.id} must resolve to a Date`);
    assert.ok(target!.getTime() > now.getTime(), `${choice.id} must be in the future`);
    assert.ok(
      !Number.isNaN(Date.parse(target!.toISOString())),
      `${choice.id} must serialise to a valid ISO instant`,
    );
  }

  // "Later today" must never mean the middle of the night — at either end.
  const lateEvening = new Date('2026-08-24T22:30:00+02:00');
  const bounced = laterToday(lateEvening);
  assert.equal(bounced.getHours(), 9, 'late-evening "più tardi oggi" rolls to tomorrow morning');
  assert.ok(bounced.getDate() !== lateEvening.getDate());

  // Found in Chrome QA: at 02:23 the naive +3h proposed 05:23 — still night.
  // Someone awake in the small hours means later in the day they are about to
  // have, so it snaps forward to the morning of the SAME day.
  const smallHours = new Date('2026-08-24T02:23:00+02:00');
  const snapped = laterToday(smallHours);
  assert.equal(snapped.getHours(), 9, '"più tardi oggi" at 02:23 must not propose 05:23');
  assert.equal(snapped.getDate(), smallHours.getDate(), 'it is still the same day');
  assert.ok(snapped.getTime() > smallHours.getTime());

  assert.equal(tomorrowMorning(now).getHours(), 9);
  assert.equal(thisWeekend(now).getDay(), 6, '"questo weekend" resolves to a Saturday');
  // Said on a Saturday, it means the next one — never "now".
  const saturday = new Date('2026-08-29T10:00:00+02:00');
  assert.equal(saturday.getDay(), 6);
  assert.ok(thisWeekend(saturday).getTime() > saturday.getTime());
}

// ---------------------------------------------------------------------------
// K — calendar settings cannot re-open an unattended write
// ---------------------------------------------------------------------------
{
  const settings = readCode('app/settings.tsx');
  assert.ok(
    !settings.includes('calendar_auto_add_enabled'),
    'consumer settings must not offer to enable unattended calendar writes',
  );
  assert.ok(
    !settings.includes('calendar_auto_add_threshold') && !/soglia/i.test(settings),
    'a confidence threshold is an implementation state, never a consent control',
  );
  assert.ok(
    /chiede sempre conferma/i.test(settings),
    'the calendar section must state the confirmation promise in human terms',
  );
}

// ---------------------------------------------------------------------------
// L — desktop geometry
// ---------------------------------------------------------------------------
{
  assert.ok(
    DECISION_COLUMN_MAX_WIDTH >= 720 && DECISION_COLUMN_MAX_WIDTH <= 840,
    'the decision column must stay inside the agreed 720–840 reading band',
  );
  assert.ok(
    CONTEXT_RAIL_WIDTH >= 280 && CONTEXT_RAIL_WIDTH <= 360,
    'the reserved contextual rail must stay inside the agreed 280–360 band',
  );

  const container = read('src/components/ui/PageContainer.tsx');
  assert.ok(
    container.includes("alignSelf: 'center'"),
    'the column must centre in the space the shell leaves it, not hug the rail',
  );
  // §12 — the contextual rail is reserved, never filled with invented content.
  assert.ok(
    /if\s*\(!isDesktop\s*\|\|\s*!contextRail\)\s*return column;/.test(container),
    'no rail frame may render when there is nothing real to put in it',
  );

  // The screens that had no column at all now have one. Profilo still uses the
  // shared container; Documenti moved to the dashboard composition the later
  // PX1.x surfaces share — a bounded, centred column beside a real rail. What
  // PX1.1 was protecting is that neither screen is full-bleed and neither
  // invents a rail, so the assertion checks the property rather than which
  // component happens to provide it.
  assert.ok(
    read('app/(tabs)/profilo.tsx').includes('PageContainer'),
    'profilo must use the shared column',
  );
  const documenti = read('app/(tabs)/documenti.tsx');
  const docMax = Number(/const PAGE_MAX_WIDTH = (\d+)/.exec(documenti)?.[1]);
  const docRail = Number(/const RAIL_WIDTH = (\d+)/.exec(documenti)?.[1]);
  assert.ok(docMax > 0 && docMax <= 1400, 'documenti must bound its column');
  assert.ok(documenti.includes("alignSelf: 'center'"), 'documenti must centre its column');
  assert.ok(
    docRail >= 280 && docRail <= 360,
    'documenti must keep the contextual rail inside the agreed band',
  );
}

// ---------------------------------------------------------------------------
// M — mobile navigation must not regress into the desktop rail
// ---------------------------------------------------------------------------
{
  const bar = read('src/shell/AmbientTabBar.tsx');
  assert.ok(
    bar.includes("const isRail = bp === 'desktop'"),
    'the rail must remain desktop-only',
  );
  assert.ok(
    bar.includes('AMBIENT_BAR_HEIGHT') && bar.includes('GlassContainer'),
    'the floating phone bar must survive PX1.1',
  );
  assert.ok(bar.includes('testID="ambient-tab-bar"'), 'mobile bar testID must be stable');
  assert.ok(bar.includes('testID="ambient-rail"'), 'desktop rail testID must be stable');
}

// ---------------------------------------------------------------------------
// Human-state rule — no implementation state in what the user reads
// ---------------------------------------------------------------------------
{
  // The literal leaks PX1.1 was asked to remove, checked across the consumer
  // surfaces this sprint touched.
  const forbidden = [
    'attention_revision',
    'defer_hours',
    'confidence',
    'ImpactAssessment',
    'AttentionDecision',
    'LifeChangeSignal',
    'reasoning_epoch',
  ];
  for (const file of [
    'app/(tabs)/attivita.tsx',
    'app/(tabs)/profilo.tsx',
    'src/components/home/quiet/SnoozeModal.tsx',
  ]) {
    const src = readCode(file);
    for (const term of forbidden) {
      assert.ok(!src.includes(term), `${file} must not surface "${term}" to the user`);
    }
  }

  // Attività says what it holds, in the user's own terms, and never announces
  // a roadmap. PX1.1 shipped it as a named empty room and asserted the future
  // tense; PX1.6 built the room, so the same promise is now made in the
  // present. The rule that mattered — describe it, do not advertise it —
  // is what the assertion keeps.
  const attivita = readCode('app/(tabs)/attivita.tsx');
  assert.ok(!/coming soon|prossimamente|in arrivo/i.test(attivita));
  assert.ok(
    /Qui trovi le domande, gli aggiornamenti e le azioni di ORA\./.test(
      readCode('src/components/activity/ActivityParts.tsx'),
    ),
    'Attività must describe what it holds, in Italian',
  );
  assert.ok(
    /Non c'è nulla che richieda la tua attenzione\./.test(
      readCode('src/components/activity/ActivityParts.tsx'),
    ),
    'the empty state must be a calm statement, not a blank page',
  );
}

// ---------------------------------------------------------------------------
// Chrome QA findings — regressions caught with the app running, guarded here
// so they cannot come back silently.
// ---------------------------------------------------------------------------
{
  // 1. Horizontal scrollers were being vertically compressed by the flex
  //    column around them: the stats row rendered 25px tall around 51px of
  //    content, slicing every label off. Pre-existing, and invisible while the
  //    screen was still dark and low-contrast.
  // PX1.7 removed both of Documenti's horizontal scrollers — the stats strip
  // became the rail's summary panel and the filter chips became selects — so
  // the rule is now checked where such a scroller actually survives. Every
  // horizontal ScrollView in the app must still declare the guard; the crush
  // is invisible until a label is sliced in half.
  const scrollerFiles = [
    'src/components/workspace/WorkspaceParts.tsx',
    'app/(tabs)/documenti.tsx',
  ];
  for (const file of scrollerFiles) {
    const src = read(file);
    const horizontals = (src.match(/^\s*horizontal/gm) || []).length;
    if (!horizontals) continue;
    assert.ok(
      /flexGrow:\s*0,\s*flexShrink:\s*0/.test(src),
      `${file} has a horizontal scroller and must declare flexShrink: 0`,
    );
  }

  // 2. Raw confidence was surfacing in two places in Documents — a percentage
  //    badge on every card, and an "Affidabilità NN%" row in the detail panel.
  //    Both are implementation state the reader cannot act on.
  assert.ok(
    !/Math\.round\([^)]*confidence[^)]*\)/.test(readCode('app/(tabs)/documenti.tsx')),
    'no confidence percentage on document cards',
  );
  assert.ok(
    !/Affidabilità/.test(readCode('src/components/documents/DocumentUtilityPanel.tsx')),
    'no raw reliability score in the document detail panel',
  );

  // 3. The phone bar must not truncate a primary destination. Two things make
  //    "Documenti" fit at the 12px floor and must stay true: the account slot
  //    is icon-only (it is not a destination), and the label weight is
  //    constant so the row does not reflow — and widen — when selected.
  const bar = readCode('src/shell/AmbientTabBar.tsx');
  assert.ok(bar.includes('const iconOnly = isAccount && !isRail;'),
    'the phone account affordance stays icon-only');
  assert.ok(
    /fontWeight:\s*isRail\s*\?\s*\(focused\s*\?\s*'600'\s*:\s*'400'\)\s*:\s*'500'/.test(bar),
    'bar label weight must not change with selection — bold overflows the slot',
  );
  // The account slot must keep a real tappable size; `flex: 0` collapsed it to
  // zero width and made the only route to the account untappable.
  assert.ok(
    /barAccount:\s*\{[^}]*flexBasis:\s*44[^}]*minWidth:\s*44/s.test(bar),
    'the account slot needs an explicit basis/minWidth, never `flex: 0`',
  );
}

console.log('PX1.1 foundation guards: all assertions passed');
