# ORA — Product Capability Audit (CTO)

| Campo | Valore |
|-------|--------|
| Data audit | 2026-08-06 |
| Branch | `feature/life-experience-ai` |
| Tip commit base | `09404f1` (`feat: introduce AI-first Life Experience`) |
| Ambito | Solo lettura codice + docs + evidenze di test già documentate |
| Implementazioni in questo audit | **Nessuna** (solo documentazione) |
| Mobile nativo | **NON VERIFICATO** (never) su tutte le feature UI |
| PRODUZIONE | **Non assegnata** a nessun modulo |

> **Aggiornamento post-audit (2026-08-06, branch `feature/life-experience-ai-documents`):** implementato upload documento reale (file picker Expo) + AI Document Understanding (Gemini) in Life Experience, precedentemente marcato "upload binario V2 incompleto" nella riga Life Setup sotto. Vedi `LIFE_EXPERIENCE_REAL_DOCUMENTS.md`, `AI_DOCUMENT_UNDERSTANDING.md`, `LIFE_DOCUMENT_MAPPING.md`, `CROSS_DOCUMENT_REASONING.md`, `LIFE_EXPERIENCE_DOCUMENT_VERIFICATION.md` per il dettaglio onesto (per tipo documento) — questo audit di base resta lo snapshot originale del `09404f1`.

### Legenda stato (unica ammessa)

| Stato | Significato |
|-------|-------------|
| `NON ESISTE` | Assente come capacità prodotto |
| `ARCHITETTURA` | Predisposto / stub / contratti; **non** operativo |
| `PROTOTIPO` | Codice/UI parziale; non affidabile end-to-end |
| `PARZIALE` | Parte del flusso reale; pezzo critico mancante o non verificato |
| `FUNZIONANTE` | Codice+API operativi in locale; verifica E2E incompleta o solo unit/API |
| `VERIFICATO` | Evidenza pytest + (tipicamente) Playwright web e/o real smoke documentato |
| `PRODUZIONE` | Ops production-ready — **non usato** in questo audit |

### Livelli di verifica (non confondere)

| Livello | Cosa prova |
|---------|------------|
| unit | pytest / unit service |
| API | HTTP contro FastAPI |
| browser | Playwright / Chromium su Expo **web** |
| real smoke | Provider reale (Google Calendar, OCR host, Gemini opzionale) |
| never | Nessuna evidenza |

**PREDISPOSTO ≠ FUNZIONANTE.** Stub che ritornano `[]` / `{stub:true}` = `ARCHITETTURA`.

Documenti correlati: `CAPABILITY_MATRIX.md`, `FEATURE_STATUS.md`, `PRODUCTION_READINESS.md`.

---

## 1. Capability Matrix

Vedi tabella completa: [`docs/CAPABILITY_MATRIX.md`](./CAPABILITY_MATRIX.md).

Sintesi moduli richiesti:

| Modulo | Stato |
|--------|-------|
| Conversation | VERIFICATO |
| Intent | VERIFICATO |
| Semantic | VERIFICATO |
| AI Life Strategist | VERIFICATO |
| Life Setup | VERIFICATO |
| Goal | VERIFICATO |
| Action | VERIFICATO |
| Study | VERIFICATO |
| Travel | VERIFICATO |
| Documents V2 | VERIFICATO |
| Knowledge Graph | FUNZIONANTE |
| Brain | PARZIALE |
| Home | VERIFICATO |
| Proactive | VERIFICATO |
| Google Calendar | VERIFICATO |
| Google Login | PARZIALE |
| Apple Login | PROTOTIPO |
| Maps | PARZIALE |
| Notifications | NON ESISTE |
| Email | ARCHITETTURA |
| WhatsApp | ARCHITETTURA |
| Finance | ARCHITETTURA |
| Settings | FUNZIONANTE |
| Authentication | VERIFICATO |
| Memory | PARZIALE |
| Search | VERIFICATO |
| Projects | PARZIALE |
| Document Intelligence | VERIFICATO |
| Flashcard | VERIFICATO |
| Interrogami | VERIFICATO |
| Voice | PROTOTIPO |

---

## 2. Architecture

### Stack

