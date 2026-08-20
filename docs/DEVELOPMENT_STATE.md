# ORA — Development State

## V2.8.3a — Provider Reliability & Error Taxonomy

- Provider order remains Gemini → OpenAI → Ollama → Emergent.
- `LLMNotConfigured` now means only that no provider is enabled/configured;
  exhaustion of a configured chain raises `LLMProviderUnavailable` with
  bounded sanitized attempt kinds.
- External quota/rate/timeout/network/auth/model/protocol failures are typed
  and fail over. Unknown internal ORA/adapter errors fail fast and cannot be
  hidden by another provider.
- Recent failures drive an in-memory, per-process cooldown. There is no Redis,
  polling, blocking sleep or additional provider call. Status is a passive
  snapshot (`unknown`, `healthy`, `degraded`, `cooldown`, `disabled`).

## V2.8.3 — Memory Proposal & Governed Learning

Final provider-real gate: explicit Memory authorization now remains authoritative after
an empty bounded lookup; correction/forget must retrieve the governed Memory ref and reuse
its canonical `identity_key`. A terminal runtime guard blocks unpersisted Memory claims if
the model exhausts its reasoning budget. Provider-real PROMOTE, temporary/inference
isolation, cross-session correction/supersession and targeted Forget are green.

| Item | Stato |
|------|--------|
| `MemoryCandidate` AI-owned, optional, bounded | **implemented** |
| Governance PROMOTE/CLARIFY/REJECT/SUPERSEDE/FORGET | **implemented** |
| Temporary Situation → no durable Memory | **enforced** |
| Tentative/inferred/device evidence → no silent promotion | **enforced** |
| User-scoped correction, history, revision, logical forget | **implemented** |
| Same-turn idempotency / cross-turn learning | **implemented** |
| Context Broker cross-session read of promoted Memory | **implemented** |
| Stage A Memory existence index / Stage B governed target metadata | **implemented, bounded** |
| Persist-before-claim and post-write result consistency | **enforced** |
| Second LLM / domain router / new dependency | **none** |
| Live gate on canonical local backend `:8000` | **passed** |

Last updated: 2026-08-18 (V2.8.3a provider reliability)

## V2.8.2 — Context Broker V3

| Item | Stato |
|------|--------|
| `ContextNeed` AI-owned e backward-compatible | **implemented** |
| Life Context source registry | **implemented** |
| Profile / Memory / Situation / Life OS / Goals / file / calendar | **bounded adapters** |
| Presence automatica | **forbidden; capability required** |
| Authority, provenance, conflicts, diversity, budget | **preserved/enforced** |
| Stage A minimized + Situation detail signal | **implemented** |
| Source failure honesty + safe observability | **implemented** |
| Second LLM/domain router/new dependency | **none** |
| Deterministic core regression | **246 passed** |
| Real-provider generality/conflict eval | **4 passed** |
| Final product QA | **passed in integrated browser** |

Last updated: 2026-08-17 (Google Login V2 multipiattaforma — uncommitted)

## Google Login V2 — GIS web + native SDK (this batch)

| Item | Stato |
|------|--------|
| Web Google Identity Services lazy/popup | **implemented** |
| iOS/Android `@react-native-google-signin/google-signin` | **implemented; device not tested** |
| Login missing config → no crash; Email/Register available | **covered by regression test** |
| Settings link/unlink via same adapter | **implemented** |
| JWT persistence atomic before user/routing | **implemented** |
| Explicit backend audience allowlist + documented legacy fallback | **implemented** |
| JWKS temporary failure → controlled 503 | **implemented/tested** |
| Google Login ≠ Google Calendar OAuth | **enforced/documented** |
| Frontend auth regression | **8 passed** |
| Backend social auth | **20 passed** |
| V2.7.1 Home handoff + location regression | **52 passed** |
| TypeScript / lint / Expo web export | **ok** (lint: 42 pre-existing warnings) |
| Real GIS / native OAuth | **not completed** — browser runtime unavailable; native build absent |
| Commit / push | **NO** |
| stash@{0} | **untouched** |

## Prompt V2.7.1 — Home → ORA first-turn handoff (this batch)

| Item | Stato |
|------|--------|
| Root cause: start response discarded; mount ignored pending client_actions | **fixed** |
| Generic `pending_turn` on GET (not location-specific) | **yes** |
| Mount fulfills awaiting_client once → client-resume | **yes** |
| message_id identity; no text-only history dedupe | **yes** |
| Home Ask ≡ in-ORA send (one user turn) | **yes** (unit) |
| Live Home → Dove sono / Come mi chiamo | **pending CPO** |
| Handoff + location tests | **52 passed** |
| V1→V2.6.2 focused | **45 passed** |
| TypeScript | **ok** |
| stash@{0} | **untouched** |
| Commit / push | **NO** |

## Prompt V2.7.1 — STALE → fresh foreground refresh (prior)

| Item | Stato |
|------|--------|
| Root cause: STALE `needs_client` without usable `client_action` / loop pause | **fixed** |
| STALE + while_using → `request_foreground_location` (`refresh`) | **yes** |
| Browser granted + ORA while_using → direct `getCurrentPosition` (no sheet) | **yes** |
| `maximumAge: 0` on refresh; default 60s otherwise | **yes** |
| timeout / denied / unavailable / POST failure distinct | **yes** |
| pending_client_capability generic retry (no hardcoding “prova ora”) | **yes** |
| Place-label resolver | **unchanged** this batch |
| Unit tests location v271 | **46 passed** |
| V1→V2.6.2 focused (core + life_os + context_change) | **45 passed** |
| TypeScript `tsc --noEmit` | **ok** |
| Live Chrome re-QA | **partial** — location OK on 2nd in-ORA send; Home first turn blocked until handoff fix |
| Prompt 7.x stash@{0} | **untouched** |
| Commit / push | **NO** — STOP for CPO |

## Prompt V2.7.1 — Foreground location + PresenceContext (prior)

