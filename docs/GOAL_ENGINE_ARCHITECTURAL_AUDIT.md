# ORA Goal Engine — Architectural Audit

**Status:** Audit only — no Goal Engine implementation.  
**Date:** 2026-08-05  
**Branch tip audited:** `feature/travel-action-flow` @ `cda5017`  
**Scope:** Intent Engine, Action Engine (incl. Study/Travel), Projects (`action_projects`), Brain / Life Graph / Knowledge, Home V2, Mongo collections.

---

## 1. Current architecture map

```
                         ┌──────────────────────┐
  Free text / Home item  │  Intent Engine       │  backend/intent_engine/
  ─────────────────────► │  classify → Intent   │  NOT persisted as its own collection
                         └──────────┬───────────┘
                                    │ Intent (+ subtype, entities, confidence)
                                    ▼
                         ┌──────────────────────┐
                         │  Action Engine      │  backend/action_engine/
                         │  open → session      │  flows/* + study/ + travel/
                         │  answer → turns      │
                         │  preview / confirm   │
                         └──────────┬───────────┘
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
   action_sessions         action_projects          Domain artifacts
   (conversational)        (AE aggregator)          study_plans / study_sessions
                                                    travel_projects
              │                     │                     │
              │                     ▼                     ▼
              │              life_nodes (goal|trip)   calendars / Google
              │              node_knowledge           documents / reminders
              │              life_edges               decisions (optional)
              ▼                     │                     │
                         ┌──────────▼─────────────────────▼──┐
                         │  Home V2                          │
                         │  adapters → rank → primary_focus  │
                         │  priorities / resume_item         │
                         └───────────────────────────────────┘
```

### Layer summary (today)

| Layer | Package / path | Persists? | Role today |
|-------|----------------|-----------|------------|
| Intent | `backend/intent_engine/` | No dedicated collection; stamped on `action_sessions.meta` and sometimes `decisions` | Classify text → Intent; sole flow router |
| Action Engine | `backend/action_engine/` | `action_sessions` | Guided Q&A; effects; confirm gates for study/travel |
| AE Projects | `backend/action_engine/projects.py` | `action_projects` | Lightweight link aggregator (docs, calendar, reminders, decisions, session_ids) |
| Study domain | `backend/action_engine/study/` | `study_plans`, `study_sessions` | Living study plan + sessions |
| Travel domain | `backend/action_engine/travel/` | `travel_projects` | Living travel project + calendar events |
| Brain | `backend/life_graph/`, `backend/knowledge/` | `life_nodes`, `life_edges`, `node_knowledge` | Graph identity + facts; AE creates `goal` / `trip` nodes |
| Home V2 | `backend/home/` | `home_snapshots`, `home_item_state`, `home_insights` | Aggregate adapters, rank, primary focus, resume |
| Decisions / Action Center | `decisions` + `backend/action_center/` | `decisions`, `decision_action_history` | Ranked work items + action_state machine (orthogonal to AE) |
| Tasks (legacy) | — | `tasks` | Legacy scored tasks; not Goal Engine |

There is **no** `goal_engine/` package, **no** `goals` Mongo collection, and **no** first-class Goal API/UI.

---

## 2. Module responsibilities

### 2.1 Intent Engine (`backend/intent_engine/`)

**Responsibility:** Deterministic (optional LLM enrich) classification of free text / Home item context into a typed `IntentResult`.

| Piece | File | Notes |
|-------|------|-------|
| Models | `models.py` | `IntentResult`, `IntentEntities` (includes free-text field `goal`), thresholds |
| Classifier | `classifier.py` + `knowledge.py` | Pattern KB (IT), scoring |
| Entities | `entities.py` | subject, place, dates, exam, travel period, … |
| Mapping | `mapping.py` | Intent → AE flow / Home type / decision category |
| Service / API | `service.py`, `router.py` | `POST /api/intent/classify` |

