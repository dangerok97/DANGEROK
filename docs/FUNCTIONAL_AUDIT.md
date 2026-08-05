# ORA — Functional Audit

Data: 2026-08-04  
Ambiente: locale Windows, MongoDB, uvicorn `:8000`, Expo web `:8081`  
Branch: `ora/cursor-platform`

## Legenda stati

| Stato | Significato |
|-------|-------------|
| operativo | Eseguito/verificato end-to-end in questo audit |
| parzialmente operativo | Parte del flusso funziona; manca pezzo critico |
| soltanto UI | Visibile, nessuna azione utile o disabilitato |
| mock | Dati/finti path di sviluppo |
| non collegato | Codice FE/BE non cablato insieme |
| non implementato | Assente come funzione prodotto |
| bloccato da credenziali | Codice pronto, manca config esterna |
| obsoleto | Legacy mantenuto ma non primario |
| non utilizzato | Presente ma non esposto in UI |

## Inventario schermate / route

| Elemento | Stato | Note verifica |
|----------|-------|---------------|
| `/login` | parzialmente operativo | Email OK; Google/Apple codice pronto, UI “non configurata” senza client ID (non mock) |
| Home `/(tabs)` | operativo (web Home V2) | Aggregato `/api/home`; Adesso/Perché/azioni tipizzate → Action Engine; situazione/priorità/insights/resume; banner Google compatto |
| `/action/[sessionId]` | operativo (web study) | Guida una-domanda; study: multi-chip/preview/confirm |
| `/action/open` | implementato | Bridge deep-link verso Action Engine |
| `/study-plan/[id]` | implementato (web) | Piano attivo: sessioni, pause, sync, delete |
| `/situazione` | operativo (web) | Vista completa reale da CTA Home |
| Memoria | parzialmente operativo | UI + add/list OK; ask serve LLM |
| Documenti | operativo (web) | Empty + upload/list/detail/persistenza verificati 2026-08-04; vedi `docs/DOCUMENTS_VERIFICATION.md` |
| Aggiungi | parzialmente operativo | Priorità/Ricordo/Documento attivi; Foto “In arrivo” |
| Profilo | parzialmente operativo | Documenti attivo; spese/obiettivi/email/banche “In arrivo” |
| Settings | operativo | “Nessun account collegato” corretto |
| manage-calendars | bloccato da credenziali | Dipende da Google OAuth |
| connect-apple-calendar | non verificato / mock | Web non nativo; mock flag esiste |
| how-it-works | operativo | Contenuto statico verificato |
| document/[id] | operativo (API+route) | Dettaglio via HTTP + navigazione post-upload; UI web non cliccata su ogni tab insights |

## Matrice funzionale

