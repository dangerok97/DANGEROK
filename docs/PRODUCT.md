# ORA — Product (struttura reale)

## Personal Context Retrieval V3 (V2.8.2)

ORA può chiedere il minimo contesto personale necessario per decidere meglio,
senza trasformare la conversazione in un router di domini. Il modello formula un
`ContextNeed` semantico; il broker recupera evidence bounded da fonti user-owned,
preserva conflitti, authority e provenance, poi il modello ragiona nuovamente.
Situation è l'anchor di continuità, non una categoria. Profile, Memory, Life OS,
Goal, file e calendar metadata sono evidence source; nessuna source decide
l'intento e nessuna retrieval promuove automaticamente nuova Memory.

Ultimo aggiornamento: 2026-08-16 — Home → ORA first-turn handoff + location presence.

## ORA (production conversation)

**ORA** is the production conversational surface (`/ora`, Ambient tab, Home ask bar).  
**AI Core** is the cognitive runtime behind it.  

### Situation continuity (V2.8.1)

ORA can keep one general-purpose Situation across turns and sessions: something
expected, ongoing, changed, resolved or cancelled in the user's life. The AI
decides semantic continuity; the system owns canonical identity, revision,
ownership and provenance. Situation is neither Life Memory nor a domain flow.
Linked plans/objects are changed only when the AI separately invokes successful
Life OS capabilities.
**Life OS** is execution/persistence.  
**GenerativeObjects** are AI-created work products.  
**Goal Workspace** is the persistent work surface.  
**`/ora-ai` is DEV/diagnostic only** — not linked from Home, Ambient, Continue, or Workspace.

There is one ORA: you talk, ORA understands context, may research, creates and adapts useful work, and keeps plans organized. Not a menu of domain wizards. Revealable cards use a single front/back contract. Home / Contesti / Goal Workspace share the same plan identities. Rich text for answers (no raw `###` / `$$` as UX).

### Device presence vs residence (V2.7.1)

**Canonical:** Location is sensor evidence. Presence is contextual state. Meaning remains governed/AI-interpreted. Memory remains governed.

On **web**, ORA can ask for **foreground** device location while you use the app (never on silent launch). Settings → Posizione: *Disattivata* or *Durante l'uso di ORA*. Background location is **not available**. Native apps: not yet supported. If the last fix is outdated, ORA refreshes via the browser (Chrome Location already allowed does **not** require re-enabling settings — only ORA’s own preference must be *Durante l'uso*). Failed refresh wording stays honest: timeout ≠ permission denied. Asking from **Home** opens `/ora` and completes the same turn automatically (including location) — you should not need to type the question twice.

**Residence** (Profile / “dove vivo”) and **current presence** (“dove sono adesso”) are different. Device GPS does not overwrite where you live. Temporary user statements and goal-specific origins stay authoritative for that conversation. Raw GPS is short-lived sensor evidence — never Life Memory.

### Files as evidence (V2.6 / V2.6.1 / V2.6.2)

Users can attach files in the shared OraComposer (paperclip). A file is **contextual evidence**, not a workflow. When new evidence supersedes prior assumptions, ORA can **reconcile** the same plan/object (`replace_items`) instead of appending duplicates. A later conversational fact (e.g. a changed time/budget/date constraint) can likewise adapt the **same** artifacts — idempotency only prevents identical writes inside one turn, not future replanning. Goal Workspace **Fonti** shows human labels (e.g. “Fornito da te”), never internal ids.

## Vision

ORA è il sistema operativo della vita quotidiana: riduce il carico cognitivo mostrando **cosa fare adesso**, con decisioni ordinate, memoria personale e documenti.

**ORA IS AI-FIRST.** L’LLM possiede comprensione dell’obiettivo e la decisione sul prossimo passo (rispondere / chiedere / recuperare contesto / usare un tool / agire). Il backend fornisce contesto, capacità, stato e governance — non sequenze di slot. Prompt 7.x (requirements deterministici) è abbandonato. Prompt 7 V2 introduce il nucleo cognitivo AI-native (foundation); ricerca web e piani dominio arriveranno come tool, non come wizard.

