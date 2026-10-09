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
import { aggiornamentoScaduto, elencoAggiornamenti } from './aggiornamenti.ts';

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
  assert.ok(
    visual.includes('generating ? <View style={styles.generating}'),
    'queued/generating visuals need a visible non-blocking state',
  );

  const sectionsCode = readCode('src/components/home/v3/HomeSections.tsx');
  assert.ok(
    (sectionsCode.match(/imageSource=\{item\.visual\?\.status === 'ready'/g) || []).length >= 2,
    'Oggi and Più avanti must reuse ready contextual images, not fall back to abstract placeholders',
  );

  const visualService = read('../backend/visuals/service.py');
  assert.ok(
    visualService.includes('status in {"queued", "generating", "missing", "failed"}') &&
      visualService.includes('attempts < MAX_ATTEMPTS'),
    'interrupted or transiently failed image jobs must be resumed instead of remaining placeholders',
  );

  const visualProviders = read('../backend/visuals/providers.py');
  assert.ok(
    visualProviders.includes('GeminiSecondaryImageProvider') &&
      visualProviders.includes('"gemini2": GeminiSecondaryImageProvider()'),
    'Home image generation must fall through to the configured second Gemini account',
  );
}

// ---------------------------------------------------------------------------
// D / E — sections disappear rather than invent content
// ---------------------------------------------------------------------------
{
  const sections = readCode('src/components/home/v3/HomeSections.tsx');
  for (const guard of [
    // V3.1 — the questions section now carries two kinds of row: real blockers
    // and suggestions. What PX1.2 was protecting is that it vanishes when it
    // has nothing, so the guard follows the section rather than the old shape.
    'if (!questions.length && !open.length) return null;',
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
// Agent updates are outcomes/problems, never scheduling theatre
// ---------------------------------------------------------------------------
{
  const sections = readCode('src/components/home/v3/HomeSections.tsx');
  assert.ok(sections.includes("work.has_real_activity"), 'ORA-si-e-mossa badge requires real activity');
  assert.ok(sections.includes("work.problem"), 'overdue/failed autonomous work has an attention state');
  assert.ok(!sections.includes("<Text style={{ fontWeight: '700' }}>Rilevato: </Text>"),
    'why_now must not be presented as if it were an observed fact');
  assert.ok(sections.includes("<Text style={{ fontWeight: '700' }}>Perché conta: </Text>"),
    'the reason a goal matters is labelled as a reason');
}

// ---------------------------------------------------------------------------
// O — existing action contracts are unchanged
// ---------------------------------------------------------------------------
{
  const home = readCode('app/(tabs)/index.tsx');
  for (const call of [
    'api.getHome()', 'api.refreshHome()', 'api.homeAction(',
    'api.dismissSuggestion(',
  ]) {
    assert.ok(home.includes(call), `Home 3.0 must keep calling ${call}`);
  }
  assert.ok(!home.includes('api.acceptSuggestion('), 'Opening a suggestion must not consume it');
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
  assert.ok(
    hero.includes('const showVisual = visualReady || visualGenerating') &&
      hero.includes('{showVisual ? ('),
    'the hero must not reserve a fake photo panel after image providers have failed',
  );
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
  // Home events are already in memory; manually saved events also remain
  // available for days beyond Home's short upcoming window.
  assert.ok(/testID={`rail-day-\${day}`}/.test(rail), 'calendar days must be tappable');
  assert.ok(rail.includes('const byDay = useMemo('), 'events are indexed by day in memory');
  assert.ok(rail.includes('api.homeDayEvents(dayKey)'), 'saved commitments reload for any selected day');
  assert.ok(rail.includes('api.homeMonthDays(monthKey)'), 'saved commitments mark their day after navigating months');
  const eventForm = readCode('src/components/calendar/CalendarEventForm.tsx');
  assert.ok(eventForm.includes('api.createHomeEvent('), 'the shared form persists its event');
  assert.ok(eventForm.includes('Calendario ORA'), 'the storage destination is clear');
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


// V143 — stale alerts must disappear without deleting recurring memories.
{
  const now = Date.now();
  const expired = new Date(now - 86400000).toISOString();
  const future = new Date(now + 86400000).toISOString();
  assert.equal(aggiornamentoScaduto(expired), true);
  assert.equal(aggiornamentoScaduto(future), false);
  const rows = elencoAggiornamenti({
    opportunities: [
      { id: 'old-birthday', title: 'Compleanno', why_now: 'Ricorrenza', created_at: expired,
        valid_until: expired, sources: ['Memoria'] },
      { id: 'future-deadline', title: 'Impegno', why_now: 'Entro domani', created_at: expired,
        valid_until: future, sources: ['Calendario'] },
    ],
  } as any);
  assert.deepEqual(rows.map(x => x.id), ['future-deadline']);
  assert.equal(rows[0].quando, expired, 'creation timestamp not confused with event date');
  assert.equal(rows[0].scade, future, 'expiry is explicit');
}


// v144: the update is a truthful situation console, not a cryptic agent task.
{
  const view = readCode('src/components/home/v3/UpdateNextStep.tsx');
  const client = readCode('src/api/client.ts');
  const detail = readCode('app/aggiornamento/[id].tsx');
  const conversation = readCode('src/components/ora/OraConversationScreen.tsx');
  assert.ok(view.includes('situation.followup_status') && view.includes('situation.notify_when'));
  assert.ok(view.includes('situation.last_checked_at'), 'actual last check must be distinguishable from a scheduled check');
  assert.ok(view.includes("situationDecision('stop_alerts')"), 'user must be able to stop alerts');
  assert.ok(view.includes("situationDecision('resolved')"), 'physical completion must be explicit');
  assert.ok(view.includes('Non ancora · Rispondi a ORA') && view.includes('È cambiata · Spiega a ORA'));
  assert.ok(client.includes('stopSituationAlerts:'));
  assert.ok(detail.includes('<UpdateNextStep a={a} />'), 'same situation response remains in details');
  assert.ok(conversation.includes('initialDraft') && conversation.includes('useState((initialDraft'), 'draft must not auto-submit');
}


// v145 — a saved link to a closed September trip is not a new decision.
{
  const detail = readCode('app/aggiornamento/[id].tsx');
  assert.ok(detail.includes('e?.status !== 410'),
    'Gone must render as no longer active, not an action prompt');
  assert.ok(detail.includes('non ti chiederà di risolvere un evento già passato'),
    'the user needs an understandable lifecycle message');
}


// v146 — information-only notices are not fictitious pending missions.
{
  const result = elencoAggiornamenti({
    opportunities: [
      {
        id: 'notice_for_today', title: 'Consegna prevista oggi', why_now: 'È indicata una previsione',
        informational_only: true, sources: ['email'], created_at: '2026-10-09T04:21:00+02:00',
        valid_until: '2027-10-09T23:59:00+02:00',
      },
      {
        id: 'explicit_investigation', title: 'Una discrepanza da approfondire',
        why_now: 'Le fonti non coincidono', informational_only: false,
        what_ora_can_do: 'Posso verificare due fonti disponibili', sources: ['email'],
      },
    ],
  } as any);
  const info = result[0];
  const actionable = result[1];
  assert.equal(info.solo_informazione, true);
  assert.equal(info.lavoro, undefined, 'an informational notice cannot automatically start a verification');
  assert.equal(info.azione?.kind, 'route');
  assert.equal(info.azione?.params?.opportunityId, 'notice_for_today',
    'the optional follow-up must keep the exact original identity');
  assert.equal(info.azione?.params?.entry, 'opportunity');
  assert.ok(!String(info.azione?.params?.draft).includes('Consegna prevista oggi'),
    'personal information must not be copied into query parameters');
  assert.equal(actionable.solo_informazione, false);
  assert.equal(actionable.lavoro, 'verify');
  assert.equal(actionable.azione?.kind, 'verify');

  const view = readCode('src/components/home/v3/UpdateNextStep.tsx');
  assert.ok(view.includes('aggiornamento-solo-informativo'));
  assert.ok(view.includes('Una segnalazione, non un compito'));
  assert.ok(view.includes('Una previsione non è la prova'));
  const route = readCode('app/ora/index.tsx');
  assert.ok(route.includes("opportunityId && entry !== 'opportunity'"),
    'explicit user-initiated follow-up must not redirect back to the detail');
}


// v147 — a synthetic bank balance is NEVER disposable cash, and a generic
// Action Engine admin hint is not a real payable bill / Daily Focus.
{
  const financeUI = readCode('app/conti-e-denaro.tsx');
  const financeAPI = readCode('src/api/client.ts');
  const source = readCode('app/conti-e-denaro.tsx');
  assert.ok(financeUI.includes('CONTO DI PROVA'), 'demo bank label must be unambiguous');
  assert.ok(financeUI.includes('Saldo simulato (non reale)'),
    'simulated balance must not read "Disponibile"');
  assert.ok(financeAPI.includes('simulato?: boolean'));
  assert.ok(source.includes('rileggi-email-economiche'));
  assert.ok(source.includes('api.reviewFinancialEmailSources()'));
  const adapter = readCode('../backend/home/adapters/action_engine_adapter.py');
  assert.ok(adapter.includes('if not actionable_refs:'));
  assert.ok(adapter.includes('"admin": "activity"'),
    'admin flow is not itself evidence of a bill');
}