- **Frontend:** Expo 54 + React Native + TypeScript + expo-router  
- **Backend:** FastAPI (`server.py` thin) + Uvicorn  
- **DB:** MongoDB (Motor async)  
- **Auth:** JWT HS256 + bcrypt; Google/Apple ID-token verify (`social_auth/`); Emergent Google session **legacy gated**  
- **AI:** Provider Manager `backend/llm/` — priorità Gemini → OpenAI → Ollama → Emergent; non required at boot  
- **Design:** dark-first tokens (`frontend/src/theme/tokens.ts`)

### Forma moduli (confini)

```
Input (Home / Parla / Life Experience / Documents / deep-link)
    → Conversation Engine (orchestrator, NOT chatbot)
        → Semantic Engine (extract + gaps) [optional enrich Gemini]
        → Intent Engine (classify → flow)
        → Goal Engine (shadow upsert / context)
        → Action Engine (study | travel | event | …)
            → Study Plans / Travel Projects
            → Documents V2 / Brain links / Maps artifacts
            → Google Calendar drafts/sync (consent)
        → Proactive Engine (suggestions ≤3)
    → Home V2 aggregator (ranking 1.2, presentation dedupe)
```

Life Experience è il first-launch: `life_setup` + `ai_life_strategist` (reasoning loop) → `life_profiles` / sync Goal+Proactive benefit — **non** wizard.

### Feature flags (env, da `.env.example`)

Esempi rilevanti: `GOAL_ENGINE_ENABLED`, `PROACTIVE_ENGINE_ENABLED`, `CONVERSATION_ENGINE_ENABLED`, `SEMANTIC_ENGINE_ENABLED`, `SEMANTIC_GEMINI_ENABLED`, `LIFE_SETUP_ENABLED`, `AI_LIFE_STRATEGIST_ENABLED`, `DOCUMENT_AI_ENABLED`, `DOCUMENT_OCR_ENABLED`, `CALENDAR_*`, `BEHAVIOR_*`, `APPLE_CALENDAR_ENABLED`, `OLLAMA_ENABLED`.

### Cosa non è architettura “pronta”

- Canali Email / Open Banking / WhatsApp / Weather: **adapter stubs only** (`life_setup/adapters_stubs.py`, `proactive_engine/generators/stubs.py`, CE `StubOriginAdapter`).
- Push notifications: policy meta in Proactive, **nessun delivery channel**.
- Apple Login / Apple Calendar: codice+flag; device/real = never.

---

## 3. Pipeline (diagramma)

```mermaid
flowchart TB
  subgraph clients [Client Expo web / RN]
    HomeUI[Home V2]
    Parla[PARLA CON ORA]
    LifeUX[Life Experience /life-setup]
    DocsUI[Documenti V2]
    ActionUI[Action session UI]
  end

  subgraph api [FastAPI /api]
    Auth[/auth]
    CE[/conversation]
    SE[/semantic]
    IE[/intent]
    AE[/action-engine]
    SP[/study-plans]
    TP[/travel-projects]
    GE[/goals]
    PE[/suggestions]
    HomeAPI[/home]
    Docs[/documents]
    Strat[/strategist]
    LS[/life-setup]
    GCal[/connectors/google-calendar]
  end

  subgraph data [MongoDB]
    Users[(users / user_identities)]
    LifeP[(life_profiles / life_setup_sessions)]
    Conv[(conversation_sessions)]
    Goals[(goals / goal_events)]
    Plans[(study_plans / study_sessions / travel_projects)]
    DocsC[(documents / calendar_event_drafts)]
    Sug[(proactive_suggestions)]
    HomeC[(home_snapshots / home_item_state)]
    LG[(life_nodes / life_edges / node_knowledge)]
  end

  subgraph stubs [Stubs predisposti — non operativi]
    EmailStub[Email]
    WAStub[WhatsApp]
    FinStub[Open Banking]
    WxStub[Weather/Health]
  end

  HomeUI --> HomeAPI
  Parla --> CE
  LifeUX --> LS
  LS --> Strat
  DocsUI --> Docs
  ActionUI --> AE
  CE --> SE
  CE --> IE
  CE --> AE
  AE --> SP
  AE --> TP
  AE --> GE
  AE --> Docs
  AE --> GCal
  PE --> HomeAPI
  GE --> HomeAPI
  stubs -.->|never invent facts| PE
  stubs -.->|honest stub session| CE
  Auth --> Users
  LS --> LifeP
  CE --> Conv
  Docs --> DocsC
  HomeAPI --> HomeC
  Strat --> LifeP
```