| Item | Stato |
|------|--------|
| LocationSignal short-lived (TTL **2h**) user-scoped | **yes** |
| PresenceContext CURRENT/RECENT/STALE/UNKNOWN | **yes** |
| Web `navigator.geolocation` foreground bridge via `client_actions` | **yes** |
| AI caps: get_current_location / get_current_presence / get_recent_presence_context | **yes** |
| Context Broker minimized presence (≠ residence) | **yes** |
| Settings: Disattivata / Durante l'uso — background **not available** | **yes** |
| Quiet Premium permission sheet (no silent launch request) | **yes** |
| Native foreground (`expo-location`) | **unsupported** (not installed) |
| Background tracking / geofencing / proactive / routines | **NOT implemented** |
| MeaningfulPlace / home-work inference / TravelFlow | **NOT this slice** |
| Device must not overwrite residence | **enforced** |
| Raw GPS → Life Memory / Life Map | **never** |
| Unit tests `test_ai_native_location_v271.py` | **pass** |
| V1→V2.6.2 focused regression | **180 passed** (`-n0`) |
| Live browser QA (Dove sono / vivo / deny / stale) | **fix 2026-08-16** — false `disabled_by_user` skipped consent/geo; requires_consent + location nudge |
| Live re-QA after consent fix | **partial** — label Vibo Marina OK; STALE refresh blocked until this batch |
| Place-label precision (locality vs municipality) | **fixed 2026-08-16** — generic resolver; provider supports Vibo Marina at zoom≥14 |
| Prompt 7.x stash@{0} | **untouched** |
| Commit / push | **NO** — STOP for CPO / architecture review |

## Prompt V2.6.2 — Context change & persistent replanning (prior)

| Item | Stato |
|------|--------|
| Root cause: session-persisted `tool_signatures` banned cross-turn `update_*` | **fixed** |
| Turn-scoped reasoning epoch + same-turn duplicate reuse | **yes** |
| Duplicate UX leak ("Sto evitando di ripetere…") removed | **yes** |
| Prompt: new conversational facts ≠ duplicate execution | **yes** |
| `user_fact_summary` → USER_PROVIDED_CONTENT / user_conversation | **yes** |
| Conversational evidence must not supersede user_file | **yes** |
| Live `lop_93e3f8760a2c4e`: 12→5 item reconciled; obj rev 2→3 | **yes** (scripted) |
| Unscripted live LLM proof | **not claimed** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.6.1 — Source-grounded reconciliation (prior)

| Item | Stato |
|------|--------|
| Root cause: `update_plan` only `add_items` (append) — no replace | **fixed** |
| `replace_items` + `reconciliation_mode` + remove_item_ids | **yes** |
| Same plan/object identity; target_date/session preserved | **yes** (live) |
| PlanItem `origin` provenance | **yes** |
| Evidence status active/superseded + public_sources | **yes** |
| Workspace Fonti human labels (no lcf_/doc_) | **yes** |
| GenerativeObjectRenderer uses `useTheme` (light readable) | **yes** |
| Live Matematica: 8 mixed items → 5 official modules; obj rev 8→9 | **yes** |
| Non-study move + quote reconciliation | **yes** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.6 — Files / evidence / context (prior)

| Item | Stato |
|------|--------|
| ContextFile model + Documents V2 storage reuse | **yes** |
| `POST /api/conversation/ai-core/files/upload` (auth, ownership) | **yes** |
| OraComposer real attach (chip, upload, remove, multi, file-only) | **yes** — shared composer |
| AI Core caps: list/get context/content/link | **yes** — no domain handlers |
| Context Broker `session_files` + staged chunks | **yes** |
| Capability honesty + untrusted-file prompt rules | **yes** |
| Evidence refs `USER_PROVIDED_CONTENT` / `user_file` | **yes** |
| Workspace quiet Fonti | **yes** |
| Live scripted QA: same plan `lop_0aecb72a15cf49`, object `lgo_44b1f457f1c247` rev 7→8 | **yes** |
| Live unscripted multi-turn LLM exam PDF in browser | **partial** — needs bearer session; plumbing proven scripted |
| Image multimodal understanding | **unavailable** (OCR text only if extracted; honesty in caps) |
| Orphan upload GC / full Files product UI | **not in scope** — deferred |
| Production object storage (S3/GCS) | **migration path** — still Documents V2 local abstraction |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.5.1 — Blank Home runtime fix (prior)

| Item | Stato |
|------|--------|
| Metro `Unable to resolve "./nav"` / `@/src/ora/nav` | **fixed** — module renamed `oraNav.ts` |
| Blank white `/` from failed bundle | **fixed** |
| Home OraInput still → `/ora` (not `/ora-ai`) | **yes** |
| Cognitive / ranking / Life OS semantics | **unchanged** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.5 — Production ORA surface (prior)

| Item | Stato |
|------|--------|
| Canonical `/ora` + `/ora/{sessionId}` on AI Core | **yes** |
| Home OraInput → AI Core (not CE→AE) | **yes** |
| Ambient ORA tab → AI Core fresh thread | **yes** |
| Goal Workspace Continua → `/ora` + session-focus | **yes** |
| Object “Continua con ORA” binds active_object | **yes** |
| `/ora-ai` DEV-only, shared components | **yes** |
| Quiet Premium Goal Workspace | **yes** (presentation) |
| Nav helpers opaque ids only | **yes** |
| Attachment pipeline in composer | **superseded by V2.6** — real ContextFile path |
| Live Home/ORA/Workspace LLM QA | **partial** — browser often missing bearer; automated ownership/route tests green |
| Home ranking / AI Core loop / Context Broker | **unchanged** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4.3 — GenerativeObject card/reveal fix (prior)

