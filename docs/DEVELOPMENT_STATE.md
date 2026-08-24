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

## V2.8.6a — Calendar Foundation Hardening (this batch)

**Status: foundation only — hardens the existing Calendar infrastructure. Does NOT expose
Calendar as an AI Core capability yet (that is V2.8.6b, gated separately). No CalendarFlow, no
keyword router, no OAuth structural change.**

| Item | Stato |
|------|--------|
| Context Broker `_calendar` source field-name bug (`start`/`end`/`source` → real schema `start_datetime`/`end_datetime`/`provider`) | **fixed** — AI no longer sees `start=unspecified` for every event |
| General-purpose `timezone_service.resolve_user_timezone()` (user_confirmed → connector_calendar → system_fallback, authority always observable) | **implemented** — no wizard, no auto-write to Profile, no GPS-derived residence inference |
| Real Google Calendar provider `create_event` idempotency (`extendedProperties.private.ora_event_id`, bounded exact lookup via `privateExtendedProperty`, never fuzzy) | **fixed** — previously only the fake provider checked this; a network failure after Google accepted could duplicate an event on retry |
| Canonical `GoogleCalendarSyncService.reschedule_draft()` (title/start/end/timezone/location/description; never a second draft; failure never claims success) | **implemented** — no update/reschedule path existed for document-derived drafts before this batch |
| `connectors/google_calendar/consent.py` — reusable, non-HTTP `calendar_consent_granted()`/`require_calendar_consent()` for a future AI Core tool handler | **implemented** — reuses `PermissionService`, no second permission system |
| `reauthorization_required` instance status now set on refresh failure | **fixed** — small, additive; OAuth flow itself unchanged |
| Revocation now also revokes `calendar.write` consent (previously only `calendar.read`); google-synced drafts flagged `sync_status="revoked"` when no other active Google instance remains for the user (non-destructive — never deletes/touches Google, never touches `google_event_id`) | **fixed** — multi-account edge case (attributing a draft to a specific surviving instance) explicitly left as a documented limitation, not solved here |
| `calendar_event_drafts` index `(user_id, status)` | **added** — verified live on boot |
| Three pre-existing independent write subsystems (`documents/intelligence`, `action_engine/study`, `action_engine/travel`) | **untouched** — consolidation explicitly out of scope for this batch |
| `intent_engine`/`semantic_engine` keyword routing, Action Engine reminder wizard, `goal_engine.linked_calendar_events`, `ai_life_strategist` | **untouched**, as instructed |
| AI Core tool registry | **unchanged** — verified 0 Calendar capabilities (V2.8.6a does not add any) |
| `context_graph` | **untouched** — `calendar:` ref prefix already supported since V2.8.5 |
| V2.8.6a tests (A–T) | **22/22 passed** |
| Calendar regression (`test_iter9_ingestion_and_google_calendar`, `test_google_calendar_write_sync`, `test_iter18_apple_calendar_connector`, `test_oauth_loopback_hosts`) | **57 passed** |
| `conversation_engine/tests` (excl. `_live.py`) | **312 passed** |
| `situations/life_memory/life_os/llm` | **44 passed** |
| Provider Manager | **22 passed, 1 skipped** |
| `compileall` / blocking lint / `git diff --check` | **all clean** |
| Real backend boot (`server.startup()` invoked directly, real configured DB) | **PASS** — "Life Context Graph indexes ready" + new calendar index confirmed live, no regression |
| No real Google/Apple call anywhere in this batch | **confirmed** — fake provider + mocked `httpx` transport only |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up (non-blocking, not decided as requirements)

1. Multi-account attribution of `calendar_event_drafts` to a specific revoked instance is not solvable with the current schema (no `connector_instance_id` on the draft) — documented limitation, not fixed.
2. The three independent Google write subsystems (`documents/intelligence`, `action_engine/study`, `action_engine/travel`) still duplicate "resolve active instance" logic — consolidation candidate for a future batch, not this one.
3. V2.8.6b will add the actual AI Core capabilities (`get_calendar_events`, `create_calendar_event`, `update_calendar_event`, `cancel_calendar_event`) on top of this now-hardened foundation, using the `consent.py` helper and `reschedule_draft()` added here.

## V2.8.6b — AI-native Calendar Intelligence (this batch)

**Status: Calendar is now an AI Core capability — read-only evidence plus confirmed,
consent-gated writes. No CalendarFlow, no intent router, no new confirmation UI, no new
governance code, no new idempotency mechanism, no Context Graph changes.**