---

## 4. All APIs (inventory da codice)

Mount: `ALL_ROUTERS` in `backend/routers/__init__.py` sotto prefisso `/api`.

### Core / health

| Method | Path |
|--------|------|
| GET | `/api/` |
| GET | `/api/health` |

### Auth — `/api/auth`

`POST /register`, `/login`, `/google-session`, `/google`, `/apple`, `/link/google`, `/link/apple`, `/logout`  
`GET /providers`, `/identities`, `/me`  
`DELETE /link/{provider}`

### Decisions — `/api/decisions`

list/top/CRUD-ish + `start|partial|postpone|blocked|complete|dismiss|history|explanation|resolve`

### Legacy — `/api/tasks`, `/api/priorities`

### Life Graph — `/api/life-graph`

vocabulary, seed, nodes/edges CRUD, decision↔node links

### Knowledge — `/api/knowledge`

schemas, node properties CRUD/history

### Auto-link — `/api/auto-link`

analyze/reanalyze/proposals accept|reject

### Context — `/api/context`

assemble/refresh/latest/history/snapshots

### Permissions — `/api/permissions`

registry, consents grant/revoke, audit, admin sync

### Connectors — `/api/connectors`

registry + status

### Ingestion — `/api/ingestion`

events, stats

### Google Calendar — `/api/connectors/google-calendar`

oauth start/callback(+fake), instances, calendars, select, sync, refresh, revoke, status, config-status

### Apple Calendar — `/api/connectors/apple-calendar`

config-status, connect, instances, select, sync, disconnect

### Daily — `/api/daily`

today/tomorrow/date/refresh

### Behavior — `/api/behavior`, `/api/behavior-shadow`

profile/metrics/patterns/timeline/confidence; shadow rules/evals/stats

### Documents — `/api/documents`

upload, list, hub, preferences, study, quiz/answer, admin actions, search/intelligent, calendar drafts/sync, CRUD, analyze/reanalyze, events confirm/dismiss/calendar, ask, …

### Home — `/api/home`

`GET ""`, `/situation`, `POST /actions`, `/refresh`

### Intent — `/api/intent`

`POST /classify`

### Action Engine — `/api/action-engine`

open, sessions get/answer/back/draft/cancel/complete/search-docs/preview/modify/confirm/merge-project

### Study plans — `/api/study-plans`

list/get/sessions/action/complete/postpone/sync/retry/patch/delete

### Travel projects — `/api/travel-projects`

list/get/retry-sync/delete

### Goals — `/api/goals`

CRUD, search, merge, archive, timeline

### Proactive — `/api/suggestions`

list, regenerate, search, get, explain, dismiss/accept/complete/snooze, notification-policy

### Conversation — `/api/conversation`

list, start, resume, resume-token, sessions get, message/continue/cancel/pause, history, summary

### Semantic — `/api/semantic`

extract, gaps, patch conversation entities, confirm-entity

### Strategist — `/api/strategist`

status, next-question

### Life Setup — `/api/life-setup`

status, start, answer, skip, upload-doc, explain, complete, cancel, profile, profile/correct, profile/delete-fact, stubs/{name}

### LLM — `/api/llm`

providers, status, preferences

### Memory — `/api/memory`

add, list, ask

### Admin — `/api/admin/demo/refresh`

**Nota:** inventariato da decorator nei router; OpenAPI live non ri-eseguito in questo audit docs-only.

---

## 5. Database (collezioni / indici)

Indici creati allo startup (`server.py`) e/o `ensure_indexes` / `ensure_ready` dei servizi:

| Area | Collezioni (evidenza codice) |
|------|------------------------------|
| Auth | `users`, `user_identities` |
| Legacy | `tasks` |
| Decisions | `decisions`, `decision_action_history` |
| Life Graph | `life_nodes`, `life_edges` |
| Knowledge | `node_knowledge` |
| Auto-link | `link_proposals` |
| Context | `context_snapshots` |
| Memory | `memories` |
| Permissions | `permission_consents`, `permission_capability_meta`, `permission_audit` |
| Connectors | `ingestion_events`, `connector_instances`, `secret_vault`, `google_oauth_sessions`, `data_revocation_plans` |
| Documents | `documents`, `calendar_event_drafts` (+ file storage locale) |
| Home | `home_item_state`, `home_snapshots`, `home_insights` (nomi da service) |
| Action | `action_sessions`, `action_projects`, `reminders` (soft), `study_plans`, `study_sessions`, `travel_projects` |
| Goals | `goals`, `goal_events` |
| Proactive | `proactive_suggestions`, `proactive_learning` |
| Conversation | `conversation_sessions` |
| Life Setup | `life_setup_sessions`, `life_profiles` |
| Behavioral | collezioni via `BehavioralIntelligenceService.ensure_ready` / shadow |

Schema: **non-destructive** indexes at startup; nessuna migrazione wipe documentata come default.

---

## 6. Modules (dettaglio onesto)

### Authentication — VERIFICATO

Email register/login JWT: evidenza HTTP + browser login nei E2E Documents/Home/Life.  
Logout server **non** blacklista token. Storage web AsyncStorage.

### Google Login — PARZIALE

`POST /auth/google` + FE helpers; unit mock JWKS. Reale: bloccato da `GOOGLE_WEB_CLIENT_ID` (docs SOCIAL_AUTH). Emergent `google-session` legacy gated.

### Apple Login — PROTOTIPO

UI + `POST /auth/apple` + unit nonce/relay. Keys/Services ID / device: **never**. Profilo/settings mostrano non configurato quando manca env.

### Conversation Engine — VERIFICATO

Orchestrator entry; origini stub email/whatsapp/open_banking oneste. pytest + Playwright travel/study via CE. Non è chatbot.

### Intent — VERIFICATO

Deterministic IT KB; corpus ≥124; Playwright psychology (no ticket flow). LLM enrich opzionale.

### Semantic — VERIFICATO

Extract + Gap Analyzer; domande atomiche; pytest 17 + Playwright gap scenarios. Gemini opzionale.

### AI Life Strategist — VERIFICATO

`reasoning_loop`, benefit engine, document strategy, Gemini structured + fallback IT. pytest life experience + foundation; Playwright life-experience-ai / life-setup-strategist. **Gemini live** in questo audit: NON VERIFICATO (fallback sì).

### Life Setup / Life Experience — VERIFICATO

Session/profile APIs; anti-wizard UX; Home/Proactive benefit cards. Open: upload binario V2 reale da conversazione; consent UI calendario bozze strategist. Stubs adapter.

### Goal — VERIFICATO

Shadow Study/Travel; Home `goal_*` + dedupe; API goals; **no Goal tab** by design. pytest + Playwright shadow/home-goal-aware.

### Action / Study / Travel — VERIFICATO

Guided AE; study plan + travel project; Google sync real smoke documentato (2026-08-05). Maps: deep link + Nominatim soft. Mobile never.

### Documents V2 + Document Intelligence + Flashcard + Interrogami — VERIFICATO

Pipeline hub/dynamic detail; OCR host; flashcards/quiz browser E2E; search intelligente. Mobile never. OpenAI live spesso skipped.

### Knowledge Graph — FUNZIONANTE

API piena; UI prodotto assente → non “Life OS knowledge browser”.

### Brain — PARZIALE

Adapter/link da AE study/travel/CE/Home; merge soft; **nessuna Brain screen**.

### Life Graph — FUNZIONANTE

CRUD API; scarsa esposizione UI.

### Home — VERIFICATO

Aggregator ranking 1.2, Adesso/Perché/situazione/resume/ORA TI CONSIGLIA; Playwright home-v2 / goal-aware / presentation-dedupe.

### Proactive — VERIFICATO

Decision gate IF/WHEN/HOW/WHY; generatori reali; stubs always empty (tested). Push: non inviato.

### Google Calendar — VERIFICATO