| Item | Stato |
|------|--------|
| Live object `lgo_44b1f457f1c247` audited (rev 7): `card` with empty `front`/`back`, content only in `title` | **yes** |
| Root cause: A+B+D (malformed card + validator allowed empty reveal + FE ignored `title`, always showed “Tocca per rivelare”) | **fixed** |
| Canonical revealable item `{front, back, revealable}` + small alias normalize | **yes** |
| `card_deck` validation rejects missing front/back after normalize | **yes** |
| Single `card` may be static (`revealable: false`) when only title/front exists | **yes** |
| API `GenerativeObject.public()` display-normalize for older shapes | **yes** |
| FE `CardDeck`: no reveal affordance without back; never blank; nav resets reveal; event `reveal` | **yes** |
| Browser Goal Workspace live click | **blocked** — missing bearer token in browser session |
| Live public() QA: title → front, `revealable: false` (no blank reveal) | **yes** |
| Home / AI Core cognition / Context Broker | **unchanged** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4.2 — Persistent GenerativeObject adaptation (prior)

| Item | Stato |
|------|--------|
| Root cause: chat-only answer, no `update_object`, empty object refs in AI payload | **fixed** |
| `active_object_ref` / `recent_object_refs` / `current_plan_item_ref` in session | **yes** |
| Life OS AI payload includes lightweight object previews | **yes** |
| Prompt: durable adapt → `update_object`; conversational-only OK | **yes** (AI decides) |
| Persist-before-claim for “ho semplificato / aggiornato…” | **yes** |
| `update_object`: content/spec/append/remove + revision + evidence preserve | **yes** |
| Workspace interact / Continua → session focus bind | **yes** |
| Live Matematica object `lgo_44b1f457f1c247` rev 1→3 via adaptation path | **yes** (scripted decision_fn on real DB) |
| Live unscripted LLM always calls `update_object` | **partial** — depends on model; nudge + context in place |
| Home ranking | **unchanged** this prompt |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4.1 — Canonical Home ownership (prior)

| Item | Stato |
|------|--------|
| Root cause: past plan deadlines scored as overdue (+Goal boosts) | **fixed** |
| Temporal states ACTIVE / UPCOMING / EXPIRED_* / SUPERSEDED | **yes** (`home/temporal.py`) |
| Ranking `home-rank-1.4` — canonical_active + stale penalties | **yes** |
| Daily Focus prefers actionable LifeOsPlan over expired legacy | **yes** (live QA) |
| Horizon skips EXPIRED_STALE / past dates | **yes** |
| Life OS Home routes → `/goal-workspace/{planId}` | **yes** |
| Continue prefers Life OS resume | **yes** |
| Contesti hides exam-day/past study with no session | **yes** (presentation) |
| DEV rank trace `HOME_RANK_TRACE` / `dev_rank_trace` | **yes** |
| DEV QA cleanup utility (provenance-gated) | **yes** (no auto-wipe) |
| Persistent `update_object` after “spiegamelo più semplice” | **no** — session has no `update_object` tool call |
| Object `revision` bump on update | **yes** (code path; live object never updated) |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4 — AI-native Generative Workspaces (prior)

| Item | Stato |
|------|--------|
| Closed flashcards/quiz/map artifact cognition removed from AI Core | **yes** |
| `GenerativeObject` + declarative UI primitives | **yes** |
| Capabilities `create_object` / `update_object` / `get_object` / `list_goal_objects` | **yes** |
| Generic FE `GenerativeObjectRenderer` + `/goal-workspace/[planId]` | **yes** |
| Life OS actions never open legacy `/action` | **yes** |
| Stale historical goal demotion (ambiguous exam) | **yes** |
| `generate_artifact` / type-specific generators | **deprecated / removed from registry** |
| Legacy `life_os_artifacts` | **read-only compat** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.3 — Generic Life OS execution (prior; artifact catalog superseded)

| Item | Stato |
|------|--------|
| `life_os` plans/artifacts collections | **yes** |
| Capabilities create/update plan, actions, artifacts | **yes** |
| Evidence calibration (general vs target-specific) | **yes** |
| Home adapter + Continue `/ora-ai` | **yes** |
| Focus Horizon via `due_at` / `goal_target_date` | **yes** |
| Life Map situations | **yes** |
| Staged artifact generation budgets | **yes** |
| Rich text harness `/ora-ai` | **yes** |
| Tests V2.3 A–Z | **yes** |
| Persist-before-claim (Life OS writes) | **yes** (soft re-entry; note_intention insufficient) |
| Live exam → Home + artifacts | **yes** (local Mongo + `/home`) |
| Resume prefers life_os over chat-only | **partial** — plan/actions on Home; resume_item may still be conversation_session |
| Evidence wording always calibrated | **partial** — governance + prompt; model may still overclaim without TARGET_SPECIFIC |
| StudyFlow / domain wizards | **not added** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt 7 V2.2 — General tool use & grounded external knowledge (prior)

| Item | Stato |
|------|--------|
| Tool Registry V2 (capability metadata) | **yes** |
| `web_search` capability | **yes** |
| Provider failover Tavily→Brave→Gemini Search | **yes** (config-dependent) |
| ExternalObservation re-entry | **yes** |
| Tool-before-claim governance | **yes** (prompt + policy) |
| Autonomous READ_ONLY tools | **yes** |
| CONSEQUENTIAL_WRITE blocked | **yes** |
| Query minimization | **yes** |
| `current_facts` temporal scope | **yes** |
| Tests A–J `test_ai_native_tools_v22.py` | **yes** |
| Combined AI-core pytest | **55 passed** |
| Live research QA | **depends on RESEARCH_ENABLED + keys** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt 7 V2.1 — Personal context retrieval (prior)

| Item | Stato |
|------|--------|
| Stage A account display name | **yes** |
| Semantic Stage B personal lookup | **yes** (identity/residence/employment/study/general) |
| Provenance + authority reuse (Life Memory bands) | **yes** |
| Context re-entry keeps original question | **yes** |
| Over-broad context query blocked | **yes** |
| No name/residence/job conversation branches | **yes** |
| Tests `test_ai_native_personal_context_v21.py` | **yes** (A–L) |
| Combined AI-core pytest | **34 passed** |
| Live Gemini QA name/residence/work | **yes** — synthetic user: name 1-call; residence/work 2-call |
| Commit / push | **no** — STOP for CPO |