## Design — ORA Quiet Premium

Linguaggio visivo **calmo, editoriale, premium** (Apple HIG; riferimenti Calendar/Journal/Reminders/Health, Things 3, Notion Mobile, Arc Search, Day One — non Linear). Accent **Deep Indigo**. Temi Light / Dark / System. Primitive UI in `frontend/src/components/ui/`. Glass solo su tab bar / sheet / controlli floating.

### Login Quiet Premium V1

`/login` è Immersive (canvas, niente card): wordmark ORA, headline *Tutto ciò che conta, nel momento giusto.*, *Accedi per continuare.*, poi Apple → Google → Email. Google Login V2 usa GIS popup sul web e Google Sign-In native su iOS/Android; se Google non è configurato, la CTA è realmente disabilitata e Email/registrazione restano operative. Registrazione via **Nuovo? Crea un account**. Post-auth invariato (`routeAfterAuth` → Life Setup o Home).

### Signature Language — Application Shell V1

ORA si presenta in tre modalità: **Ambient** (navigazione vita quotidiana), **Focus** (una guida / un compito), **Immersive** (attenzione piena). Barra Ambient primaria: Home · Contesti · ORA · Memoria · Profilo. Su desktop la rail Ambient è una colonna compatta (~80px), non una sidebar SaaS a metà schermo; il contenuto Home si bilancia nella regione rimanente. **ORA** al centro apre la superficie di produzione `/ora` (AI Core — stesso Ask Bar della Home e Continua da Goal Workspace), non una chat e non Aggiungi. Documenti resta raggiungibile da Profilo. Le guide Action Engine usano chrome Focus (←, Continua, progresso “N di M” quando noto) con colonna decisione più stretta della Home; niente chip “capito” che competono con la domanda.

### Contesti — Life Map V1

**Contesti non è il menu delle categorie di ORA. È la mappa della vita che ORA ha compreso.**

Domanda implicita: *di quali parti della mia vita ORA ha una comprensione?* — non *quale categoria vuoi aprire?*

- **In questo periodo** — situazioni vive con identità propria (piani di studio / progetti viaggio attivi), non priorità Home.
- **La tua vita** — ambiti persistenti già presenti nel Life Profile con fatti conosciuti (nessuna tassonomia fissa vuota).
- Nessun “+ Nuovo contesto”, nessun CRUD cartelle, nessuna dashboard a icone.
- Dettaglio contesto generico **non** in V1: le situazioni aprono route esistenti (`/study-plan/[id]`, `/travel-project/[id]`); gli ambiti sono editoriali finché non esiste un detail sensato.
- Empty: *ORA sta ancora conoscendo la tua vita.*
- **Prompt 5.1/5.2:** Contesti legge preferibilmente `GET /api/life-map`. Gemini (`LIFE_MAP_GEMINI`, default off) può produrre situazioni novel *grounded* (open semantics, senza enum palestra/gym) mostrate in “In questo periodo” in modo generico; ambiguità restano nel modello, non in UI Contesti. Se l’API fallisce, resta il compose frontend Prompt 5.

### Memoria — Life Memory V1

**Memoria non è l’elenco dei record nel database. È ciò che ORA ha imparato e trattiene su di te.**

| Superficie | Domanda |
|------------|---------|
| **Home** | Cosa conta adesso? |
| **Contesti** | Quali ambiti/situazioni compongono la mia vita ora? |
| **Memoria** | Che cosa sa e ricorda ORA di me? |
| **Documenti** | Quali materiali/file ho dato a ORA? |
| **ORA (Conversation)** | Come comunico con ORA? |