| Modulo | Funzione | Frontend | Backend | Database | Test | Stato | Blocchi | Priorità | Prossimo intervento |
|--------|----------|----------|---------|----------|------|-------|---------|----------|---------------------|
| Auth | Register | login.tsx | POST /auth/register | users | HTTP+smoke | operativo | — | critica | — |
| Auth | Login | login.tsx | POST /auth/login | users | HTTP+smoke | operativo | — | critica | — |
| Auth | Logout | profilo | POST /auth/logout | — | HTTP | operativo | logout server non invalida JWT | alta | blacklist/TTL docs |
| Auth | Me / sessione | AuthContext | GET /auth/me | users | HTTP+UI | operativo | storage web AsyncStorage | critica | — |
| Auth | Validazione credenziali | login form | 401/409 | users | HTTP | operativo | — | alta | — |
| Auth | Google login | login + authGoogle | /auth/google | users+identities | mock+HTTP | bloccato da credenziali | manca GOOGLE_*_CLIENT_ID | critica | setup console |
| Auth | Apple login | login + authApple | /auth/apple | users+identities | mock | bloccato da credenziali | manca Apple keys/Services ID | critica | setup Apple |
| Auth | Identities / link | settings | /auth/identities|link | user_identities | HTTP email | operativo (email path) | social link senza credenziali | alta | — |
| Decisions | Top / seed | Home | /decisions/top | decisions | HTTP+UI | operativo | — | critica | — |
| Decisions | Azioni (start/…) | sheets | /decisions/{id}/* | decisions, history | HTTP start/history | operativo | non tutte le azioni cliccate in UI | alta | E2E UI azioni |
| Decisions | Explanation | Perché adesso | /explanation | — | HTTP 200 | operativo | — | media | — |
| Decisions | Resolve AI | Risolvi | /resolve | — | HTTP 503 | bloccato da credenziali | LLM | alta | adapter + chiave o UX offline |
| Daily | Today summary | DailySummaryCard | /daily/today | derived | HTTP+UI | operativo | vuoto senza calendario | media | — |
| Memory | Add/list | Aggiungi/Memoria | /memory | memories | HTTP | operativo | — | alta | — |
| Memory | Ask AI | Memoria | /memory/ask | memories+KL | HTTP 503 | bloccato da credenziali | LLM | alta | provider LLM |
| Documents | List/empty | documenti | /documents | docs | HTTP+UI+pytest | operativo | web only | alta | native smoke |
| Documents | Upload | documenti/aggiungi | /documents/upload | docs+files | pytest+HTTP | operativo (web API) | picker UI non e2e-automatizzato | alta | device test |
| Documents | Isolation/auth | — | get/list/upload | docs | pytest | operativo | — | critica | — |
| Documents | Insights/actions | document/[id] | /insights + FE actions | docs | HTTP detail OK | parzialmente operativo | azioni UI non tutte cliccate | media | C3 roadmap |
| Documents | Intel pipeline | document/[id] | analyze/events/ask | intel | pytest+HTTP+OCR | operativo locale+OCR | OpenAI reale bloccato; picker no | critica | chiave OpenAI + UI pass |
| Documents | OCR | upload image/PDF | extraction | files | real Tesseract | operativo (host) | qualità OCR variabile | alta | — |
| Documents V2 | Hub + dynamic utility + study/quiz/admin | documenti / document/[id] + DocumentUtilityPanel | documents + drafts + brain + study/quiz | hub/prefs/pipeline/study/quiz/admin V2 | pytest V2 15p + Playwright Chromium E2E + prior Google sync | **web verified** (flashcards, Interrogami, dynamic detail) | mobile / Gemini live non ri-verificati | alta | device smoke |
| Google Calendar | OAuth read+write | Home/Settings + doc confirm | connectors/google-calendar + documents/calendar | connectors, vault, drafts | fake suite + config-status | write implementato; reale bloccato da credenziali | GOOGLE_OAUTH_* | alta | setup OAuth + verify event |
| Apple Calendar | Connect/sync | settings iOS | apple-calendar | connectors | config enabled:false | mock / non verificato | device + flag | media | EAS/device |
| Life Graph | CRUD nodes | — | /life-graph | life_* | HTTP nodes | non utilizzato | no UI | media | decidere se esporre |
| Knowledge | Facts | dietro memoria | /knowledge | node_knowledge | codice | non utilizzato | no UI | media | — |
| Auto-Link | Proposals | — | /auto-link | link_proposals | codice/test | non utilizzato | no UI | bassa | — |
| Permissions | Registry/consents | — | /permissions | permission_* | HTTP registry | non utilizzato | UI minima | media | UI consensi |
| Behavior | Profile/metrics | — | /behavior | behavioral cols | HTTP profile | non utilizzato | no UI | bassa | — |
| Context/Ingestion | Assemble/events | — | /context /ingestion | snapshots, events | codice | non utilizzato | dipende connettori | media | — |
| Legacy tasks | /tasks /priorities | client API | legacy_tasks | tasks | codice | obsoleto | sostituito da decisions | bassa | deprecare FE client |
| Notifiche push | — | — | — | — | — | non implementato | — | media | design poi implementare |
| Email/Gmail | Profilo placeholder | — | — | — | UI | soltanto UI | — | media | — |
| Promemoria | — | postpone decisioni | — | — | parziale | non un modulo reminder | — | media | modello reminder |
| Progetti | — | — | — | — | — | non implementato | — | media | definire scope |
| Admin demo | — | — | /admin/demo/refresh | — | codice | non utilizzato | — | bassa | — |

## API backend (sintesi copertura)

- Auth, decisions, daily, memory, documents list, permissions registry, connectors registry, life-graph nodes, behavior profile, google/apple config-status: **chiamate reali OK**.
- Resolve / memory ask: **503 senza LLM** (comportamento corretto).
- Google OAuth start: **503 senza credenziali** (corretto).

## Collezioni Mongo rilevanti

`users`, `tasks` (legacy), `decisions`, `life_nodes`, `life_edges`, `node_knowledge`, `link_proposals`, `context_snapshots`, `memories`, `permission_*`, `ingestion_events`, `connector_instances`, `secret_vault`, `google_oauth_sessions`, `data_revocation_plans`, `decision_action_history`, + collezioni documents/behavioral (ensure_ready).

## Problemi UI osservati

1. ~~Profilo “Documenti — In arrivo”~~ → corretto (attivo, “File caricati e archivio”).
2. ~~Aggiungi “Documento — In arrivo”~~ → corretto (“Carica un file”); Foto resta “In arrivo”.
3. Google/Apple login non operativi in locale (messaggi onesti).
4. Home CTA “Continua con Google” per calendar: richiede OAuth non configurato.
5. RN-web accessibility tree povero (testID poco esposti agli screen reader).
6. Dark UI: screenshot neri se contenuto non ancora montato (false alarm).

## Aggiornamento 2026-08-04 — Documenti (post BACKLOG-001/002)

Vedi `docs/DOCUMENTS_VERIFICATION.md`. Label allineate; upload/list/detail/isolamento/persistenza verificati via pytest + HTTP; UI web empty/labels verificati in browser. Native non verificato. Storage locale only.

## Aggiornamento 2026-08-05 — Documenti intelligenti (verifica reale)

Vedi `docs/INTELLIGENT_DOCUMENTS_VERIFICATION.md`. Casi A–F sintetici + OCR reale + DOCX/PPTX extract + calendario interno idempotente verificati. OpenAI reale **non** eseguito (chiave assente). File picker UI e mobile non verificati. Google Calendar da documenti non avviato.

## Conteggi (questo audit)

Vedi output finale in chat: moduli analizzati, operative / parziali / UI-mock / bloccate credenziali.