## Prompt 7 V2 — AI-Native Cognitive Core (prior)

| Item | Stato |
|------|--------|
| Package `conversation_engine/ai_core/` | **yes** |
| AI owns cognition (decision contract) | **yes** |
| Context Broker stage A/B | **yes** (upgraded in V2.1) |
| Tool Registry (read + soft note) | **yes** |
| Bounded loop MAX_STEPS=4 | **yes** |
| Governance without domain wizards | **yes** |
| Minimal harness `/ora-ai` + scroll | **yes** |
| Mocked suite `test_ai_native_core_v1.py` | **yes** (20 passed) |
| Web research / Tavily / learning artifacts | **not in scope** |
| Prompt 7.x stash restored | **no** |
| Commit / push | **no** — STOP for CPO |

### Principle

**AI owns cognition. Deterministic systems own capabilities and governance.**

### Abandoned

Prompt 7.x remains in `stash@{0}: backup: abandoned Prompt 7.x cognitive architecture` — do not restore.

## Cognitive Reset — Prompt 7.x abandoned (prior)

| Item | Stato |
|------|--------|
| Working tree restored to HEAD `258cd85` | **yes** |
| Safety stash `backup: abandoned Prompt 7.x cognitive architecture` | **yes** (`stash@{0}`) |
| Cognitive Focus / requirements / research orchestration removed from tree | **yes** (in stash only) |
| New AI-first cognitive engine | **not started** — STOP for CPO |
| Commit / push | **no** |

### Why abandoned

Live QA showed deterministic readiness/requirements/question planners owning dialogue before the LLM: repeated asks, unnatural copy, discriminator loops, research/action at the wrong time. Not fixable by micro-patch.

### Canonical rebuild direction (next prompt — do not implement yet)

**ORA IS AI-FIRST.** The LLM owns goal understanding, what to ask/research/tool/act, and the next conversational turn. Deterministic code validates (auth, schemas, provenance, privacy, idempotency, tool execution, safety) — it does **not** script the conversation via fixed slot sequences.

### V2.8.1 Situation Model V1

| Contract | State |
|---|---|
| User-scoped Situation persistence | **implemented** |
| Cross-session current/recent context slice | **implemented** |
| AI-owned create/update/cancel/resolve/none | **implemented** |
| Runtime ids, ownership, revision, transition validation | **implemented** |
| Same-turn/client-resume idempotency | **implemented** |
| Cross-turn corrections and supersession history | **implemented** |
| Automatic Situation → Memory promotion | **forbidden** |
| Automatic linked plan/object mutation | **forbidden** — AI must use Life OS capability |
| Dedicated Situation UI/Home card | **not implemented by design** |

Target loop (conceptual only): USER → AI orchestrator → structured next action → governance → tool → AI again → response.

### Reusable infrastructure proven in 7.x (capabilities, not conversation architecture)

Gemini provider · Groq provider · Tavily retrieval · Brave fallback · provider failover · source provenance · web evidence · document attachments · StudyPlan persistence · Life Profile · Life Memory · Life Map

### Preserved committed surfaces

Quiet Premium · Home · Shell · Login · Contesti/Life Map · Memoria/Life Memory · Life Setup · auth · canonical backend services · committed Study/Travel services

## Prompt 6.1.1 — Epistemic authority (prior)

| Item | Stato |
|------|--------|
| Life Setup utterance → user_said/confirmed | **yes** |
| Inferred leftover repair (name/home/role keys) | **yes** (idempotent) |
| Account name → known | **yes** |
| GPS/device ≠ known residence | **yes** |
| needs_clarification only if weak authority | **yes** |
| Gemini persona (never “mi chiamo”) | **yes** |
| Commit / push | **no** |

Last prior: 2026-08-10 (Prompt 6.1 — Memory clarification loop)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- Baseline: `9722724`
- No push / no merge unless requested

## Prompt 6.1 — Clarification loop (this batch)

| Item | Stato |
|------|--------|
| Actionable “Da chiarire” | **yes** |
| `POST /life-memory/clarify/*` | **yes** |
| CE `origin=memoria` → Focus clarify (not AE) | **yes** |
| Gemini question + free-text resolve | **yes** (Provider Manager; soft-fail) |
| Governance → Life Profile correct_fact | **yes** |
| Additional facts as suggest only | **yes** |
| Soft language for ambiguous/likely | **yes** |
| Fake Correct/Forget buttons | **no** |
| Home / Contesti / Login / Life Setup / Shell | **frozen** |
| Commit / push | **no** |

## Prompt 6 — Memoria Life Memory V1 (prior)

| Item | Stato |
|------|--------|
| `GET /api/life-memory` deterministic | **yes** |
| Identity + contradiction governance | **yes** |
| Gemini wording (`MEMORY_GEMINI`, default 0) | **yes** (optional) |
| Memoria Quiet Premium browse UI | **yes** (replaces ask-first) |
| FE invent from raw sources on API fail | **no** (honest empty/error) |
| Correct / Forget / Confirm in UI | **clarify loop** (not form editors) |
| Conversation → durable memory promotion | **partial** (clarify path; general CE promotion still gap) |
| Life Objects as Memory evidence | **gap** (hybrid documented; Profile-first V1) |
| Home / Contesti / Login / Life Setup / Shell | **frozen** |
| Commit / push | **no** (CPO/CDO review) |

### Boundaries

- Home = now · Contesti = current situations · Memoria = durable learned · Documenti = files · ORA = talk

## Prompt 5.3.1 — Runtime integration (prior)