- Fatti duraturi in linguaggio naturale (*Lavori nella Guardia di Finanza*, *Vivi a Tarquinia*).
- Gruppi solo se c’è contenuto reale (nessuna tassonomia fissa vuota).
- Provenienza in progressive disclosure; **“Da chiarire”** apre un chiarimento Focus con ORA (linguaggio naturale, non form).
- Empty: *ORA sta ancora imparando a conoscerti.* → CTA quiet verso conversazione ORA.
- API: `GET /api/life-memory` + `POST /api/life-memory/clarify/*` (legacy `/api/memory` resta note + ask).
- **DATABASE RECORD ≠ MEMORY.** **MEMORY ≠ CURRENT CONTEXT.** **AI ≠ EVIDENCE.**

### Home Quiet Premium V1 (+ polish 2.1)

La Home risponde a **“Cosa conta per me in questo momento?”** — non è dashboard, widget wall o chat. Gerarchia: Ambient Header → Daily Focus (superficie + Focus Glow sentito) → Ask Bar (Apple Search) → Focus Horizon (sezioni temporali) → Priorità tipografiche → Aggiornamenti → Situazione → Continua. CTA a tre livelli. Stessi dati `HomeV2Response`; quando esiste un piano Life OS attivo e actionable, quello è il focus/continue (Goal Workspace), non uno StudyPlan/Decision legacy scaduto.

I **Life Objects** (Casa, Auto, Università, Lavoro, …) sono il **modello vivente della realtà dell’utente**. L’AI (Gemini) è **consultant**; il backend è **autorità** su tipo, titolo, merge e campi (Semantic Validator prima del persist). Conversation, Goal, Documents, Brain, Proactive e Home **continuano a esistere** come satelliti. Aggiornamenti **shadow**; Home resta Goal-aware; Home V3 oggetti solo predisposta (`LIFE_OBJECT_HOME_UI_ENABLED=0`).

## Utenti

Persone che vogliono una priorità unica chiara (non un task manager generico), con calendario, documenti e memoria collegati.

## Navigazione frontend (expo-router)

| Route | Schermata | Ruolo |
|-------|-----------|--------|
| `/login` | Login Quiet Premium | Immersive canvas (no card): headline *Tutto ciò che conta, nel momento giusto.*; Apple → Google → Email; CTA **Nuovo? Crea un account**; stessi flussi auth + `routeAfterAuth` / Life Setup gate |
| `/(tabs)` → index | Home Quiet Premium | Daily Focus + Ask Bar + Horizon + priorità/aggiornamenti (stesso ranking API) |
| `/(tabs)/contesti` | Contesti Life Map V1 | Mappa della vita che ORA conosce (non menu categorie): “In questo periodo” + “La tua vita” da dati reali |
| `/(tabs)/ora` | ORA entry | Ask Bar → produzione `/ora` → AI Core (mai chat; `/ora-ai` solo DEV) |
| `/life-setup` | Life Setup Gate (primo avvio) | Sprint 4/4.1/4.2: conversazione Quiet Premium (intro → domanda → thinking in-thread → ack AI o fallback sicuro → sintesi → **Entra in ORA**); copy AI fact-bounded con intent domanda fissato dal planner (`question_goal`); Esci/Più tardi solo su resume (`?resume=1` / `start.resumed`); posizione opzionale per città; MLC Sprint 3; gate Sprint 2B; Home solo dopo complete valido |
| `/conversation` | Entry Conversation Engine | Bridge a guida AE (mai chat thread) |
| `/situazione` | Situazione completa | Vista reale da CTA Home |
| `/(tabs)/memoria` | Memoria Life Memory V1 | Cosa ORA ha imparato su di te (fatti duraturi); non Q&A, non Contesti |
| `/(tabs)/documenti` | Documenti | Lista/upload/dettaglio (nascosto dalla barra primaria; da Profilo) |
| `/(tabs)/aggiungi` | Aggiungi | Capture (nascosto dalla barra primaria) |
| `/(tabs)/profilo` | Profilo | Account, link Documenti, placeholder moduli, logout |
| `/settings` | Impostazioni | AI Provider + account/calendari |
| `/manage-calendars` | Gestione calendari | Selezione calendari Google |
| `/connect-apple-calendar` | Apple Calendar | Flusso nativo iOS |
| `/how-it-works` | Onboarding informativo | Spiega Google Calendar |
| `/document/[id]` | Dettaglio documento | Insights + azioni |
| `/action/[sessionId]` | Guida Action Engine (Focus) | Una domanda per schermo; chrome ← / Continua; no Ambient nav |
| `/study-plan/[id]` | Piano di studio | Progresso, sessioni, flashcard, Interrogami |
| `/action/open` | Bridge apertura guida | Da Home Apri/Organizza/Inizia |

