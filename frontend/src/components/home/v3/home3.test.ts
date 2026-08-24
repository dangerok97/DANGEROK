/**
 * PX1.2 — Home 3.0 contract guards.
 *
 * Run: node --experimental-strip-types src/components/home/v3/home3.test.ts
 *
 * Behaviour is imported and executed where it is pure (action hierarchy,
 * visual derivation, section gating); composition is checked by reading the
 * source, the same technique PX1.1 uses — the regressions worth catching here
 * are things *reappearing* (a hardcoded exhibition, a fourth equal button, a
 * confidence score) rather than a function returning the wrong number.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  primaryActionOf,
  overflowActionsOf,
  relativeDayLabel,
  isQuestion,
  splitSuggestions,
  todayItems,
  allItems,
} from './homeItemView.ts';
import { visualKindFor, visualFor, ALL_VISUAL_KINDS } from './visualKind.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const item = (o: Record<string, unknown> = {}) => ({
  id: 'i1', type: 'generic', title: 't', source_type: 's', source_id: 'x',
  priority: 'today', urgency: 'soon', status: 'open', actions: [], reason_factors: [],
  ...o,
}) as any;

// ---------------------------------------------------------------------------
// F — one primary CTA, everything else demoted
// ---------------------------------------------------------------------------
{
  const withAll = item({
    actions: [
      { kind: 'ignore', label: 'Ignora' },
      { kind: 'open', label: 'Apri' },
      { kind: 'resume', label: 'Continua' },
      { kind: 'snooze', label: 'Rimanda' },
    ],
  });
  const primary = primaryActionOf(withAll);
  assert.equal(primary?.kind, 'resume', 'continuing beats opening');

  const overflow = overflowActionsOf(withAll);
  assert.ok(!overflow.some((a) => a.kind === 'resume'), 'the primary is not repeated');
  for (const dismissive of ['snooze', 'ignore']) {
    assert.ok(
      !overflow.some((a) => a.kind === dismissive),
      `${dismissive} is offered by the card itself, never as a generic action`,
    );
    assert.notEqual(primaryActionOf(item({ actions: [{ kind: dismissive, label: 'x' }] }))?.kind, dismissive,
      `${dismissive} must never become the primary call to action`);
  }

  assert.equal(primaryActionOf(item({ actions: [] })), null, 'no actions, no CTA');
  assert.equal(primaryActionOf(null), null);
}

// ---------------------------------------------------------------------------
// C / K — every card can carry a contextual visual, and it never fails
// ---------------------------------------------------------------------------
{
  // Derived from the backend's own taxonomy, never from words.
  assert.equal(visualKindFor({ type: 'event' }), 'moment');
  assert.equal(visualKindFor({ type: 'payment' }), 'ledger');
  assert.equal(visualKindFor({ type: 'insight' }), 'discovery');
  // Falls back through structural signals, then to a safe default.
  assert.equal(visualKindFor({ source_type: 'calendar' }), 'moment');
  assert.equal(visualKindFor({ type: 'something_new_from_backend' }), 'task');
  assert.equal(visualKindFor(null), 'task', 'a missing item must still get a visual');
  assert.equal(visualKindFor({}), 'task');

  // Every kind resolves to a complete descriptor — no undefined tint or icon
  // can reach a gradient and collapse a card.
  for (const kind of ALL_VISUAL_KINDS) {
    const d = visualFor({ type: kind });
    assert.ok(d.icon, `${kind} needs an icon`);
    assert.equal(d.tint.length, 2, `${kind} needs two gradient stops`);
  }

  const visual = readCode('src/components/home/v3/ContextualCardVisual.tsx');
  assert.ok(visual.includes('imageSource'), 'a real image must be expressible today');
  assert.ok(
    /minHeight:\s*40/.test(visual) && /minWidth:\s*40/.test(visual),
    'the visual needs a floor so a missing size cannot collapse the card',
  );
  assert.ok(
    visual.includes('accessibilityElementsHidden'),
    'the generated fallback is decorative and must be hidden from screen readers',
  );
  assert.ok(visual.includes('cachePolicy'), 'real images must be cached, not refetched');
}

// ---------------------------------------------------------------------------
// D / E — sections disappear rather than invent content
// ---------------------------------------------------------------------------
{
  const sections = readCode('src/components/home/v3/HomeSections.tsx');
  for (const guard of [
    'if (!questions.length) return null;',
    'if (!items.length) return null;',
    'if (!total) return null;',
  ]) {
    assert.ok(sections.includes(guard), `missing empty guard: ${guard}`);
  }

  assert.deepEqual(todayItems([]), [], 'no items, no Oggi');
  assert.deepEqual(allItems(null), []);
  assert.deepEqual(allItems([{ items: [item({ id: 'a' })] }, { items: [item({ id: 'a' })] }]).length, 1,
    'the same item in two priority bands is one card');
}

// ---------------------------------------------------------------------------
// B — no reference content is hardcoded
// ---------------------------------------------------------------------------
{
  // Everything illustrative in the CPO's reference image, which must exist in
  // the product only if the user's own data says so.
  const fromReference = [
    'mostra fotografica', 'Lezione Psicologia', 'Cena con Marco', 'Ristorante Il Faro',
    'Centro Culturale', 'Aula B1', 'Trasloco', 'Marco', 'Francesco',
  ];
  for (const file of [
    'app/(tabs)/index.tsx',
    'src/components/home/v3/HomeSections.tsx',
    'src/components/home/v3/HeroAdesso.tsx',
    'src/components/home/v3/ContextRail.tsx',
    'src/components/home/v3/HomeChrome.tsx',
  ]) {
    const src = read(file);
    for (const literal of fromReference) {
      assert.ok(!src.includes(literal), `${file} hardcodes reference content: "${literal}"`);
    }
  }
}

// ---------------------------------------------------------------------------
// H — no implementation state on a consumer surface
// ---------------------------------------------------------------------------
{
  const rendered = [
    'src/components/home/v3/HeroAdesso.tsx',
    'src/components/home/v3/HomeSections.tsx',
    'src/components/home/v3/ContextRail.tsx',
  ];
  for (const file of rendered) {
    const src = readCode(file);
    for (const leak of ['confidence', 'ranking_version', 'reason_factors', 'importance', 'urgency_hint']) {
      assert.ok(!src.includes(leak), `${file} surfaces implementation state: ${leak}`);
    }
    assert.ok(!/Math\.round\([^)]*\*\s*100\)/.test(src), `${file} renders a raw percentage`);
  }
  // `reason_summary` is the one model-produced string allowed through: it is a
  // human sentence written for the user, not a chain of thought.
  assert.ok(
    read('src/components/home/v3/HeroAdesso.tsx').includes('reason_summary'),
    'Perché ora must use the human summary the backend already provides',
  );
}

// ---------------------------------------------------------------------------
// G — snooze keeps the PX1.1 human dialog
// ---------------------------------------------------------------------------
{
  const home = readCode('app/(tabs)/index.tsx');
  assert.ok(home.includes('SnoozeModal'), 'Home must reuse the PX1.1 snooze dialog');
  assert.ok(!/Rimanda \(ore\)/.test(home), 'the hours input must never come back');
  assert.ok(
    read('src/components/home/quiet/SnoozeModal.tsx').includes('HUMAN_SNOOZE_QUICK_CHOICES'),
    'the dialog still speaks human time',
  );
}

// ---------------------------------------------------------------------------
// I / J — one design, two arrangements
// ---------------------------------------------------------------------------
{
  const home = readCode('app/(tabs)/index.tsx');
  assert.ok(/TWO_COLUMN_MIN\s*=\s*\d+/.test(home), 'the two-column threshold must be explicit');
  assert.ok(home.includes('twoColumn ? ('), 'desktop and phone take different branches');
  assert.ok(home.includes('wideHero'), 'the hero re-composes rather than shrinking');
  // The rail must still be reachable on phone — stacked, not dropped.
  const stacked = home.slice(home.indexOf('twoColumn ? ('));
  assert.ok(stacked.includes('ContextRail'), 'the rail must appear in both branches');
  assert.equal(
    (home.match(/<ContextRail/g) || []).length, 2,
    'exactly one rail per branch — never rendered twice at once',
  );

  // PX1.1's reading column must not have been widened for everyone else.
  const container = read('src/components/ui/PageContainer.tsx');
  assert.ok(container.includes('DECISION_COLUMN_MAX_WIDTH'), 'PageContainer is untouched');
  assert.ok(!home.includes('PageContainer'), 'Home opts out deliberately, it does not redefine it');
}

// ---------------------------------------------------------------------------
// M / N — empty and loading are designed, not accidental
// ---------------------------------------------------------------------------
{
  const chrome = readCode('src/components/home/v3/HomeChrome.tsx');
  assert.ok(chrome.includes('HomeEmptyV3') && chrome.includes('HomeSkeletonV3'));
  assert.ok(
    /non c'è nulla che richieda la tua attenzione/.test(read('src/components/home/v3/HomeChrome.tsx')),
    'the empty state must say nothing is needed, not that something broke',
  );
  assert.ok(chrome.includes('skHeroVisual'), 'the skeleton mirrors the hero it precedes');
}

// ---------------------------------------------------------------------------
// O — existing action contracts are unchanged
// ---------------------------------------------------------------------------
{
  const home = readCode('app/(tabs)/index.tsx');
  for (const call of [
    'api.getHome()', 'api.refreshHome()', 'api.homeAction(',
    'api.acceptSuggestion(', 'api.dismissSuggestion(',
  ]) {
    assert.ok(home.includes(call), `Home 3.0 must keep calling ${call}`);
  }
  // The V2 dual-step navigation contract survives verbatim.
  assert.ok(
    home.includes("['maps', 'navigate', 'open', 'guide', 'study', 'resume', 'confirm']"),
    'the navigate-only vs record-and-navigate split must not drift',
  );
}

// ---------------------------------------------------------------------------
// Questions come from the attention layer, not from guessing
// ---------------------------------------------------------------------------
{
  const ask = { id: 'a', title: 'q', meta: { delivery: 'ask_user' } } as any;
  const plain = { id: 'b', title: 'u' } as any;
  assert.equal(isQuestion(ask), true);
  assert.equal(isQuestion(plain), false, 'absent delivery means update, the safe direction');
  const split = splitSuggestions([ask, plain]);
  assert.equal(split.questions.length, 1);
  assert.equal(split.updates.length, 1);
  assert.deepEqual(splitSuggestions(undefined), { questions: [], updates: [] });
}

// ---------------------------------------------------------------------------
// Human relative dates, never raw ISO
// ---------------------------------------------------------------------------
{
  const iso = (days: number) => {
    const d = new Date(); d.setDate(d.getDate() + days); return d.toISOString();
  };
  assert.equal(relativeDayLabel(iso(0)), 'oggi');
  assert.equal(relativeDayLabel(iso(1)), 'domani');
  assert.equal(relativeDayLabel(iso(5)), '5 giorni');
  assert.equal(relativeDayLabel(iso(-2)), 'in ritardo');
  assert.equal(relativeDayLabel(null), null);
  assert.equal(relativeDayLabel('not-a-date'), null, 'a bad date must not crash a card');
}

// ---------------------------------------------------------------------------
// Visual convergence pass — the CPO's findings, guarded
// ---------------------------------------------------------------------------
{
  const home = readCode('app/(tabs)/index.tsx');
  // A missing section must close the row, not leave a column-wide hole.
  assert.ok(home.includes('function SectionRow'), 'rows must recompose around missing sections');
  assert.ok(
    /if \(!present\.length\) return null;/.test(home),
    'an empty row renders nothing at all — not an empty gap',
  );
  assert.ok(
    /if \(!twoColumn \|\| present\.length === 1\)/.test(home),
    'a single surviving section must take the full width',
  );

  // The hero must not read as a placeholder: warm surface, modest mark.
  const hero = readCode('src/components/home/v3/HeroAdesso.tsx');
  assert.ok(hero.includes('colors.surfaceWarm'), 'the hero has its own warm surface');
  const visual = readCode('src/components/home/v3/ContextualCardVisual.tsx');
  assert.ok(
    /hero: \{ radius: [^,]+, icon: 2\d \}/.test(visual),
    'the hero mark stays small — a large centred glyph reads as an empty slot',
  );
  for (const form of ['formTall', 'formRound', 'formBar', 'horizon']) {
    assert.ok(visual.includes(form), `the composition needs its ${form}`);
  }

  // Updates must carry human time, never a raw timestamp.
  const sections = readCode('src/components/home/v3/HomeSections.tsx');
  assert.ok(sections.includes('agoLabel'), 'updates show how long ORA has held them');
  assert.ok(!/created_at\}/.test(sections), 'no raw ISO timestamp is ever printed');
}

// ---------------------------------------------------------------------------
// Final completion pass
// ---------------------------------------------------------------------------
{
  const rail = readCode('src/components/home/v3/ContextRail.tsx');
  // Days must be reachable, and a tap must not cost a request: the events for
  // the period are already in memory.
  assert.ok(/testID={`rail-day-\${day}`}/.test(rail), 'calendar days must be tappable');
  assert.ok(rail.includes('const byDay = useMemo('), 'events are indexed by day in memory');
  assert.ok(!/fetch\(|api\./.test(rail), 'selecting a day must never trigger a request');
  assert.ok(rail.includes('Nessun impegno per questa giornata'), 'an empty day says so');
  // Selected / today / has-events must not be told apart by colour alone.
  assert.ok(rail.includes('borderColor: colors.accent'), 'the selected day carries a ring');
  assert.ok(rail.includes('accessibilityState={{ selected: isSelected }}'), 'selection is exposed');

  // ORA is a destination on the rail, not a section label.
  const bar = readCode('src/shell/AmbientTabBar.tsx');
  assert.ok(bar.includes('item.center && !isRail ? ('),
    'the circular ORA mark belongs to the phone bar only');

  // Display casing must never rewrite what is stored.
  const account = readCode('src/shell/RailAccount.tsx');
  assert.ok(account.includes('export function titleCase'), 'presentation casing helper exists');
  assert.ok(!/api\.|update|save/i.test(account), 'casing is display-only, never persisted');
}

console.log('PX1.2 Home 3.0 guards: all assertions passed');