| Item | Stato |
|------|--------|
| Live API had `/life-map` before restart? | **no** (stale uvicorn Aug 9 → 404 → FE fallback) |
| After restart `force=true` Psicologia count | **1** canonical + Vibo |
| Snapshot cache masking identity? | **no** (no snapshot; cache is Gemini-only) |
| Contesti uses API when available | **yes** (+ DEV warn on fallback; refresh `force=true`) |
| Semantic truth three plans | **SAME** (lineage + same-day polluted title; not two exams) |
| Contesti visual redesign | **no** |
| Commit / push | **no** |

### Restart reminder

Backend must run **current** tree (prefer `--reload`). Old process without `life_map` router → Contesti shows raw study plans again.

## Prompt 5.3 — Semantic identity & deduplication (prior)

| Item | Stato |
|------|--------|
| Root cause Psicologia ×3 | **3 study_plans** (incl. `Studio: Psicologia` title leak + lineage re-confirm) |
| Level 1/2 deterministic identity | **yes** (`identity.py`) |
| SAME ≠ RELATED | **yes** |
| Gemini identity consultant (capped) | **yes** when `LIFE_MAP_GEMINI=1` |
| Contesti visual redesign | **no** |
| Frontend dedup | **no** (API returns canonical) |
| Home / Life Setup / Memoria / Shell | **frozen** |
| Commit / push | **no** |

### Screenshot expectation (user_0ea622447cfc shape)

BEFORE: 3 Psicologia study rows + Vibo. AFTER: 1 canonical Psicologia + Vibo.

## Prompt 5.2 — Grounded Gemini Life Map vertical slice (prior)

| Item | Stato |
|------|--------|
| Novel grounded situation → Contesti rows | **yes** (open semantics, no gym enum) |
| Stable identity from evidence refs | **yes** |
| Hallucination drop / ambiguity preserve / dedup / det wins | **yes** (tests) |
| `LIFE_MAP_GEMINI` default 0; works when 1 | **yes** |
| Contesti visual redesign | **no** |
| Raw conversation → Life Map | **no** (deliberate) |
| Home / Life Setup / Memoria / Shell | **frozen** |
| Commit / push | **no** (CPO/architecture review) |

### Local AI check

1. `LIFE_MAP_GEMINI=1` + `GEMINI_API_KEY` in `backend/.env`
2. Life Profile fact with free-text novel activity (e.g. salute.attivita)
3. `GET /api/life-map?force=true` → `situations` may include `kind=inferred`
4. Contesti “In questo periodo” shows row without special-case FE

## Prompt 5.1 — AI-Native Life Map foundation (prior)

| Item | Stato |
|------|--------|
| Option | **B** — thin `backend/life_map/` on shared Provider Manager |
| Principle GEMINI=cognition / data=truth | **documented + coded** |
| `GET /api/life-map` deterministic assemble | **yes** |
| Gemini enrichment | **foundation only** (`LIFE_MAP_GEMINI=0` default) |
| Contesti UI redesign | **no** (unchanged Quiet Premium) |
| Novel situations in Contesti rows | **not yet** (validated in interpretation only) |
| Conversation → Life Map evidence | **gap** (not wired) |
| Life Objects projection | **gap** (interpretation layer designed; LO not assembled yet) |
| Home / Life Setup / Memoria / Shell | **frozen** |
| Commit / push | **no** (CPO/architecture review) |

### Gaps / next (5.1)

- Wire conversation-confirmed facts into evidence pack.
- Optionally surface grounded inferred situations in Contesti when product defines nav.
- Life Object list as additional structured source (avoid Profile duplicate).
- Enable `LIFE_MAP_GEMINI=1` only after review + cost/latency check.

## Prompt 5 — Contesti Life Map V1 (prior)

| Item | Stato |
|------|--------|
| Placeholder Contesti sostituito | **yes** |
| Life Map (not category menu) | **yes** |
| Dati: Life Profile + study/travel attivi | **yes** (no new backend) |
| Nessuna tassonomia fissa vuota / + Nuovo contesto | **yes** |
| Sezioni solo se contenuto reale | **yes** |
| Context Detail generico | **no** (deliberato — gap documentato) |
| Life Objects / relazioni / history in Contesti | **no** (gap — shadow / non affidabili per V1) |
| Home / Life Setup / Memoria / Shell | **frozen / untouched** |
| Commit / push | **no** (fermo per review CPO/CDO) |

### Visual QA — Contesti (desktop Light)

1. `scripts/dev`; login utente con Life Profile popolato e/o studio/viaggio attivi.
2. Tab Contesti: titolo + supporting copy; max-width ~800; Ambient rail invariata.
3. Con dati: “In questo periodo” e/o “La tua vita” senza card grid / icone categoria.
4. Utente nuovo / pochi dati: empty *ORA sta ancora conoscendo la tua vita.*
5. Capture Screenshot A (con dati) + B (empty) se possibile.

### Gaps / next

- Generic Context Detail quando esisterà destinazione sensata (Life Object o profile domain).
- Relazioni reali (non string-match) se Life Graph / LO relationships sono product-ready.
- Opzionale: Life Objects active list come spine aggiuntiva (oggi shadow; rischio duplicato con Profile).

## Prompt 4 — Login Quiet Premium V1 (prior)

| Item | Stato |
|------|--------|
| ImmersiveScreen canvas, no login card | **yes** |
| Canonical headline + supporting copy | **yes** |
| AppButton / AppInput / AppDivider + useTheme | **yes** |
| Apple → Google → Email order; modes + register toggle | **yes** |
| Forgot password / legal links | **omitted** (did not exist) |
| Password visibility toggle | **omitted** (did not exist) |
| `routeAfterAuth` / Life Setup / Home / Shell | **frozen / untouched** |
| Backend / AuthContext / api client | **untouched** |
| Commit / push | **no** |

### Visual QA — manual repro (Login)

**Desktop Dark / Light**

1. `scripts/dev` (or Expo web); open `/login` logged out.
2. Viewport ≥1024px: content column ~420–480px, centered, slightly above vertical middle; lots of whitespace; no card.
3. Toggle theme preference Light/Dark/System — surfaces/text/accent from semantic tokens.
4. Providers: Apple (if shown) → Google → divider → Continua con Email; dimmed if unconfigured; tap unconfigured → human config message.
5. Email form: Accedi primary Deep Indigo; toggle *Nuovo? Crea un account*; loading disables double submit; bad password → human error.
6. Capture Screenshot A (Dark) + B (Light).