## Moduli prodotto

### 1. Autenticazione

- **Scopo:** una sola identità ORA (JWT) per email, Google e Apple.
- **Stato:** email **operativa**; Google Login V2 **implementato** (GIS web + SDK native, verifica ID token backend + identity store), live OAuth ancora dipendente da credenziali/build reali; Apple implementato.
- **Flusso:** FE ottiene ID token → backend verifica JWKS → `user_identities` → JWT ORA.
- **Backend:** `/api/auth/register|login|google|apple|link/*|identities|providers|me|logout`.
- **DB:** `users` + `user_identities`.
- **Esterni:** Google Cloud OAuth clients; Apple Sign In (App ID / Services ID / key). Legacy Emergent opzionale. In locale, `localhost` e `127.0.0.1` vanno entrambi registrati come Authorized JavaScript Origins (origin diversi). Google Login è identità; Google Calendar è un OAuth separato.
- **Docs:** `docs/SOCIAL_AUTH_*.md`.
- **Aperti:** credenziali reali; device iOS/Android; revoca JWT server-side.

### 1b. Life Object Engine (modello canonico — SHADOW + AI enrichment)

- **Scopo:** verità canonica sulla realtà dell’utente (HOME, VEHICLE, UNIVERSITY, JOB, …). Gli altri motori restano e aggiornano questi oggetti.
- **Stato:** **SHADOW FUNZIONANTE** — writes paralleli ON; **nessuna modifica UX importante**; Home V3 oggetti **PREDISPOSTO / OFF**.
- **Flusso:** Documents V2 → Life Object AI → **Semantic Validator** → oggetto canonico (titolo deterministico, assimilazione mutuo/bolletta, gap su concetti, Health 2.0) → enrichment; Goal ottiene `life_object_id`; Travel/Study aggiornano in parallelo.
- **Identity vs State:** identità stabile (indirizzo/targa/…) separata dallo stato che cambia (fornitori, importi, rate).
- **Backend:** `/api/life-objects/*` (+ narrative/questions/insights/health/history/enrich); flag `LIFE_OBJECT_ENGINE_ENABLED`, `LIFE_OBJECT_HOME_UI_ENABLED`, `LIFE_OBJECT_GEMINI`.
- **Docs:** `LIFE_OBJECT_ENGINE.md`, `LIFE_OBJECT_REASONING.md`, `LIFE_OBJECT_ARCHITECTURE.md`, `LIFE_OBJECT_VERIFICATION.md`.
- **Aperti:** Home V3 UI; wiring Conversation/Proactive più ricco.

### 2. Home V2 — Intelligence dashboard

- **Scopo:** rispondere “cosa è più utile sapere o fare adesso” con ranking multi-fonte (documenti, calendario, studio, decisioni, …).
- **Stato:** **operativo (web)** — `GET /api/home`, ranking `home-rank-1.2` Goal-aware (flag) senza Gemini, UI **PARLA CON ORA** + Adesso/Perché/azioni tipizzate/situazione/priorità/**ORA TI CONSIGLIA**/insights/resume Continua; banner Google compatto; no Goal tab; **no chat**.
- **Flusso UI:** Ask / PARLA → produzione **`/ora` → AI Core** (Life OS); Continua da Goal Workspace rientra nella stessa sessione ORA. Item legacy possono ancora aprire Conversation Engine → Action Engine.
- **Proactive:** `docs/PROACTIVE_ENGINE_PRODUCT.md` — Email/Finance/Weather/WhatsApp predisposti, non operativi.
- **Backend:** `backend/home/` + adapters fail-soft (+ Action Engine + Conversation adapters).
- **DB:** `home_snapshots`, `home_item_state`, `home_insights` (+ fonti esistenti).
- **Docs:** `docs/HOME_V2_*.md`.
- **Aperti:** native mobile non verificato.