**Output contract:** Intent name + subtype + confidence + entities + clarify options.  
**Does not:** own long-lived goals, schedules, sessions, or Home ranking.  
**Relation to Action Engine:** `POST /api/action-engine/open` classifies (or accepts precomputed Intent) then `flow_from_result` → `study|travel|event|medical|admin|generic|clarify` (`docs/INTENT_ENGINE_ARCHITECTURE.md`).

### 2.2 Action Engine (`backend/action_engine/`)

**Responsibility:** Turn a Home priority (or source refs) into a short guided conversation and apply real side effects.

| Piece | File | Notes |
|-------|------|-------|
| Session model | `models.py` | `ActionSession`, turns, `ProjectLink`, effects meta |
| Orchestration | `service.py` | open / answer / back / draft / preview / confirm / complete / merge |
| Flows | `flows/*.py` | Thin registry; study/travel delegate to packages |
| Brain helpers | `brain.py` | `find_similar_goal`, `ensure_brain_node` (creates `life_nodes` type=`goal`), knowledge merges |
| Projects | `projects.py` | CRUD-ish for `action_projects` + merge |
| Effects | `effects.py` | calendar life events, reminders, decisions, study hooks |
| Router | `router.py` | `/api/action-engine/*`, `/api/study-plans/*`, `/api/travel-projects` |

**Persisted session state:** `action_sessions` — answers, turn_history, current_turn, proposed_actions, project link, `brain_node_id`, meta (intent*, study_plan_id, travel_project_id, home_invalidate, next_focus_hint).

**Home / calendar links:**

- Home entry via `home/actions_catalog.py` → guide → `/action/open`; FE `frontend/src/action-engine/ActionEngine.ts`.
- Adapter `home/adapters/action_engine_adapter.py` surfaces active sessions (resume) + projects with `next_focus_hint`.
- Study/Travel Google sync only after **confirm** (`study/google_sync.py`, `travel/google_sync.py`).
- Internal calendar via Life Graph `event` nodes (`effects._create_life_event`).

### 2.3 Projects today (`action_projects`)

**Not a product “Projects” domain.** Explicit comment in `projects.py`: *“lightweight multi-step aggregators (no separate Projects domain).”*

Holds:

- `id`, `user_id`, `title`, `flow`, `status` (`active` / `merged`)
- `session_ids[]`, `brain_node_id`, source refs
- `answers` snapshot
- `linked`: documents, calendar_event_ids, reminder_ids, decision_ids, task_ids, flashcard_doc_ids
- optional `next_focus_hint`, `merge_proposal`, `study_plan_id` / `travel_project_id` (written by study/travel confirm paths)

**Can it represent Goals?** Partially as a bag of links — but it lacks outcome semantics (desired end state, target date as first-class goal fields, progress model, phases, ownership of study/travel domain docs). Study/Travel already outgrew it into dedicated collections.

### 2.4 Brain / Life Graph / Knowledge

| Concern | Owner | Collections |
|---------|-------|-------------|
| Nodes / edges | `life_graph/service.py` | `life_nodes`, `life_edges` |
| Typed facts + provenance | `knowledge/` | `node_knowledge` |
| Node types | `life_graph/types.py` | Includes `NodeType.GOAL`, `TRIP`, `EVENT`, `UNIVERSITY`, … |
| Goal knowledge schema | `knowledge/schemas.py` → `"goal"` | category, target, target_date, progress_pct, motivation, milestones |

**How AE uses Brain today:**

- On open: `ensure_brain_node` always creates/reuses a **`goal`** Life Graph node for the session title (`action_engine/brain.py`).
- Study confirm: `study/brain_links.py` links exam/subject goal + document edges (dedupe keys).
- Travel confirm: `travel/brain_links.py` creates/reuses **`trip`** node (`attributes.kind=travel_project`) + destination/docs/people edges.
- Answers: `record_answer` → knowledge `_extra` keys; completion → `upsert_summary`.

**Home Brain adapter** (`home/adapters/brain.py`) only surfaces unresolved `link_proposals` — not goal nodes as priorities.

### 2.5 Home V2 (`backend/home/`)

