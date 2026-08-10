# ORA — Development State

Last updated: 2026-08-10 (Prompt 6.1.1 — Memory epistemic authority)

## Prompt 6.1.1 — Epistemic authority (this batch)

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