### 2x. Life Experience + AI Life Strategist (first-launch conversation)

- **Scopo:** prima conversazione naturale per costruire contesto di vita (domini in qualsiasi ordine) con reasoning loop benefit-driven o upload documenti — **non** wizard/questionario/settings.
- **Stato:** **Life Experience V1 conversazionale** — first contact (chi è ORA + una domanda aperta), acknowledgement contestuale, explain orientato al beneficio, documenti come acceleratore opzionale, momento finale con restituzione dai facts reali, CTA **Entra in ORA** (stesso flusso gate).
- **Dopo complete:** modulo invisibile; Home mostra **benefici** (non Life Setup); interrupt → soft resume «ORA può aiutarti ancora di più».
- **Flag:** `LIFE_SETUP_ENABLED`, `AI_LIFE_STRATEGIST_ENABLED`, `AI_LIFE_STRATEGIST_GEMINI`.
- **Non fatto:** Email / Open Banking / WhatsApp / Weather (solo stub).
- **Docs:** `LIFE_EXPERIENCE.md`, `AI_REASONING_LOOP.md`, `AI_PROMPTING_GUIDE.md`, `AI_DECISION_POLICY.md`, `CONVERSATION_EXPERIENCE.md`, `BENEFIT_ENGINE.md`.

### 2z. Conversation Engine — entry orchestrator (NOT a chatbot)

- **Scopo:** unico ingresso linguaggio naturale → collaborazione guidata a un passo → artefatti (Goal, Project, calendario, …) via motori esistenti.
- **Stato:** **foundation implementata** — `backend/conversation_engine/`, API `/api/conversation/*`, FE PARLA CON ORA + bridge `/action/[sessionId]`.
- **Flusso:** testo/voce-stub → **Semantic Extraction → Intent → Gap Analyzer** → Goal shadow → Action Engine → Projects/Brain/Proactive/Home.
- **Flag:** `CONVERSATION_ENGINE_ENABLED` (default ON).
- **Origini stub:** email / whatsapp / open_banking (struttura only).
- **Docs:** `docs/CONVERSATION_ENGINE_*.md`, `SESSION_MODEL.md`, `ORCHESTRATION.md`.
- **Limiti:** STT non cablato; origini email/WA/banking non simulate.

### 2y. Semantic Extraction + Gap Analyzer

- **Scopo:** estrarre significato strutturato (date, destinazione, materia, importi…) e decidere la **prossima domanda utile** — senza duplicare Intent.
- **Stato:** **implementato** — `backend/semantic_engine/`, API `/api/semantic/*`, wiring CE→AE, FE summary Partenza/Destinazione/Ritorno.
- **Bugfix:** «Fra due settimane parto.» → «Dove andrai?» (mai «Quando parti e quando torni?»).
- **Flag:** `SEMANTIC_ENGINE_ENABLED` (default ON). Gemini opzionale.
- **Docs:** `docs/SEMANTIC_ENGINE_*.md`, `ENTITY_MODEL.md`, `GAP_ANALYZER.md`.

### 2a. Intent Classification Engine — single intent brain

- **Scopo:** capire *cosa vuole fare l’utente* da testo libero (e meta) e produrre un oggetto **Intent** riusabile (Home, Parla, Documents, …).
- **Stato:** **operativo** — regole deterministiche + KB italiana; Gemini opzionale (`INTENT_LLM_ENRICH`); bassa confidence → chiarimento, mai flusso sbagliato.
- **Flusso:** priorità/testo → `intent_engine` → Intent → Action Engine sceglie il flow.
- **Esempio:** “devo studiare l'esame di psicologia” → study / exam_preparation → domanda data esame (non biglietto).
- **Backend:** `backend/intent_engine/`, `POST /api/intent/classify`.
- **Docs:** `docs/INTENT_ENGINE_*.md`.