| Piece | Role |
|-------|------|
| `adapters/__init__.py` `gather_all` | Fail-soft parallel loaders |
| `ranking.py` | Deterministic `home-rank-1.0` scores + bands |
| `service.py` | Snapshot, primary_focus, priorities, resume_item, situation |
| Persistence | `home_snapshots`, `home_item_state`, `home_insights` |

**Relevant adapters for Goals:**

- `study.py` — `study_plans` (+ doc flashcards/quiz resume)
- `travel.py` — `travel_projects` with phase evolution
- `action_engine_adapter.py` — AE sessions + `action_projects` hints
- `decisions_adapter.py`, `reminders.py`, calendars, documents, …

**Ranking / focus / resume:**

- `primary_focus` = top ranked non-`resume` item.
- `resume_item` = most recently updated `type=resume` (AE session, study draft, travel draft, quiz/flashcards).
- Study/travel contribute type weights (`study` 12, `travel` 15) + meta why-now factors (countdown, phase, sessions today).

**Goals do not appear as a first-class Home type today** — only via study/travel/AE project adapters.

### 2.6 Study & Travel flows (Goal-candidate data)

| Aspect | Study | Travel |
|--------|-------|--------|
| Intent | `study` (+ `exam_preparation`) | `travel` (+ `vacation`) |
| Domain model | `StudyPlan` / `StudySessionItem` | `TravelProject` |
| Collections | `study_plans`, `study_sessions` | `travel_projects` |
| Lifecycle | draft → awaiting_confirmation → active/paused/completed/cancelled | same pattern |
| Links | `action_session_id`, `project_id`→`action_projects`, `brain_node_id`, `source_priority_id` | same |
| Idempotency | hash(user, source_priority, exam_name, exam_date) | hash(user, source_priority, dest, start, end) |
| Confirm outputs | sessions schedule, tools, optional Google events, Brain goal | calendar events propose→confirm, maps, prep, Brain trip |
| Home | plan cards + draft resume | phase cards + draft resume |
| Detail UI | `frontend/app/study-plan/[id].tsx` | `frontend/app/travel-project/[id].tsx` |

These are **the strongest Goal Engine precursors**: durable outcomes with progress/phase, not just conversation state.

### 2.7 Mongo collections inventory (Goal-relevant)

| Collection | Indexed / owned by | Goal relevance |
|------------|--------------------|----------------|
| `users` | `server.py` | Owner |
| `action_sessions` | `ActionEngineService.ensure_indexes` | Conversation; meta links to plans |
| `action_projects` | same | Weak aggregator / merge candidates |
| `study_plans` / `study_sessions` | `StudyPlanService.ensure_indexes` | Study goal artifact |
| `travel_projects` | `TravelProjectService.ensure_indexes` | Travel goal artifact |
| `life_nodes` / `life_edges` | `server.py` | Brain identity (`goal`, `trip`, `event`, …) |
| `node_knowledge` | `server.py` | Facts on nodes (goal schema exists) |
| `decisions` / `decision_action_history` | `server.py` + Action Center | Work items; Intent fields when opened |
| `tasks` | `server.py` | Legacy — do not reuse as Goals |
| `documents` / `calendar_event_drafts` | documents services | Linked materials |
| `reminders` | AE effects | Operational follow-ups |
| `ingestion_events` / connector / vault | connectors | External calendar events |
| `home_snapshots` / `home_item_state` / `home_insights` | HomeService | Ranking UX state |
| `memories`, `link_proposals`, `context_snapshots` | Brain ecosystem | Context, not Goals |
| **`goals`** | — | **Does not exist** |

---

## 3. Overlaps

| Overlap | Where | Problem |
|---------|-------|---------|
| “Goal” word overloaded | Intent entity `goal`; Life Graph `NodeType.GOAL`; `find_similar_goal` searching **`action_projects` first**; study Brain “goal” node; product Goal Engine (missing) | Mental model collision; dedupe logic mixes project aggregator with Brain goals |
| Three durable “plan” shapes | `action_projects` + `study_plans` + `travel_projects` | Home can show AE project hint **and** study/travel card for same outcome |
| Brain node type inconsistency | AE open → always `goal` node; Travel confirm → prefers `trip` | Same travel flow may attach session to `goal` then enrich/link a `trip` |
| Session vs domain draft | `action_sessions` + plan `status=draft` both drive Home resume | Multiple resume candidates for one user journey |
| Decisions vs AE outcomes | `effects` may create decisions; Decision Engine / Action Center manage `action_state` | Parallel “what should I do” tracks without a parent Goal |
| Knowledge goal schema unused as product API | `schemas.py` `"goal"` fields | Progress lives in study/travel models, not Knowledge |
| Intent `project` → AE `generic` | `mapping.py` | Intent name “project” is not a durable Project/Goal |