**Mobile**

1. Narrow viewport / device: full-height Immersive, safe-area, keyboard opens without clipping submit.
2. Capture Screenshot C.

**Post-auth (routing frozen)**

1. New user → Life Setup gate; completed user → Home. Do not bypass gate for QA.

## Micro-batch 3.S — Human Presentation Semantics (prior)

| Item | Stato |
|------|--------|
| Human Italian `reason_summary` from factor codes | **yes** — `home/reason_presentation.py` |
| Ranking scores/weights/order unchanged | **yes** |
| DailyFocus `"Tipo "` omit removed | **yes** — backend fixed |
| Study exam identity ≠ Home/insight title | **yes** — `study/flow.py` + `plan_service` |
| Shell / Home visual / Daily Focus layout | **untouched** |
| Commit / push | **no** |

### INTERNAL ≠ PRESENTATION

- **INTERNAL:** `ReasonFactor` codes + weights drive ranking; type factor may still label `Tipo travel` for debug API.
- **PRESENTATION:** `format_reason_summary(factors, item_type=…)` → short Italian; wired in `ranking.score_item` / dampen path → `explanation.summary`.
- **Study:** subject identity = `intent_entities.subject|exam` only. Never `display_title` / `ctx.title` / `session.title`. Known → `Quando è l'esame di {Subject}?`; unknown → `Quando è l'esame?` + `Quale esame vuoi preparare?`.

## Application Shell V1 Visual Correction (Prompt 3.1) — prior

| Item | Stato |
|------|--------|
| Desktop rail fixed 80px (remove `railWrap` flex:1) | **yes** |
| `useAmbientInset.paddingLeft` = 0 (rail is layout sibling) | **yes** |
| Rail active state quieter (weight; no rail dots; ORA not FAB) | **yes** |
| Action Focus decision max-width 720 (`FOCUS_DECISION_MAX_WIDTH`) | **yes** |
| Focus understood-summary chips hidden (Destinazione: Partenza noise) | **yes** — session data kept |
| DailyFocus omit engine `reason_summary` with `"Tipo "` | **superseded by 3.S** |
| Presentation Semantics Issue (full human Perché copy) | **closed in 3.S** |
| Exam title bug (`study/flow.py`) | **fixed in 3.S** |
| Home layout / DailyFocus structure / max-width | **frozen** |
| Backend / commit / push | **no** |

### Visual QA — manual repro (auth-gated; no auth bypass)

**Screenshot A — Home desktop compact rail**

1. `scripts/dev` (or Expo web + backend) with a logged-in user.
2. Resize viewport ≥1024px width.
3. Open Home `/(tabs)`.
4. Confirm left Ambient rail ≈80px; content (DailyFocus / AskBar / Horizon) centers in the *remaining* viewport, not the full window ignoring the rail.
5. Capture Screenshot A.

**Screenshot B — Action Focus**

1. From Home Daily Focus, open an Action guide (`/action/[sessionId]`).
2. Confirm: no Ambient rail/bar; Focus chrome ← only; decision column ~720px; Continua full-width inside column; no “Destinazione: Partenza” chips above the question.
3. Capture Screenshot B.

### Manual checklist (shell)

1. Tabs: Home · Contesti · ORA · Memoria · Profilo
2. ≥1024: compact rail 80px, not 50/50
3. Narrow: floating Ambient bar unchanged
4. Action: Focus width ~720; no understood-summary noise; Continua primary
5. Light/Dark via tokens
6. Reduce motion: shell fade 0

## Application Shell V1 (Prompt 3) — foundation

| Item | Stato |
|------|--------|
| `OraShellMode` ambient / focus / immersive | **yes** (`frontend/src/shell/`) |
| AmbientTabBar floating + GlassContainer | **yes** |
| Desktop Ambient rail via `useBreakpoint` | **yes** (geometry corrected in 3.1) |
| Primary IA Home · Contesti · ORA · Memoria · Profilo | **yes** |
| Contesti Quiet Premium placeholder | **replaced** by Life Map V1 (Prompt 5) |
| ORA center → ConversationEngine Ask path | **yes** (`/(tabs)/ora`) |
| Documenti / Aggiungi `href: null` (Profilo → Documenti) | **yes** |
| FocusScreen / FocusChrome | **yes** |
| ImmersiveScreen foundation | **yes** (no Life Setup redesign) |
| Action `/action/[sessionId]` Focus chrome + useTheme | **yes** |
| Shell transition ~240ms + reduce-motion | **yes** |
| Home Frozen — shell glue + safe presentation omit only | **yes** |
| Life Setup / Backend | **untouched** |
| Commit / push | **no** (per request) |

## Sprint 4.2 Final Fix — question intent constrained

| Item | Stato |
|------|--------|
| `QUESTION_GOALS` / planner-owned intent | **yes** |
| Gemini context binds `question_goal` | **yes** |
| spoken_question semantic validation (life_places drift) | **yes** |
| Ack judgment sanitize (giustamente/ovviamente/correttamente) | **yes** |
| Architecture A (one StrategistPlan LLM call) | **yes** (planner is deterministic pre-step) |
| MLC / gate / location / Docs / Home / auth / soft-exit frozen | **yes** |
| FE | **untouched** |
| Commit | **pending review** |

## Sprint 4.2 — AI-Native Conversational Rendering

| Item | Stato |
|------|--------|
| Architecture A (same-call spoken fields) | **yes** |
| `acknowledgement` / `spoken_question` / `conversational_bridge` XOR | **yes** |
| `validate_rendered_text` + SAFE fallbacks | **yes** |
| Critical fix: no `lavori come {priority sentence}` | **yes** |
| Optional ONE Gemini wrap synthesis | **yes** |
| MLC / gate / location / soft-exit / Home frozen | **yes** |
| DETERMINISTIC vs AI documented | **yes** |
| Tests A–F + walkthrough + mocks | **yes** (137 passed with MLC/strategist/life_experience/docs) |
| FE | **untouched** |
| Commit | **pending review** |

