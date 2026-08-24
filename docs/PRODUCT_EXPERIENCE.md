# ORA — Product Experience & Design System

Companion to `PRODUCT.md` (what ORA is for) and `ARCHITECTURE.md` (how it is
built). This file owns the rules the interface itself must obey.

Established in **PX1.1 — Product Experience Foundation**.

---

## The binding rule

> **NEVER EXPOSE IMPLEMENTATION STATE WHEN A HUMAN STATE EXISTS.**

ORA's cognitive core produces confidence scores, delivery modes, revision
counters, deferral windows, provider chains. All of them are real, all of them
are load-bearing, and **none of them is something a person can act on**.

Where a human state exists, it is the only thing the interface may show:

| Implementation state | What the user reads |
|---|---|
| `confidence = 0.76` | "ORA vuole che tu confermi questo dato." |
| `gemini-flash-lite-latest` | *(nothing — which model answered is not the user's concern)* |
| `defer_hours = 4` | "Più tardi oggi" · "Domani mattina" |
| `attention_revision = 2` | "ORA ha rivalutato questa cosa." |
| `threshold 90%` | "Prima di aggiungere qualcosa al calendario, ORA ti chiede conferma." |

The failure mode this prevents is subtle and specific: a number the user cannot
evaluate quietly becomes their responsibility. "Soglia 90%" asked someone to
decide whether 90% was a safe bet for writing to their real calendar — a
judgement they had no way to make, standing in for consent they never gave.
That is not transparency. Transparency is telling someone what will happen to
them in terms they hold.

This rule is enforced, not merely documented: `src/shell/px11Foundation.test.ts`
fails the build if these terms reappear on a consumer surface.

---

## Quiet Premium

Quiet Premium is **not** white space, tiny type and empty screens. It is:

- few things, but the right ones;
- strong hierarchy;
- calm surfaces;
- intentional space;
- high legibility;
- discreet feedback;
- no noise;
- no unnecessary exposure of technical complexity.

"Quiet" describes the product's manner, never its legibility. Text small enough
to squint at is not calm — it is just quiet about the wrong thing.

### Theme

**Consumer V1 is light, everywhere.** One constant governs this:
`CONSUMER_LIGHT_ONLY` in `src/theme/ThemeProvider.tsx`.

Dark remains fully implemented — palette, shadows, resolution logic — and is one
boolean away from returning. It is pinned off because a *partially* themed
product is worse than a single-theme one. Roughly forty screens and components
read the static `tokens.color` export inside `StyleSheet.create`, which runs once
at module load and cannot see the provider. While that export defaulted to dark,
those surfaces rendered dark whatever the user chose — which is exactly why
Profilo, Impostazioni and Documenti flipped dark while the navigation rail beside
them stayed light.

Two rules follow, and both are tested:

1. The static token export and the provider must resolve to the **same** scheme.
2. No screen may hardcode a surface colour. `#0E0E12`, `#000`, `#111` and their
   neighbours are palette values, and belong only in `palettes.ts`.

### Accent

Deep Indigo `#3D4A8C` — calm, neither electric blue nor purple. No decorative
colours are introduced outside the semantic set.

---

## Information Architecture 2.0

```
HOME · VITA · ORA · ATTIVITÀ · DOCUMENTI          (+ account, set apart)
```

| Destination | Why it is here |
|---|---|
| **Home** | What matters now. |
| **Vita** | The areas of the user's life ORA knows. Formerly "Contesti" — people have a life, not contexts. |
| **ORA** | The conversation. |
| **Attività** | Where ORA's own questions, updates and actions live. Ships empty in PX1.1; PX1.6 fills it. |
| **Documenti** | Promoted out of the account menu, where a primary surface had been hidden two taps deep. |

**Memoria** left the primary bar. It is a trust-and-configuration surface —
somewhere you go to check what ORA knows about you, not somewhere you go daily.
It stays reachable from Profilo.

**Profilo** is not one of five equal cognitive destinations. On desktop it sits
apart at the foot of the rail, separated by a divider — the gap is the point.

A phone bar has no "apart" position, so it says the same thing the only way a
bar can: **the five destinations carry words, account carries just its icon.**
That is not a compromise made for space, though it did resolve one — six
labelled items genuinely do not fit 375px once labels reach the 12px
readability floor, and the label that should give way is the one that is not a
place you go.

### Adding a destination

Adding a sixth later reshuffles every surface built on five. That is why
Attività ships as a named, empty room now rather than as a menu item bolted on
after PX1.6. **An empty room with a name is honest; a feature announcement
inside a product is not** — hence "Qui troverai le domande, gli aggiornamenti e
le azioni di ORA", never "coming soon", never a roadmap.

The same principle removed the "Prossimamente" group from Profilo. Four
permanently greyed rows (spese, obiettivi, email, banche) made the app look like
a demo of itself and re-advertised, on every visit, four things ORA cannot do.
**A capability appears the day it works.**

---

## Geometry

```
NAVIGATION RAIL (80)  ·  DECISION COLUMN (≤800)  ·  [CONTEXT RAIL (320), reserved]
```

The desktop complaint PX1.1 fixes ("a small column on the left and a huge void
on the right") was never about the column being too narrow. It was about screens
that set no width at all, so their content either stretched edge to edge or
hugged the rail.

Reading measure is a **human constant, not a fraction of the viewport**: past
roughly 800px a line of text stops being comfortable however large the monitor
is. So the column stays put and the *margins* absorb the extra width — equally
on both sides, which is what makes it read as composed rather than pushed aside.

`PageContainer` (`src/components/ui/PageContainer.tsx`) is the single source of
this geometry. The contextual rail is **reserved, not built**: passing no
`contextRail` renders nothing at all — no empty frame, no held-open space, no
invented content. PX1.3+ owns what eventually goes in it.

---

## Dialogs

A dialog is a focused question, not a page. Bounded max width (420 for a simple
choice), one clear question as its title, options in the user's vocabulary, and
a close path that always works.

The snooze dialog is the reference case. It was a text field labelled "Rimanda
(ore)" defaulting to `4`: it asked the user to do arithmetic on their own day —
work the product should be doing — and leaked the backend's unit into a
conversation about their life. It now asks *"Quando vuoi che te lo
riproponga?"* and offers **Più tardi oggi · Domani mattina · Questo weekend ·
Scegli data e ora**.

The wire format is unchanged: `src/components/ui/humanTime.ts` resolves each
choice to the absolute ISO instant the backend already accepted. Nothing about
the contract changed — only what we ask the person.

---

## Developer diagnostics

Provider status, model names and the failover chain are genuinely useful and are
**not deleted** — they are moved out of the consumer product, into
`src/components/dev/DevDiagnostics.tsx`, gated on `__DEV__`.

`__DEV__` is false in any production bundle, so the block is not merely hidden
by styling — it is not built. A person using ORA has no way to act on
"Gemini → OpenAI → Ollama → Emergent": it asks them to hold a mental model of an
inference stack in order to use a life assistant, and quietly makes the
product's own reliability their problem.

---

## Consent surfaces

A consent surface must state **what will happen to the user**, never the
mechanism that decides it. Confidence scores, thresholds and model names are
never consent controls.

PX1.1's calendar audit found this rule broken in the strongest possible way: a
settings toggle offered to add recognised events to the user's real calendar
automatically above a 90% confidence score, and the backend honoured it by
calling the user's own confirmation function on their behalf. See
`ARCHITECTURE.md` § *Calendar write consent* for the fix. The interface now
states the promise plainly:

> Prima di aggiungere, modificare o eliminare qualcosa nel tuo calendario, ORA
> ti chiede sempre conferma.

---

## PX1 roadmap

| Sprint | Scope | Status |
|---|---|---|
| **PX1.1** | Product Experience Foundation | **this batch** |
| PX1.2 | Home 3.0 | deferred |
| PX1.3 | Workspace 2.0 | deferred |
| PX1.4 | ORA Conversation Experience | deferred |
| PX1.5 | Vita / Contexts / Memory trust UX | deferred |
| PX1.6 | Activity / Trust Center | deferred |
| PX1.7 | Documents UX 2.0 | deferred |
| PX1.8 | Profile / Settings / Permissions | deferred |
| PX1.9 | Motion / States / Accessibility polish | deferred |

PX1.1 deliberately builds **the house, not the furniture**: the theme, the
navigation, the geometry and the vocabulary every later sprint will inherit.

---

## What the visual QA found

PX1.1's Chrome pass is recorded here because each finding is a rule, not an
incident. Three of the five were **pre-existing and invisible** while the app
was still half-dark — fixing the theme is what made them legible enough to see.

**Raw confidence, in two places.** Document cards carried a `60%` / `75%` badge
and the detail panel an "Affidabilità NN%" row. Both are the binding rule's own
example: a number the reader cannot act on, quietly asking them to decide how
much of ORA's reading of their own document to believe. Removed. The human
state was already beside them — *Completato*, *In attesa di conferma*, *1 azione
da confermare*.

**Horizontal rows compressed to half their height.** The stats and filter rows
in Documenti sat in a bounded flex column taller than the viewport, so flexbox
shrank them: a 25px box around 51px of content, slicing every label off. A
horizontal scroller must never be vertically compressible — `flexShrink: 0`,
and let the *page* scroll instead.

**Six labelled items do not fit a 375px bar.** Raising navigation labels to the
12px readability floor made "Documenti" truncate. The fix follows the IA rather
than fighting it: account is not a destination, so on phone it is an icon
without a word, and the label weight no longer changes with selection — bold was
wider than the slot, so the label truncated *only while selected*, and the row
reflowed on every tap.

**`<h1>` inside `<h1>`.** React Native Web renders every
`accessibilityRole="header"` as an `<h1>`, so a header role on both a wrapper and
its title emitted nested headings: invalid HTML, a hydration error, and the
heading announced twice. The heading is the title, not the block around it.

**"Later today" at 2am meant 5am.** The human-time helper guarded the evening
but not the small hours. Someone awake at 02:23 does not mean 05:23 — they mean
the day they are about to have. It now snaps to the morning.

Each of these is guarded in `src/shell/px11Foundation.test.ts`.
