# ORA — Product (struttura reale)

Ultimo aggiornamento: 2026-08-05 — AI Provider Manager (Gemini default).

## Vision

ORA è il sistema operativo della vita quotidiana: riduce il carico cognitivo mostrando **cosa fare adesso**, con decisioni ordinate, memoria personale e documenti.

## Utenti

Persone che vogliono una priorità unica chiara (non un task manager generico), con calendario, documenti e memoria collegati.

## Navigazione frontend (expo-router)

| Route | Schermata | Ruolo |
|-------|-----------|--------|
| `/login` | Login | Auth email/Google/Apple |
| `/(tabs)` → index | Home “Adesso” | Decision focus + daily + calendario CTA |
| `/(tabs)/memoria` | Memoria | Q&A e salvataggio ricordi |
| `/(tabs)/documenti` | Documenti | Lista/upload/dettaglio documenti |
| `/(tabs)/aggiungi` | Aggiungi | Capture priorità / ricordo |
| `/(tabs)/profilo` | Profilo | Account, placeholder moduli, logout |
| `/settings` | Impostazioni | AI Provider + account/calendari |
| `/manage-calendars` | Gestione calendari | Selezione calendari Google |
| `/connect-apple-calendar` | Apple Calendar | Flusso nativo iOS |
| `/how-it-works` | Onboarding informativo | Spiega Google Calendar |
| `/document/[id]` | Dettaglio documento | Insights + azioni |

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

### 2. Decision Engine / “Cosa conta adesso”

- **Scopo:** ranking e azioni su decisioni (start/complete/postpone/block/dismiss/partial/resolve).
- **Stato:** **parzialmente operativo** — lista, seed al register, azioni e explanation OK; **resolve** bloccato senza LLM.
- **Flusso UI:** Home mostra focus + later; sheet azioni; “Risolvi” richiede provider LLM.
- **Backend:** `/api/decisions/*`, `decision_engine/`, action center, explainability.
- **DB:** `decisions`, `decision_action_history`, (legacy `tasks`).
- **Aperti:** UX resolve senza LLM; progetti/task manager non esistono come modulo separato.

### 3. Daily Intelligence

- **Scopo:** riassunto giornata (eventi, finestre, energia).
- **Stato:** **operativo** a livello API/UI (verificato: card “La tua giornata” con 0 eventi senza calendario).
- **Backend:** `/api/daily/*`, `daily_intelligence/`.
- **DB:** deriva da ingestion/life graph/calendar events.
- **Dipendenze:** ricchezza dati aumenta con Google/Apple Calendar.

### 4. Memoria

- **Scopo:** salvare ricordi e interrogare in linguaggio naturale.
- **Stato:** add/list **operativi**; ask **bloccato da LLM** (503 chiaro).
- **Backend:** `/api/memory`, `/api/memory/ask` + wiring life_graph/knowledge.
- **DB:** `memories`, nodi `life_nodes`, `node_knowledge`.

### 5. Documenti

- **Scopo:** acquisire, comprendere e trasformare i file in conoscenza/azioni (eventi, studio, scadenze), non solo archiviarli.
- **Stato:** upload/lista/dettaglio operativi; pipeline intelligente locale + LLM opzionale; event candidate con conferma; calendario interno draft; Google Calendar write **non** incluso.
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
