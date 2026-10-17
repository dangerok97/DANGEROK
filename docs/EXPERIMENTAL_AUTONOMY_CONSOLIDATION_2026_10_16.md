# ORA — experimental autonomy consolidation (16 October 2026)

> **EXPERIMENT ONLY — NEVER DEPLOY OR MERGE WITHOUT AN EXPLICIT RELEASE GATE.**
> Main app stays on `staging/cloud` (Railway project's `production` environment).
> Unified working branch: `ora/experimental-autonomy-unified-20261016`.

## Verified starting point

- Created from `staging/cloud` on 16 October 2026, after merge of PR #343
  (`e48a149c5c690cb7b71d19c1074c107b64313f25`).
- Initial comparison to `staging/cloud`: **identical** (0 ahead, 0 behind).
- No separate Railway service/environment has been attached to this branch.
- Existing Railway production backend and web were both healthy at the branch cut.
- Retain all newer app integrations, permissions, source provenance, memory and notifications.
- All new changes go to this branch only until explicit production release approval.

## Historical candidates: selective salvage, never blind merges

| Reference | Technical evidence | Decision |
| --- | --- | --- |
| [#279](https://github.com/dangerok97/DANGEROK/pull/279) calendar Core lifecycle | 5/5 model-assisted tests in isolated synthetic owners; built on #220; 109 commits ahead, 361 behind current base when compared | Extract narrowly testable date/weekday, idempotency, natural assent and read-after-write contracts. Never replace existing calendar Core wholesale |
| [#220](https://github.com/dangerok97/DANGEROK/pull/220) autonomy v162 | Last reported candidate failed CI; 84 ahead, 361 behind | Examine durable resume, source refresh and situation checkpoints individually; failures are a stop signal |
| [#212](https://github.com/dangerok97/DANGEROK/pull/212) continuity/outcomes | Previous model evaluation 5/9 scenarios; last head not proven releasable; 73 ahead, 412 behind | Only port independently justified source-validity/recovery guards with new tests |

Git compare can truncate changed files at 300; the counts above are branch-divergence
evidence, **not** a claim that every file was reviewed.

## Live defects to reproduce on the experiment

**CAL-TZ-1: 18:00 displayed as 12:00.** A 20 October 2026 18:00–18:10
synthetic internal ORA appointment was shown as 12:00–12:10 in a remote
browser. This is consistent with formatting in the browser timezone,
not a proven storage mutation. The experimental `eventDisplayTime` helper
displays event-zone wall-clock and falls back to the source offset when a
verified IANA zone is absent. Tests run with both `TZ=America/Chicago` and
`TZ=Europe/Rome`. **Release gate:** reproduce with a real API read-back
of `starts_at`, `ends_at`, `timezone` and compare both calendar and detail
screens; do not claim success based only on chat text.

**SIT-1: unattended physical situation lacks an executable follow-up.**
A synthetic *"panni stesi a Tarquinia"* message created an actual temporary
memory, but the screen said *"Programmazione da recuperare"* and did not
prove an owner-scoped scheduled wake. A stale location clarification also
appeared in updates. Generic Situation goal, attention intent and initial
review exist in mainline already, but do **not** prove useful action.
**Release gate:** fresh synthetic Situation → persisted initial-review wake →
source-grounded follow-up appointment with time and purpose → background
recheck after worker restart → truthful useful estimated/action-now result →
verified delivery admission and device receipt. Missing weather/location
evidence must create an honest blocker, never invented drying times.

**DEL-1: provider accepted is not handset received.** Existing synthetic
source-to-delivery tests prove admission and provider acceptance, not device
delivery. Verify actual transport receipt and safe retries without repeated
notifications.

## Acceptance matrix for the unified branch

Every case must have both a **positive** and a **negative** check:

1. **Source → verified action:** external confirmation may produce one justified
   native calendar event; self-sent/no-event message must not create one.
2. **Calendar:** correct date, timezone, weekday, start/end time; read-after-write;
   duplicate message gives one event; stale/ambiguous edits are rejected.
3. **Temporary Situation:** owner-scoped canonical memory, current live input,
   justified next check, persisted wake, revision fence and evidence-backed
   final instruction (or explicit unavailability). No weather-only assertion
   that clothes are physically dry.
4. **Continuity:** crash, model quota, provider outage, replay, cancellation,
   expired grant, stale source and account isolation. No unbounded retries.
5. **Notifications:** accepted by provider and delivered to device are separate
   states; no duplicate sends, no misleading completion claims.
6. **WhatsApp parity:** the same governed Core and owner authority, only
   capabilities supported by that channel. No silent permissions.
7. **Usability:** no more upfront controls just to begin a normal Situation;
   the UI shows outcome, next check and whether delivery is verified.

## Release gate (all required, no percentage shortcut)

- All branch CI and focused synthetic tests pass on the exact release commit.
- Dedicated AI model evaluation passes **all** selected cases, with versions,
  outcomes and failure diagnostics preserved; no claim of universal intelligence.
- Isolated Railway test service/environment with *synthetic* account and
  nonproduction secrets passes end-to-end; does not use live account tokens.
- Confirmed acceptance on the owner's explicitly authorized account for
  a real calendar/source/Situation workflow with actual persistence and
  notification receipt, without inventing physical observations.
- Explicit manual release decision; merge only specific reviewed files from
  this unified branch after a fresh conflict/security diff review.
- Production does not auto-deploy from this experimental branch.

### Status at branch creation

**Autonomy full release: NOT READY.** Historical calendar evidence is 5/5 in a
synthetic setting, general v162 branch had CI regressions, continuity v162
previously 5/9. No end-to-end *physical Situation outcome + handset receipt*
has been verified on the unified experiment.

### Working rule

Never merge a historical branch wholesale, never represent a timer as an
empirical estimate, never represent a provider's success as device delivery,
never grant broader authority on behalf of a test user. Each recovered
improvement requires a reviewable diff, a failure-reproducing test, and a
confirmed isolated execution. This document is the backlog of record.

## Integration audit — 17 October 2026 (single active lane)

The canonical working branch and only release-candidate PR are
`ora/experimental-autonomy-unified-20261016` / **draft #350**.
Production `staging/cloud` and Railway remain untouched by these commits.
The competing experimental draft #349 was **closed without merge** after
transferring its narrowly reviewed calendar changes; original branches remain
archived as comparison sources, not concurrent development lanes.

### Selective recovery with explicit limits

- **CAL164 no-op local edits, historical #279 / experimental #349**:
  copied into the canonical branch the owner-scoped, fresh-read comparison
  `manual_update_is_noop` and the matching local calendar update path,
  with `test_unified_calendar_noop_v1.py` in the experimental and generic CI.
  Its assertions concern correct no-op semantics, no duplicate writes or wakes,
  expiry/concurrency fences and known vs unknown end times. **This does NOT
  prove that the 18:00 → 12:00 error originated only in display.** The
  actual event read-back, source calendar identity and timezone authority
  remain release blockers.
- **Bounded Situation declaration recovery, historical #220 / experimental
  #348**: **REJECTED after rechecking the current governance code.** The
  helper required `situation_create_missing_source_refs` and
  `situation_create_missing_linked_object_refs` errors, while
  `validate_decision` currently emits `bad_situation_update` and
  `SituationUpdate` already defaults both reference arrays to empty lists.
  Consequently, its tested pure helper did not prove it was reachable from
  a real Core turn. It was briefly evaluated on the experimental branch and
  then reverted; not accepted, not published. No fake checkpoint, Situation
  or notification was created.
- **Continuity from historical #212**: no wholesale runtime copy. Current
  production already contains durable goals, source fences, retry boundaries
  and delivery checks, but the original #212's 5/9 live scenario record is
  insufficient to authorize promoting more of it. Require an independently
  reproducible failing test for each missing behavior.

### Autonomy completion criteria (not a percentage)

1. One external, authorized source change reaches a single verified effect.
2. Calendar retains exact user time/date/source and rejects unwanted edits,
   duplicates, wrong-day labels and stale provider state.
3. An everyday Situation receives a *persisted executable first wake*,
   valid evidence at recheck, a useful answer or honest blocker, and
   stable completion/recovery after a process restart.
4. Transient model failure, quota and partial sources do not invent success,
   consume valid work or loop indefinitely.
5. The existing Delivery pipeline rechecks current subject and authority;
   provider acceptance and actual device delivery are separate evidence.
6. App and WhatsApp share governed capabilities without uncontrolled effects.
7. The same exact candidate tree passes CI, synthetic real-model evaluation,
   an isolated Railway preview, device acceptance and explicit release review.

**Release posture: HOLD.** Focused synthetic correctness is progress, not
evidence of full user autonomy. No production merge, no production Railway
source switch, no automatic account mutations.