---

## 4. Risks

1. **Premature unification** — folding Study/Travel into a generic Goal table too early breaks confirm gates, Google sync, phase/progress, and existing tests (`test_study_action_flow.py`, `test_travel_action_flow.py`).
2. **Duplicating Home surfaces** — a new Goals adapter without dedupe keys vs study/travel adapters → double primary_focus candidates.
3. **Treating `action_projects` as Goals** — insufficient semantics; merge/title similarity is fragile (`find_similar_goal` substring match).
4. **Treating Life Graph nodes as Goals** — Brain must stay representation (`life_graph/service.py` contract: never ranks/decides). Product Goal lifecycle (active/paused/completed, Home ranking) belongs outside pure graph writes.
5. **Intent Engine scope creep** — Intent must stay classification-only; persisting goals there would couple routing to lifecycle.
6. **Action Engine as Goal store** — sessions are ephemeral conversations; stuffing goal progress into sessions creates orphaned state after complete/cancel.
7. **Silent dual writers** — if Goal Engine and StudyPlanService both update “progress” without a single owner, Home ranking drifts.
8. **Migration without feature flags** — cutting over collections in place risks production-like local data and Emergent preview DBs.
9. **Naming collision in APIs** — `/goals` vs Life Graph filter `type=goal` vs Intent entity `goal`.
10. **Action Center confusion** — `action_center` mutates decision action_state only; must not be conflated with Action Engine or Goal Engine.

---

## 5. Recommended data model (proposal only — not implemented)

### 5.1 Principle

Introduce a **first-class Goal** as the durable outcome object. Keep Intent as classifier, Action Engine as conversational execution, Study/Travel models as **typed goal payloads** (or linked artifacts), Brain as graph identity + facts, Home as read-model.

### 5.2 Proposed collection: `goals`

```text
goals {
  id: "goal_…"
  user_id: string
  title: string
  kind: "study" | "travel" | "event" | "medical" | "admin" | "generic" | …  // aligns with AE flow / Intent
  status: "draft" | "active" | "paused" | "completed" | "cancelled"
  outcome_summary: string?          // desired end state in user language
  target_date: ISO?                 // exam date / trip end / deadline
  start_date: ISO?                  // trip start / plan start
  priority_hints: { urgency?, band? } // optional; Home still recomputes
  progress: { ratio?, phase?, label?, updated_at? }  // denormalized for Home
  links: {
    brain_node_id?: string          // life_nodes id (goal|trip|…)
    action_project_id?: string      // optional AE aggregator
    study_plan_id?: string
    travel_project_id?: string
    decision_ids?: string[]
    document_ids?: string[]
    calendar_refs?: string[]        // life event ids and/or google ids (opaque)
  }
  source: {
    intent?: string
    intent_subtype?: string
    source_type?: string
    source_id?: string
    home_item_id?: string
    idempotency_key?: string
  }
  created_at, updated_at, completed_at?
}
```

Indexes (non-destructive, later): `(user_id, status, updated_at)`, `(user_id, kind)`, unique sparse `(user_id, source.idempotency_key)`, `(user_id, links.study_plan_id)`, `(user_id, links.travel_project_id)`.

### 5.3 What Goals are / are not

| Goals ARE | Goals are NOT |
|-----------|----------------|
| Durable user outcomes (“Pass Psicologia exam”, “Vacation to X”) | Intent classification results |
| Parent pointer for study/travel/admin artifacts | Replacement for `action_sessions` turns |
| Source of truth for Home “outcome priority” identity | Full schedule blobs (sessions stay in `study_sessions`) |
| Soft-linked to one Brain node | Duplicate of all Knowledge properties |

