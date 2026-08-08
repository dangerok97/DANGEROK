# ORA — Product (struttura reale)

Ultimo aggiornamento: 2026-08-07 — ORA Home Quiet Premium V1.

## Vision

ORA è il sistema operativo della vita quotidiana: riduce il carico cognitivo mostrando **cosa fare adesso**, con decisioni ordinate, memoria personale e documenti.

## Design — ORA Quiet Premium

Linguaggio visivo **calmo, editoriale, premium** (Apple HIG; riferimenti Calendar/Journal/Reminders/Health, Things 3, Notion Mobile, Arc Search, Day One — non Linear). Accent **Deep Indigo**. Temi Light / Dark / System. Primitive UI in `frontend/src/components/ui/`. Glass solo su tab bar / sheet / controlli floating.

### Home Quiet Premium V1 (+ polish 2.1)

La Home risponde a **“Cosa conta per me in questo momento?”** — non è dashboard, widget wall o chat. Gerarchia: Ambient Header → Daily Focus (superficie + Focus Glow sentito) → Ask Bar (Apple Search) → Focus Horizon (sezioni temporali) → Priorità tipografiche → Aggiornamenti → Situazione → Continua. CTA a tre livelli. Stessi dati `HomeV2Response` / stessi flussi Action Engine e Conversation Engine; solo presentazione.

I **Life Objects** (Casa, Auto, Università, Lavoro, …) sono il **modello vivente della realtà dell’utente**. L’AI (Gemini) è **consultant**; il backend è **autorità** su tipo, titolo, merge e campi (Semantic Validator prima del persist). Conversation, Goal, Documents, Brain, Proactive e Home **continuano a esistere** come satelliti. Aggiornamenti **shadow**; Home resta Goal-aware; Home V3 oggetti solo predisposta (`LIFE_OBJECT_HOME_UI_ENABLED=0`).

## Utenti

Persone che vogliono una priorità unica chiara (non un task manager generico), con calendario, documenti e memoria collegati.

## Navigazione frontend (expo-router)

| Route | Schermata | Ruolo |
|-------|-----------|--------|
| `/login` | Login | Auth email/Google/Apple; CTA testuale **Nuovo? Crea un account** → registrazione email |
| `/(tabs)` → index | Home Quiet Premium | Daily Focus + Ask Bar + Horizon + priorità/aggiornamenti (stesso ranking API) |
| `/life-setup` | Life Setup Gate (primo avvio) | Sprint 4/4.1/4.2: conversazione Quiet Premium (intro → domanda → thinking in-thread → ack AI o fallback sicuro → sintesi → **Entra in ORA**); copy AI fact-bounded con intent domanda fissato dal planner (`question_goal`); Esci/Più tardi solo su resume (`?resume=1` / `start.resumed`); posizione opzionale per città; MLC Sprint 3; gate Sprint 2B; Home solo dopo complete valido |
| `/conversation` | Entry Conversation Engine | Bridge a guida AE (mai chat thread) |
| `/situazione` | Situazione completa | Vista reale da CTA Home |
| `/(tabs)/memoria` | Memoria | Q&A e salvataggio ricordi |
| `/(tabs)/documenti` | Documenti | Lista/upload/dettaglio documenti |
| `/(tabs)/aggiungi` | Aggiungi | Capture priorità / ricordo |
| `/(tabs)/profilo` | Profilo | Account, placeholder moduli, logout |
| `/settings` | Impostazioni | AI Provider + account/calendari |
| `/manage-calendars` | Gestione calendari | Selezione calendari Google |
| `/connect-apple-calendar` | Apple Calendar | Flusso nativo iOS |
| `/how-it-works` | Onboarding informativo | Spiega Google Calendar |
| `/document/[id]` | Dettaglio documento | Insights + azioni |
| `/action/[sessionId]` | Guida Action Engine | Una domanda per schermo |
| `/study-plan/[id]` | Piano di studio | Progresso, sessioni, flashcard, Interrogami |
| `/action/open` | Bridge apertura guida | Da Home Apri/Organizza/Inizia |

## Moduli prodotto

### 1. Autenticazione

- **Scopo:** una sola identità ORA (JWT) per email, Google e Apple.
- **Stato:** email **operativa**; Google/Apple **implementati** (verifica ID token backend + identity store); **verifica reale provider bloccata da credenziali**.
- **Flusso:** FE ottiene ID token → backend verifica JWKS → `user_identities` → JWT ORA.
- **Backend:** `/api/auth/register|login|google|apple|link/*|identities|providers|me|logout`.
- **DB:** `users` + `user_identities`.
- **Esterni:** Google Cloud OAuth clients; Apple Sign In (App ID / Services ID / key). Legacy Emergent opzionale. In locale, `localhost` e `127.0.0.1` vanno entrambi registrati in Google Console (origin diversi).
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
- **Flusso UI:** PARLA → **Conversation Engine** → guida AE; oppure focus → Action Engine; Proactive Accetta può riprendere una Conversation Session.
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

### 4. Memoria

- **Scopo:** salvare ricordi e interrogare in linguaggio naturale.
- **Stato:** add/list **operativi**; ask **bloccato da LLM** (503 chiaro).
- **Backend:** `/api/memory`, `/api/memory/ask` + wiring life_graph/knowledge.
- **DB:** `memories`, nodi `life_nodes`, `node_knowledge`.

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