### 2b. Action Engine — Guided priority flows

- **Scopo:** trasformare una priorità Home in una breve conversazione a chip (una domanda per schermo) che crea calendario, promemoria, progetto e aggiorna Brain — mai una pagina vuota.
- **Stato:** **implementato** — API `/api/action-engine/*`, flussi study/event/travel/medical/admin/generic/clarify; FE `ActionEngine.open(item)`. Routing flow **solo via Intent** (non da `item.type` grezzo).
- **Flusso UI:** Home tap → Intent → sessione → domande → complete → Home refresh con prossimo passo.
- **Backend:** `backend/action_engine/`.
- **DB:** `action_sessions`, `action_projects` (+ life_nodes, reminders, decisions, knowledge).
- **Docs:** `docs/ACTION_ENGINE_*.md`.
- **Aperti:** smoke collaborativo device/web; weather bloccato senza credenziali; medical = solo logistica.

### 2c. Study Action Flow (end-to-end)

- **Scopo:** da priorità studio/esame a piano confermato con sessioni, materiali, flashcard/Interrogami e sync calendario.
- **Stato:** **implementato** — step conversazionali, preview/confirm obbligatorio, piani `study_plans`/`study_sessions`.
- **API:** `/api/action-engine/sessions/{id}/…` (answer/back/draft/search-docs/preview/modify/confirm) + `/api/study-plans/*`.
- **UI:** `/action/[sessionId]` (multi-chip/preview) + `/study-plan/[id]`; Home mostra piano attivo e ripresa bozza.
- **Docs:** `docs/STUDY_ACTION_FLOW_*.md`, `STUDY_PLAN_GENERATION.md`.
- **Limiti:** Google sync solo se collegato; Gemini topic-split opzionale; mobile native non verificato.

### 2d. Travel Action Flow (Life Planner slice)

- **Scopo:** da «vado in vacanza…» a **Travel Project** vivo (periodo, destinazione, trasporto, prenotazioni, Maps, calendario proposto) — non checklist.
- **Stato:** **implementato** — missing-only questions, preview/confirm, Home phases (countdown → partenza → durante → bentornato).
- **API:** Action Engine + `/api/travel-projects/*`.
- **UI:** `/action/[sessionId]` (preview viaggio) + `/travel-project/[id]`.
- **Docs:** `docs/TRAVEL_ACTION_FLOW_*.md`.
- **Limiti:** meteo/email auto-find non implementati (onesti); Google eventi solo dopo conferma; mobile native non verificato.

### 2e. Goal Engine + Goal-aware Home (no Goal UX)

- **Scopo:** identità e lifecycle dell’*outcome* utente (“Preparare esame X”, “Vacanza Y”) tra Intent e Home — senza sostituire Study/Travel.
- **Stato:** **backend shadow** + **Home context** — conferma Study/Travel crea/aggiorna Goal; Home allega `goal_*`, dedupe stesso `goal_id`, fattori ranking/insights/resume. **Nessuna UI Goal**, nessun tab, nessuna sezione Goals su Home.
- **API:** `/api/goals/*` (protetta; non c’è schermata Goals). Home arricchita via `GET /api/home`.
- **Flag:** `GOAL_ENGINE_ENABLED` (default ON; OFF → Home come prima + shadow no-op).
- **Docs:** `docs/GOAL_AWARE_HOME.md` (alias `HOME_GOAL_AWARE.md`), `GOAL_ENGINE_FOUNDATION.md`, `GOAL_DATA_MODEL.md`, `GOAL_LIFECYCLE.md`.
- **Aperti:** refresh progress su session complete; eventuale UI Goals in fasi successive (non su Home come modulo).

### 3. Decision Engine