### 5.4 Typed artifacts remain

- Keep `study_plans` / `study_sessions` and `travel_projects` as **specialized engines** owned by their packages.
- Goal holds `links.study_plan_id` / `links.travel_project_id` + denormalized `progress`/`phase` for Home.
- Optionally later: `payload_ref` polymorphism; **do not** merge tables in phase 1.

### 5.5 `action_projects` destiny

- Keep as AE-internal link bag during conversation / merge UX.
- After confirm: Goal becomes canonical; `action_projects` may store `goal_id` or be marked `status=attached`.
- Do **not** rename `action_projects` → Goals.

### 5.6 Brain linkage

- One primary `brain_node_id` per Goal.
- Study → prefer Life Graph `goal` (+ university edges as today).
- Travel → prefer Life Graph `trip` (fix AE open to avoid creating a throwaway `goal` when Intent is travel — implementation phase).
- Knowledge stores facts; Goal stores lifecycle/progress for product.

---

## 6. Recommended data flow

```
User text / Home card
        │
        ▼
[Intent Engine] ── IntentResult (ephemeral)
        │
        ▼
[Action Engine open] ── action_sessions (active)
        │                 ensure/link Goal (draft) + Brain node
        │                 optional action_projects for merge UX
        ▼
 answers / preview
        │
        ▼
[confirm] ── StudyPlanService / TravelProjectService (unchanged writers)
        │       set Goal.status=active, links.*, progress snapshot
        │       Brain edges (existing brain_links)
        │       Google sync (existing)
        ▼
[Home V2] ── goals adapter (or study/travel adapters read Goal id for dedupe)
        │       primary_focus / priorities use Goal identity
        │       resume still from action_sessions / draft plans
        ▼
User acts on plan/session (complete session, phase change)
        │
        ▼
Domain service updates artifact → Goal Engine projection updates progress
        │
        ▼
Home refresh (home_invalidate)
```

### Boundary rules (single recommended architecture)

| Module | Stays responsible for | Must not own |
|--------|----------------------|--------------|
| **Intent Engine** | Classification, entities, clarify, flow mapping | Goal CRUD, progress, Home ranking |
| **Action Engine** | Sessions, turns, confirm gates, calling domain services + Goal hooks | Long-term progress after session ends |
| **Goal Engine (new)** | Goal identity, status lifecycle, links, progress projection, dedupe/idempotency across kinds | Conversational UI turns; Google API calls; Intent scoring |
| **Projects (`action_projects`)** | Session-time aggregation + merge proposals | Product-facing Goal list |
| **Study / Travel packages** | Typed plans, sessions, maps, sync, domain validation | Competing global Goal IDs (they *link* to Goal) |
| **Brain** | Nodes/edges/knowledge facts | Home ranking; Goal status machine |
| **Home V2** | Read adapters + ranking + resume | Creating Goals (except via actions that call AE/Goal APIs) |

### How Home should read Goals

- Prefer one adapter `home/adapters/goals.py` **or** extend study/travel adapters to emit `meta.goal_id` + shared `dedupe_key=goal:{id}`.
- Ranking inputs: Goal `target_date` / phase / progress + existing type weights.
- `primary_focus` can be a Goal-backed HomeItem; detail routes remain `/study-plan/{id}` or `/travel-project/{id}` via links.
- Resume stays session/draft oriented (`type=resume`), not a second Goal card.

### How flows update a Goal

1. **open** → create/find Goal `draft`, attach `action_session_id`.
2. **answer** → optional title/entity patches on Goal (not full rewrite).
3. **confirm** → domain artifact created; Goal → `active` + links + progress.
4. **session complete / travel phase tick / plan pause** → domain service notifies Goal projection (same process call; no dual HTTP).
5. **cancel** → Goal `cancelled` if no other artifacts; else detach session only.

### Avoiding duplicates