Fake suite + real create/update (docs). Checklist delete/reconnect incompleta. Credenziali richieste per ogni ambiente.

### Apple Calendar — PROTOTIPO

Router + iOS settings gate; web mock; device never.

### Maps — PARZIALE

Travel MapsInfo + document event links; stima distanza; honesty labels; non Google Directions API traffic.

### Notifications — NON ESISTE

Nessun `expo-notifications` / FCM path prodotto. Solo `notification-policy` metadata.

### Email / WhatsApp / Finance — ARCHITETTURA

Stub espliciti. UI Profilo: Email & Messaggi / Banche & Wallet / Dashboard spese = «In arrivo».

### Voice — PROTOTIPO

Origin `voice` + mic UI → hint «digita»; STT non cablato (CHANGELOG/PRODUCT).

### Memory — PARZIALE

Add/list OK; `/memory/ask` LLM-gated (503 senza provider).

### Search — VERIFICATO

`/documents/search/intelligent` + browser E2E Documents V2.

### Projects — PARZIALE

`action_projects`, study/travel come progetti vivi; **hub Progetti** NON ESISTE come feature UX.

### Settings — FUNZIONANTE

Identities, Google calendar manage, Apple iOS row; social link gated.

### Decisions / Daily / Permissions / Behavior / Context / Auto-link / LLM

Da FUNZIONANTE a VERIFICATO parziale su percorsi Home; resolve AI e alcune UI secondarie LLM/credential gated. Non sono il “wow” primario attuale.

---

## 7. Verifications (evidenza documentata — non ri-eseguita qui)

Questo audit **non** ha ri-lanciato pytest/Playwright; si basa su `*_VERIFICATION.md` + `CHANGELOG_AI.md` + codice.

| Area | Evidenza tipica | Livello |
|------|-----------------|---------|
| Life Experience | `test_life_experience.py` 30p (con foundation); Playwright `life-experience-ai` 2p | unit+browser |
| Life Setup foundation | strategist 19p; Playwright 3p | unit+browser |
| Semantic | 17p; Playwright gap 2p | unit+browser |
| Conversation | 9p; Playwright 2p | unit+browser |
| Proactive | 232p; Playwright 2p | unit+browser |
| Home V2 / goal-aware | ~39p; Playwright home specs | unit+browser |
| Goal shadow | 9p; Playwright 2p | unit+API(+browser) |
| Intent | 147p combined; Playwright psychology | unit+browser |
| Action / Study / Travel | suites + Playwright FULL UI | unit+browser+real Google |
| Documents V2 | 15p + browser script flashcards/Interrogami | unit+API+browser (+Gemini/Google prior) |
| Google Calendar write | 15p fake + real create/update checklist | unit+real partial |
| Social auth | unit mock; real Google/Apple login never | unit |
| Mobile | — | **never** |

File chiave: `HOME_V2_VERIFICATION.md`, `DOCUMENTS_V2_VERIFICATION.md`, `GOOGLE_CALENDAR_VERIFICATION.md`, `SOCIAL_AUTH_VERIFICATION.md`, `INTENT_ENGINE_VERIFICATION.md`, `ACTION_ENGINE_VERIFICATION.md`, `STUDY_*`, `TRAVEL_*`, `SEMANTIC_ENGINE_VERIFICATION.md`, `FUNCTIONAL_AUDIT.md`, `DEVELOPMENT_STATE.md`, `CHANGELOG_AI.md`.

---

## 8. Test coverage (mappa)

### Backend pytest (suite presenti sotto `backend/tests/` + package tests)

Coprono iter storiche (iter8–23), documents, intelligent docs, google calendar, social auth, home, goal, proactive, conversation, semantic, intent, action, study, travel, AI life setup, life experience, LLM manager, behavioral, permissions, life graph, knowledge, auto-link, context, local smoke.

Package: `backend/ai_life_strategist/tests/`.

### Frontend Playwright (`frontend/e2e/`)

`home-v2`, `home-goal-aware`, `home-presentation-dedupe`, `action-engine`, `study-action-flow`, `travel-action-flow`, `intent-psychology`, `proactive-engine`, `conversation-engine`, `semantic-extraction` (+ gap), `goal-engine-shadow`, `life-setup-strategist`, `life-experience-ai`.