- **Scopo:** ranking e azioni su decisioni (start/complete/postpone/block/dismiss/partial/resolve); alimenta anche Home V2 via adapter.
- **Stato:** **parzialmente operativo** — API OK; Home non dipende più solo da questo.
- **Backend:** `/api/decisions/*`, `decision_engine/`, action center, explainability.
- **DB:** `decisions`, `decision_action_history`, (legacy `tasks`).

### 3b. Daily Intelligence

- **Scopo:** indicatori giornata (eventi, finestre) usati da “La tua situazione”.
- **Stato:** **operativo** API; Home non mostra più score 100/100.
- **Backend:** `/api/daily/*`, `daily_intelligence/`.

### 4. Memoria (Life Memory V1 + Governed Learning V2.8.3)

- **Scopo:** mostrare i fatti duraturi che ORA ha imparato (Life Profile, soggetto di studio, appunti utente).
- **Stato:** browse Quiet Premium su `GET /api/life-memory` **operativo** (deterministico); Gemini wording opzionale (`MEMORY_GEMINI=0`). Il brain `/ora` può proporre apprendimento durevole, ma una governance deterministica decide `PROMOTE`, `CLARIFY`, `REJECT`, `SUPERSEDE` o oblio controllato prima di qualsiasi claim. Legacy ask/add restano su `/api/memory*`.
- **Stato UI:** read-only V1; Correct/Forget/Confirm non finti (API Life Profile esistono ma non wireate in Memoria).
- **Backend:** `life_memory/` + legacy `routers/memory.py`.
- **DB:** fonti `life_profiles`, `study_plans`, `memories`; i record governed sono user-scoped, versionati, con provenance e history; cache `life_memory_snapshots` (derived only).
- **Contratto:** Situation temporanea ≠ Memory; inferenza ≠ fatto; preferenza = evidence utile, non regola deterministica. Correzioni supersedono senza cancellare history; Forget usa tombstone logico e ownership.
- **Continuità:** Stage A segnala soltanto che esiste evidence durevole; Stage B recupera il dettaglio bounded quando l'AI lo richiede. I claim di memoria salvata/corretta/dimenticata sono consentiti soltanto dopo una mutation realmente persistita.

### 5. Documenti

- **Scopo:** acquisire, comprendere e trasformare i file in conoscenza/azioni (eventi, studio, scadenze), non solo archiviarli.
- **Stato (V2):** hub azioni intelligenti (non archivio); dettaglio dinamico per macro; flashcard + Interrogami; admin edit/scadenze; pipeline `intel-docs-2.0`; conferma eventi + sync Google; auto-add **opt-in** (confidence > 0.90); Brain merge; search intelligente; provenance correzioni; verificato API + browser web (non mobile).
- **Backend:** `/api/documents/*` + analyze/events/ask; `documents/intelligence/`.
- **DB:** `documents` (+ analysis fields), `calendar_event_drafts`, Life Graph / Knowledge.
- **Docs:** `docs/INTELLIGENT_DOCUMENTS_*.md`.

### 6. Calendario Google

- **Scopo:** OAuth + sync eventi → decisioni/daily.
- **Stato:** codice **presente**; locale **bloccato da credenziali** (`GOOGLE_OAUTH_*`); UI CTA e settings gestiscono assenza account.
- **Backend:** `/api/connectors/google-calendar/*`.
- **DB:** `connector_instances`, `google_oauth_sessions`, `secret_vault`, `ingestion_events`.

### 7. Calendario Apple

- **Scopo:** EventKit → sync eventi (iOS).
- **Stato:** backend config `enabled:false` in locale; FE mock opzionale (`EXPO_PUBLIC_APPLE_CALENDAR_MOCK`); **non verificato su device**.
- **Backend:** `/api/connectors/apple-calendar/*`.

### 8. Life Graph / Knowledge / Auto-Link

- **Scopo:** grafo vita, fatti, proposta link decision↔nodo.
- **Stato:** API **operative** (nodes/registry verificati); **poca/nessuna UI** dedicata (servizi dietro memoria/documenti/decision).
- **DB:** `life_nodes`, `life_edges`, `node_knowledge`, `link_proposals`.