- Idempotency keys already on study/travel — **promote to Goal.source.idempotency_key** (same hash or parent hash).
- Home `dedupe_key` must include `goal_id` once present; suppress raw `ae_proj_*` when Goal exists.
- `find_similar_goal` should search **Goals** (and Brain labels), not title-substring on `action_projects` alone.
- One Brain node per Goal; study/travel `brain_links` receive `existing_brain_node_id` from Goal.

---

## 7. Migration strategy (Study / Travel → Goals without breaking)

### Constraints

- Non-destructive Mongo changes only.
- Keep existing APIs (`/api/study-plans/*`, `/api/travel-projects`, `/api/action-engine/*`) working.
- Preserve confirm-before-Google invariants.
- Feature flag e.g. `GOAL_ENGINE_ENABLED=0` default until adapters proven.

### Phases of data migration

**M0 — Shadow (read-only projection)**  
- On study/travel confirm (and optionally open), upsert `goals` row from existing fields.  
- No Home consumer yet. Backfill script for active `study_plans` / `travel_projects`.

**M1 — Link fields**  
- Add `goal_id` on `study_plans`, `travel_projects`, `action_sessions.meta`, optional `action_projects.goal_id`.  
- Writers remain Study/Travel services; Goal Engine provides `upsert_from_artifact`.

**M2 — Home dedupe**  
- Adapters attach `meta.goal_id`; ranking dedupe collapses AE project + plan cards.  
- Still no separate Goals UI required.

**M3 — Goal as Home source of truth for identity**  
- Goals adapter can emit the card; study/travel adapters emit only operational children (today’s session) **or** remain but with identical dedupe keys.

**M4 — Optional API surface**  
- `GET /api/goals`, `GET /api/goals/{id}` for FE; mutations still go through AE/domain for study/travel.

**Do not (in migration):**

- Drop `study_plans` / `travel_projects`.
- Rewrite Intent or replace Action Engine.
- Auto-merge Goals by fuzzy title without user confirm (reuse merge-proposal UX).

---

## 8. Phased implementation plan

| Phase | Deliverable | Exit criteria |
|-------|-------------|---------------|
| **P0 Audit** | This document | Architecture agreed |
| **P1 Goal package skeleton** | `backend/goal_engine/` models + service upsert + indexes; flag off; no UI | Unit tests for upsert/idempotency; no Home change |
| **P2 Wire Study/Travel confirm** | Set `goal_id` on confirm/open; shadow goals | Existing study/travel pytest green; goals rows appear |
| **P3 Fix Brain open path** | Travel opens attach/create `trip` not generic `goal`; Goal.brain_node_id canonical | brain_links tests / travel suite green |
| **P4 Home dedupe** | `meta.goal_id` + ranking dedupe; suppress duplicate AE project cards | Home V2 tests updated; no double cards |
| **P5 Progress projection** | Session complete / phase recompute updates Goal.progress | Home shows consistent countdown/progress |
| **P6 API + minimal FE** | Read APIs; optional Goals section or reuse plan screens | Lint/typecheck; manual verify |
| **P7 Generic goals** | event/admin/medical confirm creates Goal without study/travel tables | Effects write Goal links |

**First concrete intervention (recommended):** **P1 + P2 shadow Goal upsert on Study/Travel confirm only** — zero UX change, proves identity/idempotency, enables later Home dedupe.

---

## 9. Necessary tests

| Area | Tests to add / extend |
|------|------------------------|
| Goal upsert idempotency | Same study confirm twice → one Goal; `links.study_plan_id` stable |
| Travel confirm | Goal kind=travel, links.travel_project_id, brain trip id |
| Open resume | Active session keeps same `goal_id` |
| Home dedupe | Fixture with action_project + study_plan + goal → single ranked card |
| Ranking | Goal-backed study near exam still ranks in today/critical bands |
| Brain non-dup | Confirm does not create second goal/trip node when Goal.brain_node_id set |
| Intent unchanged | `test_intent_engine` corpus still maps flows; no Goal side effects in classify |
| AE regression | `test_action_engine.py`, study/travel suites remain green with flag on/off |
| Migration backfill | Script dry-run creates Goals for N active plans without mutating plans |
| Negative | Cancelled session without confirm → Goal cancelled or never activated |