### Non coperto / debole

- iOS/Android device E2E  
- Apple Login/Calendar real  
- Email/WhatsApp/Finance real (by design stub)  
- Voice STT  
- Push delivery  
- Production load/security pen-test  
- Full Google Calendar delete/reconnect matrix  
- Strategist Gemini live obbligatorio (fallback tested)

---

## 9. Roadmap top-10 (solo gap trovati, impatto utente)

1. **Upload documento reale end-to-end da Life Experience** — chiude il loop “parla → carica rogito/libretto” oltre path sintetico.  
2. **Consent UI esplicita bozze calendario dallo Strategist** — fiducia + Google write sicuro.  
3. **STT reale su PARLA** (o rimuovere mic come promise) — voce oggi delude.  
4. **Push / local notifications** per scadenze studio/bollette — Proactive senza delivery = silenzio.  
5. **Smoke nativo iOS+Android** sui 5 flussi core — altrimenti store impossibile.  
6. **Google Login reale + Apple Login onesto** (o nascondere CTA) — onboarding consumer.  
7. **Email connector (read-only) o de-claim totale** — Profilo «Email» oggi ARCHITETTURA.  
8. **Hardening auth (JWT revoke, CORS allowlist, rate limit)** — prerequisito qualsiasi ship.  
9. **Finance read-only (Open Banking) o rimozione Dashboard spese** — evita falsa aspettativa.  
10. **Brain/Knowledge UI minima o merge silenzioso documentato** — oggi valore nascosto in API.

Non includere qui “riscrivere lo stack” o feature decorative: solo gap evidenti dall’audit.

---

## 10. Final verdict

### Uso quotidiano?

**Sì, limitato, su Expo web + backend locale**, per: organizzare studio/esami, viaggi, documenti intelligenti, Home che decide “cosa fare adesso”, conversazione strutturata (non chat).  
**No** come sostituto di email, WhatsApp, banca, assistente vocale, o app store-ready.

### Casi d’uso che reggono (wow)

- «Devo studiare psicologia» → Intent corretto → piano sessioni → flashcard/Interrogami → Home goal-aware → (opz.) Google sync.  
- «Fra due settimane parto / Vibo» → Semantic gap questions atomiche → Travel Project + Maps link + calendario.  
- Upload dispensa/bolletta → utility dinamica, eventi, search.  
- Life Experience first-launch: domande con beneficio italiano, non questionario; card Home «Adesso posso…».  
- ORA TI CONSIGLIA su skip studio / prep viaggio (senza inventare email/meteo).

### Delusioni prevedibili

- Mic voce → «digita il testo».  
- Profilo Email / Banche / Spese / Obiettivi tab → «In arrivo» o assenti.  
- Apple «Accedi» / Apple Calendar su web.  
- Notifiche push assenti.  
- Mobile “come sul telefono” **mai** dimostrato.  
- AI resolve/ask senza chiavi LLM → 503 onesto ma freddo.  
- Emergent/Google bridge legacy confonde “funziona online”.

### Verdetto CTO

ORA è un **Life OS locale avanzato (VERIFICATO su web)** con motore decisionale/conversazionale reale su Study/Travel/Documents/Home/Life Experience.  
Non è **PRODUZIONE**. Non è completo sui canali vita (email/WA/finance/voice/push).  
La disciplina degli stub onesti è un punto di forza ingegneristico; il rischio prodotto è **overclaim** se marketing parla di integrazioni predisposte come vive.

---

## 11. Commit di questo audit

Messaggio: `docs: complete product capability audit`  
Branch: `feature/life-experience-ai`  
Base tip pre-audit: `09404f1` (`feat: introduce AI-first Life Experience`)  
Hash del commit docs: quello con il messaggio sopra su questo branch (`git log -1 --grep="complete product capability audit"`).

File prodotti:

- `docs/PRODUCT_AUDIT_MASTER.md` (questo)
- `docs/CAPABILITY_MATRIX.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/FEATURE_STATUS.md`
- aggiornamento one-liner `docs/CHANGELOG_AI.md`