| Item | Stato |
|------|--------|
| `get_calendar_events` (READ_ONLY), `create_calendar_event`/`update_calendar_event`/`cancel_calendar_event` (REVERSIBLE_WRITE) registered in `ToolRegistry` | **implemented** — `conversation_engine/ai_core/tools/calendar_caps.py` |
| Calendar write confirmation | **reuses** the existing `response_mode="act"` mechanism — no new confirmation surface |
| Governance for calendar writes | **reuses** the existing `_blocks_side_effect(uncertainty)` gate — zero new governance code |
| Local-draft idempotency | **reuses** `InternalCalendarProvider.create_from_candidate`'s existing keying (`source_document_id="ai_core_conversation"`, `source_event_candidate_id=f"epoch:{reasoning_epoch}"`) |
| Persist-before-claim guard for calendar | **implemented** — `_CALENDAR_CLAIM_RE` in `loop.py`, fourth instance of the Memory/Graph pattern |
| Consent instance-scoping bug (write handlers checked the wildcard consent tier, but real OAuth grants consent scoped to the specific connected instance) | **found and fixed** during implementation — `_active_instance_id()` helper added |
| `update_calendar_event` false-negative honesty bug (`reschedule_draft()` commits the local field patch unconditionally before any Google-side step; the handler's failure paths denied the update had happened at all, when it always had, locally) | **found live during Chrome QA and fixed** — both failure paths now return `status="partial"` with an accurate "saved locally, not confirmed on Google" message, mirroring `create_calendar_event`'s existing convention |
| Keyword-based routing (`if "calendar"/"ricordami" in text`, `calendar_intent ==`) | **absent**, statically verified — `test_v`/`test_z` grep the production diff |
| Timezone | **exclusively** via `timezone_service.resolve_user_timezone` — no new hardcoded `Europe/Rome` in the AI-native path |
| Conflict awareness | **implemented** — bounded O(n²) overlap check inside `get_calendar_events`, capped at 20 events / 10 pairs; evidence only, no new scheduling engine, no Google FreeBusy call |
| Canonical ref | `calendar:{draft_id}` for AI-managed events; `ingestion_events` remain read-only mirrors with `calendar_ref: None` — no legacy migration |
| Calendar ↔ Situation/Plan/Goal relationship | **AI-proposed only**, via the existing V2.8.5 `context_graph_updates` channel with open predicates — never auto-created by the calendar tool |
| Deterministic tests (A–Z + 1 live-QA-derived regression test) | **27/27 passed** — `conversation_engine/tests/test_ai_native_calendar_v286b.py` |
| `conversation_engine/tests` full suite (excl. `_live.py`) | **339/339 passed, 0 errors** — verified both under the project's default `-n 2 --dist loadscope` and under `-n 0` |
| `backend/tests/test_calendar_foundation_v286a.py` (V2.8.6a regression) | **22/22 passed** |
| Calendar/connector regression (`test_iter9_ingestion_and_google_calendar`, `test_google_calendar_write_sync`, `test_iter18_apple_calendar_connector`, `test_oauth_loopback_hosts`) | **57/57 passed under `-n 0`**; the same 4-file combination shows pre-existing, non-deterministic pytest-xdist worker-sharing flakiness under the project's default `-n 2` config (14–16 spurious errors, varying run to run) — reproduced **without** any V2.8.6b file in the run, confirmed pre-existing and out of this sprint's scope |
| `situations/life_memory/life_os/llm` | **44/44 passed** |
| Provider Manager | **23/23 passed** (a real `GEMINI_API_KEY` was available this session, so the previously-skipped live-enrichment test ran and passed instead of skipping — not a regression) |
| `compileall` / blocking lint (`flake8 --select=E9,F63,F7,F82`) / `git diff --check` | **all clean** |
| Hardcoding audit (manual grep of the full diff for `calendar intent`/`reminder`/`appointment`/`meeting`/`domani`/`tomorrow`/`dentist`/`notaio`/`travel`/`study`/`work`/`medical`/`house`) | **clean** — the one match is prose guidance in `prompt.py` explicitly telling the AI never to route on those words, not a code branch |
| Security audit (ownership scoping on every query, no raw Google payload/token/secret in any Observation, no broad delete, confirmation required, uncertainty blocks write) | **verified** — all four `calendar_event_drafts`/`ingestion_events` queries in `calendar_caps.py` are scoped by `user_id`; `test_w` asserts no token/secret substrings and a fixed payload-key whitelist |
| Performance (no live Google call per turn, no new polling/cron, no mandatory second LLM call) | **verified** — `get_calendar_events` is local-only; writes are on-demand and rare |
| **Provider-real eval** (5 scenarios: simple read, create-with-confirmation, correction, Situation-linked, arbitrary vague reminder) | **5/5 passed**, run serially (`-n 0`) — parallel xdist workers triggered transient `LLMNetworkError` connection contention against the live Gemini endpoint in this environment; isolated/serial runs were reliably clean. No real Google Calendar event was created, modified or cancelled by this eval (pure `_call_ai` reasoning-shape checks, no tool execution) |
| **Chrome QA** | **executed**, in an isolated environment: a second backend instance on an alternate port (`CALENDAR_PROVIDER_MODE=fake`, process-env override only — the real `.env` file was never modified) and a dedicated throwaway account (`qa.calendar.v286b@ora.app`), fully cleaned up afterward. Covered: empty-calendar honest read, create-with-confirmation, consent-gating (honest `consent_required` message), create-partial honesty (Google not connected), correction/reschedule (found and fixed the false-negative honesty bug above, then re-verified live), cancel-with-confirmation. No real Google Calendar write occurred. One unrelated pre-existing console `409` was observed during account setup, before any Calendar-specific request; every Calendar-specific network call returned `200 OK` |
| Real backend boot with the QA-mode instance | **PASS** — full index/module startup banner identical to V2.8.6a's, no regression |
| No real Google/Apple call anywhere in this batch | **confirmed** — fake provider throughout deterministic tests and Chrome QA; provider-real eval never executes a tool handler |
| Commit / push | **NO** — STOP for CPO review |

## V2.8.6b — Final Pre-Commit Hardening Gate (this batch)

**Status: two CPO-identified gaps closed — update on a cancelled event, and calendar.read
revocation vs. cached Google events. No design reopened, no new feature, no Context Graph
change, no FreeBusy, no reminder-architecture change, no UI change, no Google real writes.**

| Item | Stato |
|------|--------|
| `update_calendar_event` on a cancelled event | **fixed** — explicit typed rejection (`status="rejected"`, `failure_kind="event_cancelled"`) before consent/Google, no DB mutation, no reactivation, no recreation, no exception reaches the reasoning loop |
| `get_calendar_events` after `calendar.read` revocation | **fixed** — `source: "google_external"` items are now gated on `calendar.read` consent (previously ungated); `source: "ora_managed"` items remain visible regardless, per CPO decision |
| Cached Google events survive revocation (not deleted) | **confirmed** — revocation only changes visibility, never touches `ingestion_events` |
| Cross-user isolation on the read path | **confirmed** — unchanged, still scoped by `user_id` on every query |
| No live Google call during read | **confirmed** — `_active_instance_id` resolves from local `connector_instances`, no network call |
| Additional bug found and fixed while adding the CPO's read-policy tests | `get_calendar_events`'s default time window used the server's **naive local** `datetime.now()`; compared via lexicographic string range against event strings that are always UTC-aware, this could silently exclude real events depending on the server's timezone offset. Fixed to default to UTC-aware "now" |
| `partial` semantics re-confirmed | Local success + Google sync unconfirmed → `status="partial"`, message says the local change was saved and Google is not confirmed — never "not moved", never "Google was updated" |
| New deterministic tests | 7 added (1 cancelled-update + 6 read-policy A–F) — suite now **34/34 passed** |
| `conversation_engine/tests` full suite (excl. `_live.py`) | **346/346 passed, 0 errors** |
| `backend/tests/test_calendar_foundation_v286a.py` | **22/22 passed** |
| Calendar/connector regression (serial, per the method already proven reliable) | **57/57 passed** |
| `situations/life_memory/life_os/llm` | **44/44 passed** |
| Provider Manager | **23/23 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit on the changed file | **clean** — no new matches |
| Security audit | **clean** — no token/secret in the file, all queries remain `user_id`-scoped, no broad delete, no consent bypass |
| Provider-real eval repeated | **NO** — prompt, `CognitiveDecision`, tool descriptions and AI-facing semantics did not change in this gate (only runtime-side consent/validation logic) |
| Chrome QA repeated | **NO** — no UI-visible behavior changed; the two fixes are runtime-internal (an error path and a consent gate), not reachable through a different observable flow than what was already verified live |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up (non-blocking, not decided as requirements)

1. The pre-existing pytest-xdist worker-sharing flakiness in `backend/tests/` (see regression row above) is unrelated to Calendar but was newly characterized this session — worth a dedicated fix in a future batch (likely: align the remaining `asyncio.get_event_loop()`-style tests in that directory to the `@pytest.mark.asyncio` convention already proven in `conversation_engine/tests/`).
3. Google FreeBusy-based availability (as opposed to local-event-derived conflict detection) remains a documented, undecided future follow-up, not built in V1.

## V2.9.1 — Life Change Signal / Continuous Life Reasoning foundation — CPO APPROVED / CLOSED OUT

**Status: event-driven foundation only. `life mutation → LifeChangeSignal` and nothing beyond
it. V2.9.1 CREATES NO PROACTIVE SUGGESTIONS, sends no notification, adds zero LLM calls, zero
external calls and zero background work. "SO WHAT?" is V2.9.2; "SHOULD I SPEAK?" is V2.9.3.**

| Item | Stato |
|------|--------|
| Pre-existing equivalent primitive | **none found** — repo-wide search for change/domain-event/outbox/signal semantics returned nothing user-scoped, persistable, idempotent and notification-neutral, so a minimal new primitive was created rather than bending a semantically different legacy model |
| New module `backend/life_signals/` (`models.py`, `repository.py`, `service.py`, `emitters.py`) | **created** — follows the `context_graph/` module convention exactly |
| New collection `life_change_signals` | **created** — indexes `(user_id,id)` unique, `(user_id,dedupe_key)` unique+sparse, `(user_id,status,created_at,id)`; registered in `server.py` startup like every other subsystem |
| Emission point | `conversation_engine/ai_core/loop.py` — in production the **single** call site of `SituationService.apply` / `ContextGraphService.apply` / `MemoryGovernanceService.process` and the executor of Calendar + Life OS write capabilities. Zero changes to any mutation subsystem's own code or contract |
| Persist-before-signal | **enforced per adapter** — proposals (`response_mode=act`), consent denials, CLARIFY/REJECT, revision conflicts, explicit no-ops, reads and failures all emit nothing |
| Idempotency | **enforced twice** — adapter-level dedupe keys derived from stable mutation identity (entity ref + revision, or reasoning epoch + capability), plus a unique sparse storage index. Adapters fail closed when no stable discriminator exists rather than risk a duplicate storm |
| No recursion | **enforced** — emitting never mutates a life entity, never creates a Graph edge, never creates a suggestion, never emits a second signal |
| Canonical refs | **reused** (`context_graph.models.is_recognized_ref`) — no second namespace; an unrecognized ref is refused, not stored. Graph signals point at the edge **subject** (the `lce_` edge id is not a canonical ref) with the object as a deterministic `affected_ref` |
| Graph expansion | **absent by design** — `affected_refs` holds only refs already present in the mutation result; bounded expansion belongs to V2.9.2 |
| Failure isolation | **implemented** — `emit()` never raises, `_emit_life_change` wraps it again; the already-committed mutation is never rolled back, and the failure stays observable via the `life_change_signal_failures` trace counter and a warning log |
| Privacy | **refs + technical metadata only** — no conversation text, entity payload, document content, token or secret; verified by a test asserting the exact stored key set |
| Mutation sources CONNECTED | Situation, Life Memory, Context Graph, Life OS (plan/object), Calendar |
| Mutation sources DEFERRED | **Documents** — its persistence is spread across many `documents.update_one` call sites in `documents/` and `documents/intelligence/` with no single canonical AI-native mutation boundary; connecting it would have required duplicating emission logic or designing a boundary this sprint was told not to design |
| Proactive Engine | **untouched** — no generator added, none removed, scoring/gate/notification policy unchanged; coexistence preserved |
| Context Broker | **untouched** — deliberately NOT given a `life_change_signals` source; the signal feeds future asynchronous reasoning, not the per-turn answer |
| Context Graph / Memory governance / Calendar semantics | **unchanged** |
| LLM calls added | **0** |
| External calls added | **0** |
| Cron / polling / scheduler / background worker | **0** |
| V2.9.1 tests | **32/32 passed** (`conversation_engine/tests/test_life_change_signal_v291.py`) |
| `conversation_engine/tests` (excl. `_live.py`) | **378/378 passed, 0 errors** |
| V2.8.6b calendar suite | included above — **34/34 passed** |
| V2.8.6a foundation | **22/22 passed** |
| Calendar connector regression (`-n 0`, the method already documented as reliable) | **57/57 passed** |
| `situations` / `life_memory` / `life_os` / `llm` | **44/44 passed** |
| Proactive Engine | **232/232 passed** (untouched; run as a safety check) |
| Provider Manager | **23/23 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms and zero keyword branches in the new module or the production diff |
| Security audit | **clean** — every signal-store query user-scoped, no secret/token/`.env`, no delete of any kind in the module, no cross-user read or write, no raw payload, no new external call |
| Provider-real Gemini | **NOT REQUIRED / NOT RUN** — V2.9.1 introduces no AI decision and changes no prompt, `CognitiveDecision` field or tool description |
| Chrome QA | **NOT REQUIRED / NOT RUN** — purely infrastructural; no user-visible behaviour changed, no UI touched, no new surface |
| Commit / push | **DONE** — CPO approved; committed and pushed to `origin/feature/ora-quiet-premium-design-system` |

### Follow-up recommended for V2.9.2 (non-blocking, deliberately not built)

1. **Impact reasoning consumer** — read a bounded batch via `list_pending`, resolve authorized context through the existing Context Broker, reason once per batch (not once per mutation), `mark_processed`.
2. **Bounded graph/context expansion** at consume time, using the existing `ContextGraphService.relevant_edges` depth cap — never at emission time.
3. **Documents emission boundary** — decide a single canonical AI-native mutation boundary for Documents, then connect it the same way (CPO decision, deliberately not taken here).
4. **Processed signal retention/compaction** — `processed` signals currently accumulate; a retention rule should be decided once a consumer exists and its replay needs are known.
5. **More robust retry/recovery for signal persistence failure** — today a failed emit loses the derived event (observable via the `life_change_signal_failures` trace counter and a warning log) with no automatic replay; a durable retry path is worth designing once a consumer exists.
6. **Claiming/lease semantics** — if V2.9.2 ever runs more than one consumer per user concurrently, `list_pending` will need a claim/lease; deliberately not built while no worker exists.
7. **`_CALENDAR_CAP_KINDS` duplication** — `life_signals/emitters.py` restates the Calendar capability names by value rather than importing `loop.py`'s `_CALENDAR_WRITE_CAPS` (that module pulls in heavy AI Core wiring). Low risk and indirectly covered by tests H/J/K, but worth collapsing if a shared lightweight constants module ever appears.

## V2.9.2 — AI-native Impact Reasoning ("SO WHAT?") — CPO APPROVED / CLOSED OUT

**Status: reasoning only. `LifeChangeSignal → bounded context → one reasoning call →
ImpactAssessment`. V2.9.2 DOES NOT DECIDE WHETHER TO SPEAK — no suggestion, no notification, no
message, no tool execution. "SHOULD I SPEAK?" is V2.9.3.**

| Item | Stato |
|------|--------|
| New module `backend/life_reasoning/` (`models.py`, `repository.py`, `prompt.py`, `context.py`, `service.py`) | **created** — follows the `life_signals/` module convention |
| New collection `life_impact_assessments` | **created** — indexes `(user_id,id)` unique, `(user_id,batch_key)` unique+sparse, `(user_id,created_at desc)`, `(user_id,focal_refs)`; registered in `server.py` startup |
| Consumer | **explicitly invoked** (`ImpactReasoningService.run_pass(user_id)`) — no worker, cron, scheduler or polling |
| Batching | ref-overlap + Context Graph connection via deterministic union-find; correlated signals cost **1** AI call, unrelated signals are never merged. Bounds: ≤5 signals/pass, ≤3 batches, ≤5 signals/batch |
| Cost model | `no change ⇒ no signal ⇒ no AI call` preserved end to end — a user with no pending signals returns before any retrieval (verified by test P) |
| Context resolution | **existing infrastructure only** — `ContextBroker` Stage B, `ContextGraphService.relevant_edges`, `timezone_service`, `ToolRegistry`. No second context loader |
| Graph expansion | bounded, seeded from the signal's own refs, depth ≤2, ≤10 edges; never global, never creates a relation |
| Epistemic model | **reused verbatim** from Memory/Graph (`epistemic_status`, `authority`, evidence refs, confidence) — no third vocabulary |
| Impact `kind` | six general-purpose technical categories (dependency/risk/opportunity/constraint/conflict/missing_information) — no domain taxonomy |
| Attention fields | **absent by construction** — no `notify`/`send_now`/`surface_home`/`interrupt`/`batch_notification`/`message_to_user`; a model that emits them has nowhere to put them (test N) |
| Chain-of-thought | **never requested, never persisted** — `reason_summary` is a bounded conclusion (test U) |
| Capability awareness | names only; `capability_hint` validated against the live registry so an invented capability is dropped (test O2). Nothing is ever executed (test O) |
| Failure honesty | provider unavailable/unparseable → no assessment, signals stay pending (I/I2); context unreadable → deferred with **zero** AI calls (J); persistence failure → signals not consumed (K); consume only after persist (L) |
| Idempotency | deterministic order-independent `batch_key` + unique sparse index; replay consumes without a second assessment (B/B2); a new signal yields a new distinguishable assessment (G) |
| Provider access | **exclusively Provider Manager** — V2.8.3a failover and circuit breaker preserved; static test forbids any direct vendor import (Z) |
| Commercial neutrality | prompt-level contract asserted by test (Z3): optimise for the user's interest, never for whoever might be selling; no company/product/vendor/brand/offer, no invented price or rate |
| Proactive Engine / Context Broker / Context Graph / Memory governance / Calendar semantics | **all untouched** |
| V2.9.2 tests | **35/35 passed** (`conversation_engine/tests/test_impact_reasoning_v292.py`) |
| `conversation_engine/tests` (excl. `_live.py`) | **413/413 passed, 0 errori** |
| V2.9.1 | **32/32 passed** |
| V2.8.6b Calendar | **34/34 passed** |
| V2.8.6a foundation | **22/22 passed** |
| Context Broker V3 | **11/11 passed** |
| Context Graph + Situation + Memory | **67/67 passed** |
| `situations`/`life_memory`/`life_os`/`llm` | **44/44 passed** |
| Calendar connector regression (`-n 0`) | **57/57 passed** |
| Provider Manager | **23/23 passed** |
| Proactive Engine (untouched, safety check) | **232/232 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms in executable code (docstrings excluded from the scan, since they state the rule rather than break it) |
| Security audit | **clean** — every query user-scoped, no secret/token/`.env`, no delete in the module, no external call beyond the LLM provider, no tool write, no notification |
| **Provider-real eval** | **5/5 passed** against real Gemini via Provider Manager — arbitrary life change without invention, unstated dependency discovery, context-grounded consequence citing only supplied refs, insufficient-evidence honesty, vendor-neutral option comparison. Run serially (`-n 0`) |
| Chrome QA | **NOT REQUIRED / NOT RUN** — V2.9.2 is internal; no UI, no user-visible behaviour changed, no new surface |
| Commit / push | **DONE** — CPO approved; committed and pushed to `origin/feature/ora-quiet-premium-design-system` |

### Follow-up recommended for V2.9.3 (non-blocking, deliberately not built)

1. **Attention / intervention policy** — read recent assessments, decide whether, when and how to surface anything; this is where `relevance` finally meets a delivery decision.
2. **Proactive Engine adapter** — route an assessment that clears the attention gate into the existing scoring/dedupe/notification-policy machinery rather than building a parallel one.
3. **Assessment retention/supersession** — assessments about the same `focal_refs` accumulate; a supersession or compaction rule should be decided once V2.9.3 defines what "still relevant" means.
4. **Concurrency** — `run_pass` is safe to replay (the unique `batch_key` index prevents duplicates) but two concurrent passes for the same user can both spend a reasoning call before one loses the race; a claim/lease becomes worthwhile only when a scheduler exists.
5. **Documents emission boundary** — still deferred from V2.9.1; documents already reachable through the Context Broker can serve as evidence, but no Documents mutation emits a signal yet.

## V2.9.3 — Attention & Intervention Intelligence ("SHOULD I SPEAK?") (this batch)

**Status: the three-question sequence is complete. V2.9.3 decides whether reasoning is worth the
user's attention and through which surface. Silence is a first-class outcome; the deterministic
system gate can only ever make the result quieter; nothing is ever pushed.**

| Item | Stato |
|------|--------|
| New module `backend/life_attention/` (`models.py`, `repository.py`, `prompt.py`, `context.py`, `gate.py`, `service.py`) | **created** — follows the `life_signals/`/`life_reasoning/` convention |
| New collection `life_attention_decisions` | **created** — indexes `(user_id,id)` unique, `(user_id,decision_key)` unique+sparse, `(user_id,created_at desc)`, `(user_id,focal_refs)`, `(user_id,delivery,defer_until)`; registered in `server.py` startup |
| Consumer | **explicitly invoked** (`AttentionService.run_pass(user_id)`) — no worker, cron, scheduler or polling |
| Relevance ≠ permission | `ai_delivery` (model) and `delivery` (system) are separate persisted fields; **only `delivery` is acted on** |
| System gate one-way property | **enforced and asserted for every possible model choice** — a downgrade may only move quieter along silent ← defer ← home ← ask_user ← propose_action ← notify |
| Silence | **first-class** — `silent` decisions persisted; zero suggestions created (test B/M) |
| Safety not in the prompt | the model is **not shown** `notifications_allowed`, `quiet_hours`, `likely_sleep`, `interruption_cost`, `user_dismiss_rate` (test X2) |
| Interruption cost | **deterministic** — resolved clock via `timezone_service`, real calendar time-overlap, measured suggestion volume, recorded dismissal history. Never inferred from calendar titles |
| Proactive Engine integration | `regenerate` refactored by **extraction** into `submit_candidates`, shared by legacy generators and the AI-native path — identical scoring, gate, dedupe, learning, notification policy. No second pipeline |
| Legacy generators | **untouched**, coexisting; the 232-test Proactive Engine suite is unchanged |
| Pre-existing scoring ceiling | **found and fixed** — `generic` candidates need 0.55 but importance/urgency/confidence alone cap at ~0.54 without a deadline or goal link (which every legacy generator happens to have, hiding it). Added one optional domain-neutral `quality_hint`; legacy leaves it `None` and scores identically |
| Dedupe vs legacy | **ref-based**, never fuzzy title — one user-facing item per entity (test Q) |
| Push dispatch | **structurally impossible** — the reused notification policy never returns `send_now` (test T) |
| Tool execution | **none** — `ask_user`/`propose_action` write nothing anywhere (tests R/S) |
| Learning | bounded — repeated dismissal downgrades to Home, never a permanent blacklist (test H2); a first-time user gets a neutral multiplier (test I) |
| Home surfacing | reuses the existing suggestion model and card; AI-native items distinguishable by `source="life_reasoning"`, verified through `home_suggestions()` |
| V2.9.3 tests | **37/37 passed** |
| `conversation_engine/tests` (excl. `_live.py`) | **450/450 passed, 0 errors** |
| V2.9.2 / V2.9.1 | **35/35** / **32/32 passed** |
| Context Broker V3 | **11/11 passed** |
| Context Graph + Situation + Memory | **67/67 passed** |
| Calendar V2.8.6b / V2.8.6a | **34/34** / **22/22 passed** |
| `situations`/`life_memory`/`life_os`/`llm` | **44/44 passed** |
| Calendar connector legacy (`-n 0`) | **57/57 passed** |
| Provider Manager | **23/23 passed** |
| **Proactive Engine (module touched — full regression)** | **232/232 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms in executable code |
| Security audit | **clean** — every query user-scoped, no secret/token/`.env`, no delete, no push dispatch, no tool execution, no external call beyond the LLM provider |
| **Provider-real eval** | **6/6 passed** against real Gemini via Provider Manager — high value not silent, low value silent, speculative never pushed, missing-information can justify asking, opportunity surfaced vendor-neutrally, and the system gate demonstrably overruling the model |
| Chrome QA | see the report — conditional requirement, environment actively in use |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up recommended for V2.9.4 (non-blocking, deliberately not built)

1. **Deferred decision re-evaluation** — `defer_until` is persisted and indexed but nothing re-reads it yet; a re-evaluation path belongs with whatever eventually schedules passes.
2. **Actual delivery** — `notify` currently resolves to a Home item with a deferred batch window; a real push channel needs its own consent flow, transport and rate policy.
3. **Continuous orchestration** — signals → reasoning → attention are three explicitly-invoked passes; nothing chains them automatically yet. This is the natural place for the scheduler all three sprints deliberately avoided.
4. **Claiming/lease** — replay is safe (unique `decision_key`), but two concurrent passes for one user can both spend a call before one loses the race.
5. **Assessment/decision retention** — both stores accumulate; a compaction rule should follow once re-evaluation semantics exist.
6. **Legacy `likely_driving` heuristic** — still governs the legacy path only; worth replacing with a real activity signal rather than calendar-title keywords if that path is ever modernised.

## V2.9.4 — Continuous Life Reasoning orchestration (this batch)

**Status: the pipeline is now autonomous and event-driven. A real mutation produces a signal, a
reasoning pass and an attention decision without anyone invoking anything — and an idle system
costs literally nothing. Autonomy did NOT increase how often ORA speaks: silence remains the most
common outcome.**

| Item | Stato |
|------|--------|
| New module `backend/life_orchestration/` (`state.py`, `service.py`, `scheduler.py`) | **created** — thin coordinator; owns no cognition, executes no tool, sends nothing |
| Why a separate module (not `life_reasoning/orchestration.py` as sketched) | the dependency chain is strictly one-way (`life_attention → life_reasoning → life_signals`); an orchestrator inside `life_reasoning` importing `life_attention` would close an **import cycle** |
| New collection `life_orchestration_state` | **created** — indexes `(user_id)` unique, `(next_retry_at)`; registered in `server.py` startup |
| Trigger | `loop.py::_emit_life_change`, only when a signal was really persisted. Best-effort: never blocks, never raises, never awaits a provider |
| Event-driven guarantee | worker blocks on `asyncio.Queue.get()`; deferrals get a one-shot alarm; recovery runs once after boot. **Static AST test asserts no loop in the module contains a sleep call** |
| Cost chain | `no change ⇒ no signal ⇒ no wake-up ⇒ no reasoning ⇒ no AI call` — verified end to end, including against the live provider |
| Idle user cost | **zero** — pending work is checked before the lease is taken, so an idle pass writes no document at all |
| Coalescing | one pending pass per user; a 20-mutation burst yields **1** pass; a change arriving mid-pass sets a redo flag instead of being lost |
| Lease | one collection, one granularity (the whole pass). TTL 120s, crash-reclaimable, released only by its owner, opaque non-PII owner id. Prevents double AI spend only — the unique `dedupe_key`/`batch_key`/`decision_key` indexes already make duplicate persistence impossible |
| Lease acquisition hardening | written explicitly (try-take → check-exists → insert) instead of relying on upsert provoking a unique-index violation, so a missing index degrades to "no lease" rather than silently handing out two |
| Bounded pass | `MAX_CYCLES = 2`; sub-service budgets unchanged (V2.9.2 ≤5 signals/≤3 batches, V2.9.3 ≤5 assessments/≤3 batches) |
| Failure isolation | impact failure never fabricates an assessment; attention failure leaves the assessment recoverable; both record **per-user** exponential backoff (60s→1h), distinct from the Provider Manager's global per-vendor circuit breaker |
| Durability | in-process queue is an accelerator, never the queue of record — dropped wake-up / full queue / cancelled task / dead process cost latency, never work |
| Shutdown | cancels rather than drains; Mongo pending state is the source of truth |
| No recursion | assessments, decisions and suggestions emit no signals; a full pass ends holding exactly the one signal it consumed |
| Legacy coexistence | `regenerate()` is never called by the orchestrator — it reaches the Proactive Engine only through the `submit_candidates` path separated in V2.9.3, so automatic reasoning adds **no** legacy generator cost |
| Deferred decisions | **partially operational, deliberately** — one-shot timer + startup recovery + `defer_status="due"` marker make them discoverable. Re-running attention on the same batch is NOT done: it needs a second decision for the same assessments, i.e. a change to V2.9.3's approved idempotency contract (CPO decision) |
| V2.9.4 tests | **39/39 passed** (`conversation_engine/tests/test_orchestration_v294.py`) |
| `conversation_engine/tests` (excl. `_live.py`) | **489/489 passed, 0 errors** |
| V2.9.3 / V2.9.2 / V2.9.1 | **104/104 passed** combined |
| **Proactive Engine (reached automatically now — full regression)** | **232/232 passed** |
| Calendar V2.8.6b + V2.8.6a | **56/56 passed** |
| `situations`/`life_memory`/`life_os`/`llm` | **44/44 passed** |
| Calendar connector legacy (`-n 0`) | **57/57 passed** |
| Provider Manager | **23/23 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — the only matches are the English noun "work" in two log strings |
| Security audit | **clean** — all lease/state queries user-scoped; the only cross-user reads are the once-per-boot recovery sweeps, each `.limit()`-capped; queue bounded; opaque owner id; no secret, no `.env`, no delete, no push, no tool execution |
| **Provider-real smoke** | **2/2 passed** against real Gemini — full pipeline signal→impact→attention end to end, plus the idle-user zero-cost guarantee |
| Chrome QA | see the report |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up recommended for V2.9.5 (non-blocking, deliberately not built)

1. ~~**Deferred re-evaluation semantics**~~ — **closed by the hardening batch below.**
2. **Multi-process coordination** — the lease makes concurrent passes safe and cheap, but wake-ups are process-local: with N uvicorn workers only the process that served the mutation schedules one. Others rely on startup recovery. A shared trigger becomes worthwhile when ORA actually runs multiple processes.
3. **Actual delivery** — `notify` still resolves to a Home item; a real push channel needs consent flow, transport and rate policy.
4. **Retention/compaction** — signals, assessments, decisions and orchestration state all accumulate; nothing is deleted, deliberately, since the history is reasoning and audit material.
5. **Opportunistic wake-up on user activity** — login/Home-open could also trigger a best-effort pass; not added because the signal trigger already covers the cases that matter and this would add cost to every session start.

## V2.9.4 — Deferred re-evaluation final hardening (this batch)

**Status: closes the one open point left by the batch above. A `defer` decision whose moment
arrives is now genuinely RECONSIDERED by the AI — refreshed operational context, one Attention
call, the identical V2.9.3 gate — never merely flagged. "AI DECIDES. SYSTEM GUARANTEES." now covers
reconsideration too: the system bounds automatic cost, it never manufactures a verdict.**

| Item | Stato |
|------|--------|
| `life_attention/models.py` | `root_attention_key_for` (order-independent), `decision_key_for(..., revision=1)` (rev 1 ≡ pre-hardening key), `MAX_AUTOMATIC_DEFER_REEVALUATIONS = 3`, `AttentionDecision` gains `root_attention_key`/`attention_revision`/`supersedes_decision_id`/`superseded_by`/`automatic_re_evaluations_used`/`auto_re_evaluation_exhausted`, `AttentionPassReport` gains `defer_reevaluations_*`/`defer_budget_exhausted`/`defer_to_*` counters |
| `life_attention/repository.py` | `list_due_deferred` now excludes superseded/exhausted chains; new `latest_for_root`, `chain_for_root`, `mark_superseded` (called only after the replacement is durably persisted), `mark_budget_exhausted` |
| `life_attention/service.py` | `_evaluate_batch` factored into shared `_build_decision` (identical AI-vs-gate rules for a first evaluation and every reconsideration); new `reevaluate_due_deferrals` / `_reevaluate_one` / `_assessments_by_ids` — re-fetches the SAME assessments, never re-runs Impact Reasoning, never re-derives |
| `life_orchestration/service.py` | `_run_cycles` gains a third bounded step (due deferral → `reevaluate_due_deferrals`, guarded by a zero-AI existence check); `mark_due_deferrals` (flag-only) replaced by `has_due_deferral` (read-only existence check) |
| `life_orchestration/scheduler.py` | `_deferred_wake` / `recover_pending` no longer reconsider inline — they only confirm a deferral is still due (no AI) and queue `schedule_user_reasoning`; the actual reconsideration happens inside the lease-protected `run_user_pass`, exactly like every other AI call in this pipeline |
| Persistence order | build → persist new revision → **only then** mark previous superseded → done. No Mongo transaction introduced — this ordering already makes every step independently safe to retry or lose |
| Failure honesty | provider failure / invalid output / persistence failure all leave the old defer current, unsuperseded, with its automatic budget unspent |
| Budget semantics | exhausting `MAX_AUTOMATIC_DEFER_REEVALUATIONS` is a **cost** marker (`auto_re_evaluation_exhausted`) — the delivery stays whatever the AI last chose, never forced to `silent`; a brand-new `LifeChangeSignal` opens a fresh, unbounded root |
| New tests | **26/26 passed** (`conversation_engine/tests/test_deferred_reevaluation_v294.py`, A–Z) |
| V2.9.4 orchestration (updated) | **39/39 passed** (`conversation_engine/tests/test_orchestration_v294.py`) |
| V2.9.3 / V2.9.2 / V2.9.1 / conversation_engine / Proactive Engine / Life OS / Calendar / Context Broker / Context Graph / Situation / Memory / Provider Manager | **553/554 passed** — the one failure is `test_real_gemini_enrichment_optional` (`tests/test_ai_provider_manager.py`), an opt-in live-network test of the unrelated document-intelligence analyzer that failed on a real Gemini timeout + real OpenAI 429s; it touches no file this sprint changed |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms in the new reconsideration code |
| Provider-real | **NOT REQUIRED** — the Attention prompt/contract did not change semantically; reconsideration reuses the exact same call shape V2.9.3's provider-real gate already covered |
| Chrome QA | **NOT REQUIRED** — no UI surface changed |
| Commit / push | **NO** — STOP for CPO review |

## PX1.1 — Product Experience Foundation (this batch)

**Status: the interface finally belongs to one product. One theme, one navigation model, one
geometry, one vocabulary — the foundations PX1.2–PX1.9 will build on. No screen was redesigned;
the house was.**

| Item | Stato |
|------|--------|
| **Calendar write consent (P0)** | **real bug found and fixed** — the document pipeline auto-called `confirm_event(sync_to_google=True)` above a 0.90 confidence score, writing real Google Calendar events unattended. Now unconditionally refuses; legacy preference inert and always reported `False` |
| Theme unification | `tokens.color`/`tokens.shadow` resolved dark while the provider resolved light; ~40 files read that static export at module load. Both now light, behind one reversible `CONSUMER_LIGHT_ONLY` constant |
| Information Architecture 2.0 | `Home · Vita · ORA · Attività · Documenti` + account set apart; Memoria demoted to a trust surface (reachable from Profilo); Documenti promoted out of the account menu |
| New route | `app/(tabs)/attivita.tsx` — named, empty, human copy; PX1.6 fills it |
| Desktop geometry | new `PageContainer` (≤800px centred decision column); applied to Profilo and Documenti, the two screens that set no width at all. Contextual rail (320px) reserved, renders nothing |
| Dev diagnostics | moved to `src/components/dev/DevDiagnostics.tsx`, `__DEV__`-gated — zero provider/model names in consumer settings |
| Profilo | "Prossimamente" group removed (spese/obiettivi/email/banche); Memoria link added |
| Snooze | human-time primitive (`src/components/ui/humanTime.ts`); no "(ore)" input; unchanged ISO wire format |
| New doc | `docs/PRODUCT_EXPERIENCE.md` — owns the binding rule *NEVER EXPOSE IMPLEMENTATION STATE WHEN A HUMAN STATE EXISTS* |
| Frontend tests | **PX1.1 guards pass** (`src/shell/px11Foundation.test.ts`, A–N); `actionLabels` and `softExit` still green |
| Typecheck | `tsc --noEmit` **clean** |
| Backend touched | **YES — only** `documents/intelligence/service.py`, for the consent fix authorised by §23–24. Cognitive core untouched |
| **Chrome QA (desktop + mobile)** | **completed on a real signed-in account** — Home, Vita, ORA, Attività, Documenti, Profilo, Impostazioni, snooze dialog; desktop 1440x900 and phone 375x812. Console clean on a fresh session |
| **QA-found regressions, all fixed** | raw `confidence` badges in Documents (card + detail panel); horizontal stats/filter rows vertically compressed to half height (**pre-existing**); "Documenti" truncating in the phone bar once labels reached the 12px floor; nested `<h1>` in `ContextsHeader` (**pre-existing**, invalid HTML + hydration error); "più tardi oggi" proposing 05:23 at 02:23 |
| Typography floor | `MIN_READABLE_FONT_SIZE = 12` declared and applied to navigation chrome (was 10) and document metadata (was 11) |
| Backend documents regression | **17/17 passed**, including the new consent test |
| Commit / push | **NO** — STOP for CPO review |

### Deferred by design

PX1.2 Home 3.0 · PX1.3 Workspace 2.0 · PX1.4 Conversation Experience · PX1.5 Vita/Memory trust UX ·
PX1.6 Activity Center · PX1.7 Documents UX 2.0 · PX1.8 Profile/Settings/Permissions ·
PX1.9 Motion/States/Accessibility.