### 9. Permissions & Connectors framework

- **Scopo:** consensi capability, registry connettori, audit.
- **Stato:** API registry **operative**; UI limitata a calendari in Settings.
- **DB:** `permission_*`, `connector_instances`.

### 10. Behavioral Intelligence / Shadow

- **Scopo:** osservazione comportamento; ranking shadow opzionale.
- **Stato:** API profile **risponde**; middleware osservazionale attivo; **nessuna UI** prodotto; shadow mode off.

### 11. Context Assembler / Ingestion

- **Scopo:** snapshot contesto decisioni; pipeline eventi connettori.
- **Stato:** backend **implementato**; UI non diretta; dipende da connettori.

### 12. Notifiche / Email / Push / Promemoria dedicati

- **Stato:** **non implementati** come prodotto (solo placeholder “Email & Messaggi” in Profilo). Postpone decisioni ≠ sistema notifiche.

### 13. Progetti

- **Stato:** **non implementato** come modulo UI/API dedicato (non confondere con life graph).

### 14. Impostazioni & Profilo

- **Profilo:** operativo per email/logout; molte righe “In arrivo”.
- **Settings:** operativo per stato “nessun account collegato”.

## Flussi principali verificati

1. Register email → seed 5 decisioni → Home con focus reale.
2. Login / me / logout / re-login.
3. Memoria add/list; ask senza LLM → errore esplicito.
4. Documenti empty state.
5. Google Calendar non configurato → 503/config-status false, UI invita a collegare.
6. Sessione web persistita via storage token.

## Fuori scope attuale

Chatbot generico, Gmail, push, analytics produzione, multi-tenant admin UI, deploy store.
# V2.8.4 — Unified uncertainty and clarification

ORA treats uncertainty as AI-owned decision state, not as a form or domain flow. Missing
information does not imply a question: the production AI Core can retrieve bounded personal
evidence, ask one necessary question, proceed with an explicit reversible assumption, defer,
or answer/act when residual uncertainty is immaterial. Assumptions are neither facts nor Life
Memory; consequential actions remain blocked when essential information is unresolved.

# V2.8.5 — Life Context Graph

ORA can now remember that two things in your life are related, not just what each of them is.
"This goal depends on that plan", "this memory is backed by that document", "this situation
is scheduled for that calendar item" — ORA proposes the relationship, in its own words, and
the system keeps it honestly: with a source, a confidence, and a full history if it later
turns out wrong. It is never a form to fill in and never a fixed list of relationship types —
the same mechanism works for a house purchase, a small hobby, or anything a developer never
anticipated. When two relationships would conflict, ORA is asked to resolve the conflict
explicitly rather than the system silently picking a winner or silently keeping both. This
never replaces Life Memory or the current-situation tracker — it only connects the things ORA
already knows to each other, across sessions, without you needing to re-explain "that thing
we talked about."

# V2.8.6b — AI-native Calendar Intelligence

ORA can now see your calendar and act on it — but it is a capability ORA reaches for when it
matters, not a new assistant bolted onto the side. When you say "domani alle 18 devo chiamare
Luca", ORA decides whether that belongs on your calendar, stays a passing note, or is really
about the plan you're already tracking — the same judgment it already applies everywhere else,
never a fixed rule like "any sentence with a time in it is an event." A vague "ricordami di
chiamare la banca" with no real time attached usually isn't calendar-worthy on its own; ORA
would rather ask or keep it conversational than invent a time for you.

ORA never puts anything on your calendar, moves anything, or cancels anything without asking
first and getting your confirmation on your next message — every write is a proposal until you
say yes. If you correct yourself ("anzi il notaio è alle 10"), ORA updates the same appointment
rather than creating a second one next to it. If two things on your calendar would overlap, ORA
can notice and mention it — it never blocks you or forces a choice by itself. And ORA is honest
about what it actually did: if a calendar connection isn't set up, or a sync to Google fails, it
tells you plainly instead of claiming something happened that didn't.