Prefer pytest near domain (`test_goal_engine.py`) plus Home fixtures in `test_home_v2.py`.

---

## 10. Final recommended decision

### Single recommended architecture

**Add a Goal Engine as a thin lifecycle/identity layer between Action Engine confirm paths and Home — do not replace Intent, Action Engine, Study/Travel domain models, or Brain.**

| Concern | Decision |
|---------|----------|
| **Intent Engine** | Stays classification + mapping only |
| **Action Engine** | Stays conversational executor + confirm orchestration; calls Goal upsert |
| **Goal Engine** | Owns `goals` collection: identity, status, links, progress projection, cross-kind dedupe |
| **Projects (`action_projects`)** | Remain AE-internal aggregators/merge; link to Goal; never product Goals |
| **Study / Travel** | Remain specialized artifacts; gain `goal_id`; keep owning schedule/maps/sync |
| **Brain** | One node per Goal (`goal` or `trip`); Knowledge for facts; no ranking |
| **Home** | Reads Goals (directly or via adapters with `goal_id` dedupe); resume stays session/draft |
| **Decisions / Action Center** | Optional links under Goal; not Goal substitutes |
| **Duplicates** | Idempotency key + `goal_id` dedupe_key + Brain node reuse |
| **Migration** | Shadow Goals from Study/Travel → link fields → Home dedupe → APIs; never break confirm/Google |

### Explicit non-goals for v1

- No chatbot Goal coach.
- No collapsing all Mongo artifacts into one document.
- No Emergent-only dependency.
- No production deploy / destructive DB wipe as part of introduction.

### Success definition (when implementation happens later)

A user completing “Organizza esame” or “Organizza vacanza” ends with **one Goal identity** visible to Home, one Brain node, one domain artifact, and zero duplicate priority cards — while Study/Travel engines keep working unchanged for scheduling and sync.

---

## Appendix A — Key file index

| Path | Why it matters |
|------|----------------|
| `backend/intent_engine/mapping.py` | Intent → flow |
| `backend/intent_engine/models.py` | Intent contract |
| `backend/action_engine/service.py` | open/confirm orchestration |
| `backend/action_engine/brain.py` | similar goal + ensure Brain node |
| `backend/action_engine/projects.py` | `action_projects` |
| `backend/action_engine/study/models.py` | StudyPlan |
| `backend/action_engine/study/plan_service.py` | draft/confirm |
| `backend/action_engine/study/brain_links.py` | Study Brain |
| `backend/action_engine/travel/models.py` | TravelProject |
| `backend/action_engine/travel/project_service.py` | draft/confirm |
| `backend/action_engine/travel/brain_links.py` | Travel Brain |
| `backend/life_graph/types.py` | `GOAL` / `TRIP` types |
| `backend/knowledge/schemas.py` | goal property schema |
| `backend/home/service.py` | primary_focus / resume |
| `backend/home/ranking.py` | scores |
| `backend/home/adapters/study.py` | Study Home |
| `backend/home/adapters/travel.py` | Travel Home |
| `backend/home/adapters/action_engine_adapter.py` | AE Home |
| `docs/INTENT_ENGINE_ARCHITECTURE.md` | Intent docs |
| `docs/ACTION_ENGINE_ARCHITECTURE.md` | AE docs |
| `docs/HOME_V2_ARCHITECTURE.md` | Home docs |
| `docs/STUDY_ACTION_FLOW_ARCHITECTURE.md` | Study docs |
| `docs/TRAVEL_ACTION_FLOW_ARCHITECTURE.md` | Travel docs |

## Appendix B — Glossary

| Term | Meaning in this audit |
|------|------------------------|
| Intent | Classification result (ephemeral) |
| Action session | Conversational AE state |
| Action project | AE link aggregator (`action_projects`) |
| Study/Travel project/plan | Domain durable artifact |
| Brain goal node | `life_nodes.type == "goal"` |
| **Goal (proposed)** | Product outcome identity in `goals` |

---

*End of audit. No application code was modified for this document.*