## Sprint 4.1 — Walkthrough Corrections (this batch)

| Item | Stato |
|------|--------|
| Auth CTA “Nuovo? Crea un account” on initial screen | **yes** |
| Hide Esci / Più tardi on first-run pre-MLC | **yes** (via `allowSoftExit` from `?resume=` / `start.resumed`, not `!done`; Salta tema kept) |
| Soft-exit residual fix (4.1) | **yes** (`softExit.ts` + tests A–D) |
| Thinking state in-thread (no full-screen loader) | **yes** |
| near_mlc_bridge not falsely “chiaro” on thin knowledge | **yes** |
| NUCLEUS explain benefits first-person | **yes** |
| Location assist life_places (geolocation + Nominatim + confirm) | **yes** (no expo-location; city only) |
| synthesize_first_picture paraphrase fixes | **yes** |
| Refusal / doc / synthesis / location tests | **yes** |
| Gate / MLC / Documents V2 / Home / auth backend frozen | **yes** |
| Backend tests (strategist+MLC+life_experience+conversational) | **59 passed** |
| `tsc --noEmit` / ESLint changed FE | **PASS** (0 errors) |
| Commit | **pending review** |

## Sprint 4 — Conversational Experience V1

| Item | Stato |
|------|--------|
| First-contact greeting (intro + one open Q) | **yes** |
| Contextual acknowledgements (strategist/voice) | **yes** |
| Near-MLC conversational bridge (no %/checklist) | **yes** (tightened in 4.1) |
| Fact-grounded final synthesis + learning promise | **yes** (rewrite in 4.1) |
| CTA **Entra in ORA** (same complete→gate→Home flow) | **yes** |
| Document proposal as optional accelerator copy | **yes** |
| Exit / Più tardi copy (≠ Home / ≠ completed) | **yes** (hidden on first-run in 4.1) |
| No FE conversation engine / no progress UI | **yes** |
| Gate / MLC / Documents V2 / Home frozen | **yes** |
| Backend tests (incl. conversational) | **superseded by 4.1 count** |
| `tsc --noEmit` / ESLint life-setup | **PASS** |
| Commit | **pending review** |

## Sprint 3 — Minimum Life Context V1

| Item | Stato |
|------|--------|
| `minimum_life_context.py` coverage model | **yes** |
| `plan_next` wrap only when MLC sufficient | **yes** |
| Multi-nucleus infer from natural language | **yes** |
| Persist coverage via `known_facts` + `meta.mlc_coverage` | **yes** |
| Documents not required for done | **yes** |
| Gate Sprint 2B / Home untouched | **yes** |
| Backend tests MLC + strategist | **passed** (superseded count by Sprint 4) |
| Commit | **included in baseline `9722724` / pending Sprint 4 review** |

## Sprint 2B — Life Setup Conversation behind Gate

| Item | Stato |
|------|--------|
| `/life-setup` mounts `LifeSetupConversationScreen` | **yes** |
| Raw `/(tabs)` bypasses removed from conversation | **yes** |
| Complete → `lifeSetupComplete` then `completeLifeSetupGate` | **yes** |
| Exit / Più tardi do not open Home | **yes** |
| Gate unlocks Home only on `session.status === completed` | **yes** |
| Tabs guard kept (2nd defense) | **yes** |
| Home / Documents pipeline untouched | **yes** |
| Commit | **pending review** |

### Resume limits (documented)

- Active session: cold start resumes via `lifeSetupStart(false)`.
- After Esci (`lifeSetupCancel`): session terminal → in-place `start(force=true)` (new turn, not mid-thread restore).
- “Più tardi” no longer calls `postpone_all` (that marked `skipped` and unlocked Home under old `should_show` semantics).

## Sprint 1 — Life Setup Gate

| Item | Stato |
|------|--------|
| Persistent `ora.lifeSetupCompleted.<userId>` | **yes** |
| Gate module `src/life-setup/gate.ts` | **yes** |
| Placeholder Completa Setup | **rollback only** (not normal path) |
| Home unaware / unchanged | **yes** |

## Prior — Home Quiet Premium V1 — technical consolidation (2.2)

**Scope:** code quality only — **no intentional visual change**. Preparing Frozen V1.

| Item | Stato |
|------|--------|
| `getFocusGlow(scheme)` in theme | **yes** |
| CTA busy disables sibling actions | **yes** |
| Nav+action dual-step documented (intentional) | **yes** |
| Redundant surface ternaries removed | **yes** |
| `focusPresentation` helpers | **yes** |
| Visual design (polish 2.1) | **frozen intent** |

## Prior — Home Quiet Premium Polish 2.1

| Item | Stato |
|------|--------|
| Daily Focus / CTA hierarchy / Horizon / Ask Bar | **yes** |
| Home V3 Life Objects UI | **still OFF** |

## Prior — Design System + Life Objects

| Item | Stato |
|------|--------|
| Quiet Premium tokens / ThemeProvider / primitives | **implemented** |
| Life Object Engine + Knowledge Model | **implemented** (shadow) |
| `LIFE_OBJECT_HOME_UI_ENABLED=0` | **yes** |

## Open / next

1. **Manual new-user Life Setup walkthrough** (Sprint 4 feel test A–G) before more features
2. **Login Quiet Premium** — CPO/CDO visual review (Screenshot A/B/C); commit when approved
3. Theme toggle in Profilo
4. Playwright Ambient IA + Action Focus smoke
5. Home V3 UI — solo con flag=1
6. Exam presentation already fixed in 3.S — monitor residual Perché factor rows

## Credentials / safety

- Never commit `.env` / tokens
- No new UI libraries
- No backend changes in this batch
# V2.8.4 — Unified Clarification + Uncertainty Engine

