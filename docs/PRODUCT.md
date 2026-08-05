# ORA — Product (struttura reale)

Ultimo aggiornamento: 2026-08-05 — Action Engine + Home V2.

## Vision

ORA è il sistema operativo della vita quotidiana: riduce il carico cognitivo mostrando **cosa fare adesso**, con decisioni ordinate, memoria personale e documenti.

## Utenti

Persone che vogliono una priorità unica chiara (non un task manager generico), con calendario, documenti e memoria collegati.

## Navigazione frontend (expo-router)

| Route | Schermata | Ruolo |
|-------|-----------|--------|
| `/login` | Login | Auth email/Google/Apple |
| `/(tabs)` → index | Home V2 “Adesso” | Ranking multi-fonte, situazione, priorità, insights, resume |
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
| `/action/open` | Bridge apertura guida | Da Home Apri/Organizza/Inizia |

## Moduli prodotto

### 1. Autenticazione

- **Scopo:** una sola identità ORA (JWT) per email, Google e Apple.
- **Stato:** email **operativa**; Google/Apple **implementati** (verifica ID token backend + identity store); **verifica reale provider bloccata da credenziali**.
- **Flusso:** FE ottiene ID token → backend verifica JWKS → `user_identities` → JWT ORA.
- **Backend:** `/api/auth/register|login|google|apple|link/*|identities|providers|me|logout`.
- **DB:** `users` + `user_identities`.
- **Esterni:** Google Cloud OAuth clients; Apple Sign In (App ID / Services ID / key). Legacy Emergent opzionale.
- **Docs:** `docs/SOCIAL_AUTH_*.md`.
- **Aperti:** credenziali reali; device iOS/Android; revoca JWT server-side.

### 2. Home V2 — Intelligence dashboard

- **Scopo:** rispondere “cosa è più utile sapere o fare adesso” con ranking multi-fonte (documenti, calendario, studio, decisioni, …).
- **Stato:** **operativo (web)** — `GET /api/home`, ranking `home-rank-1.0` senza Gemini, UI Adesso/Perché/azioni tipizzate/situazione/priorità/insights/resume; banner Google compatto.
- **Flusso UI:** Home → focus → **Action Engine** (Apri/Organizza/Inizia/card); complete/snooze/ignore/correct; refresh on focus + pull-to-refresh.
- **Backend:** `backend/home/` + adapters fail-soft (+ Action Engine adapter).
- **DB:** `home_snapshots`, `home_item_state`, `home_insights` (+ fonti esistenti).
- **Docs:** `docs/HOME_V2_*.md`.
- **Aperti:** native mobile non verificato.

### 2b. Action Engine — Guided priority flows

- **Scopo:** trasformare una priorità Home in una breve conversazione a chip (una domanda per schermo) che crea calendario, promemoria, progetto e aggiorna Brain — mai una pagina vuota.
- **Stato:** **implementato** — API `/api/action-engine/*`, flussi study/event/travel/medical/admin/generic; FE `ActionEngine.open(item)`.
- **Flusso UI:** Home tap → sessione → domande → complete → Home refresh con prossimo passo.
- **Backend:** `backend/action_engine/`.
- **DB:** `action_sessions`, `action_projects` (+ life_nodes, reminders, decisions, knowledge).
- **Docs:** `docs/ACTION_ENGINE_*.md`.
- **Aperti:** smoke collaborativo device/web; weather bloccato senza credenziali; medical = solo logistica.

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