Status: implemented in the production AI Core, CPO-approved and closed out. `CognitiveDecision`
now has an optional backward-compatible uncertainty contract with typed missing-information
identity, ambiguity and reversible assumptions. Governance prevents repeated structured
questions and unsafe actions under blocking uncertainty; Context Broker V3 remains the bounded
evidence retrieval path. No domain router, new provider, dependency, DB collection or frontend
flow was introduced.

Final local regression gate (2026-08-19): 16/16 deterministic V2.8.4 tests passed; 292 passed
in `conversation_engine/tests/` (excl. provider-real `_live.py`); 44 passed in
`situations/life_memory/life_os/llm`; legacy compatibility `test_iter19_2_memory_ask_documents.py`
3 passed/7 skipped (honest provider-unavailable skip); `compileall`, blocking lint and
`git diff --check` clean. Unrelated legacy `tests/test_iter9..23*` integration suites were
excluded from this gate (remote-preview-URL dependency and pre-existing shared-DB test-order
coupling documented in `backend/tests/conftest.py`) — confirmed unrelated to `ai_core` by
import audit, zero references found.

# V2.8.5 — Life Context Graph + Unified Cognitive State

Status: implemented, **CPO approved — closed out 2026-08-20**. New `backend/context_graph/`
module (edges only, no new node collection); `CognitiveDecision.context_graph_updates`
optional/backward-compatible, ≤2 per turn; new bounded `life_context_graph` Context Broker
source (depth ≤2, ≤10 edges). Deliberately not built on the pre-existing
`life_graph`/`knowledge`/`auto_link`/`life_objects` subsystems — see `docs/ARCHITECTURE.md`
V2.8.5 section for the full architectural rationale.

**Graph convergence decision: COEXISTENCE WITH A STRONG BOUNDARY.** `context_graph` is the
sole canonical source for relationships the conversational AI Core authors and reasons about
(Situation/Memory/Goal/Plan/Object/Profile/Document/Calendar/Presence). `life_graph` /
`knowledge` / `auto_link` keep every existing non-`ai_core` consumer they already have
(Documents, Goal Engine, Action Engine, Home's auto-link surfacing); `life_objects` keeps its
own Digital Twin relationship model (LifeObject↔LifeObject only). No bidirectional sync, no
storage migration/fusion in V2.8.5 — if a future surface needs relationships from both worlds,
the correct pattern is a read-side adapter/projection, never a shared write path.

| Item | Stato |
|------|--------|
| Edge model AI-authored, system-governed, open predicate | **implemented** |
| No duplicate canonical-entity storage (refs only) | **implemented** |
| Ownership/idempotency (`governance_key`)/revision+history | **implemented** |
| Conflicting active edge → `REQUIRES_SUPERSESSION` (never silent) | **implemented** |
| `life_context_graph` Context Broker source, bounded 1-2 hop | **implemented** |
| Temporary Situation / inference / presence never auto-promoted | **enforced** |
| Persist-before-claim honesty for graph-link language | **implemented** |
| No second LLM/embedding call, no new DB technology | **none added** |
| V2.8.5 deterministic tests (A-T) | **20/20 passed** |
| Regression: `conversation_engine/tests` (excl. `_live.py`) | **312 passed** |
| Regression: `situations/life_memory/life_os/llm` | **44 passed** |
| Legacy `test_iter19_2_memory_ask_documents.py` | **3 passed/7 skipped** (honest) |
| `compileall` / blocking lint / `git diff --check` | **all clean** |
| Hardcoding audit (new production code) | **clean** (one prose example self-corrected) |
| Provider-real eval (continuity/correction/arbitrary-life/uncertainty) | **4/4 passed** (live Gemini; one test assertion self-corrected, not production code) |
| Live Chrome gate (real backend, real DB, real auth) — edge creation/persistence | **PASS** — real `context_edges` doc created from a natural arbitrary-life conversation (non travel/study/work/house/medical), verified in Mongo (subject/predicate/object/authority/confidence/revision) |
| Live gate — cross-turn continuity | **PASS** — later turn used the relationship without the user repeating it |
| Live gate — cross-session continuity | **PASS** — new session (new `ces_` id) recalled updated state with zero re-explanation |
| Live gate — negative control | **PASS** — a routine turn with no durable relationship created zero edges |
| Live gate — persist-before-claim | **PASS** — every "ho annotato/aggiornato" claim verified true against Mongo, in both the graph edge and the Situation correction path |
| Live gate — `life_context_graph` retrieval observed live | **NOT OBSERVED** (see follow-up 1) — mechanism wired and indexed correctly; not selected by the Broker in this scenario because Situation alone already answered the query |
| Live gate — graph-level `REQUIRES_SUPERSESSION` observed live | **NOT OBSERVED** (see follow-up 2) — the live correction (a person's role changing) was correctly handled by Situation's own supersession, since no competing graph edge existed to conflict |
| Commit / push | **yes, this close-out** |

### Follow-up items (non-blocking, not yet decided as requirements)

1. `life_context_graph` Context Broker retrieval was not observed firing in the final live
   browser gate. Deterministic + provider-real coverage already exists for this path. Worth
   stressing with a retrieval-only live scenario in a future sprint — **not a defect**, and the
   Source Registry ranking/anchor logic is explicitly NOT to be changed as part of this close-out.
2. `context_graph`-level supersession (`REQUIRES_SUPERSESSION` → new edge → old edge
   `superseded_by`) was not exercised in the final live browser gate — already covered
   deterministically and via provider-real eval. Do not manufacture an artificial conflict just
   to force this live; wait for a natural scenario.
3. `life_object:` is not yet a recognized canonical ref prefix in `context_graph` — a future
   product decision, not implemented now.
4. Whether `life_context_graph` should ever receive an anchor/ranking bonus in the Source
   Registry (mirroring `situations`/`profile`/`memory`) is an open future question, explicitly
   not decided or implemented in this close-out.
