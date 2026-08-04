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
| `/login` | parzialmente operativo | Email OK; Google messaggio non-config; Apple “in arrivo” |
| Home `/(tabs)` | operativo | Decisioni seed, daily, CTA Google, azioni UI presenti |
| Memoria | parzialmente operativo | UI + add/list OK; ask serve LLM |
| Documenti | parzialmente operativo | Empty state OK; API list OK; upload non rieseguito qui |
| Aggiungi | parzialmente operativo | Priorità/Ricordo; Foto/Documento “In arrivo” |
| Profilo | parzialmente operativo | Nome/email/logout OK; moduli futuri disabilitati |
| Settings | operativo | “Nessun account collegato” corretto |
| manage-calendars | bloccato da credenziali | Dipende da Google OAuth |
| connect-apple-calendar | non verificato / mock | Web non nativo; mock flag esiste |
| how-it-works | operativo | Contenuto statico verificato |
| document/[id] | non verificato UI | Route presente; non aperta (nessun doc) |

## Matrice funzionale

| Modulo | Funzione | Frontend | Backend | Database | Test | Stato | Blocchi | Priorità | Prossimo intervento |
|--------|----------|----------|---------|----------|------|-------|---------|----------|---------------------|
| Auth | Register | login.tsx | POST /auth/register | users | HTTP+smoke | operativo | — | critica | — |
| Auth | Login | login.tsx | POST /auth/login | users | HTTP+smoke | operativo | — | critica | — |
| Auth | Logout | profilo | POST /auth/logout | — | HTTP | operativo | logout server non invalida JWT | alta | blacklist/TTL docs |
| Auth | Me / sessione | AuthContext | GET /auth/me | users | HTTP+UI | operativo | storage web AsyncStorage | critica | — |
| Auth | Validazione credenziali | login form | 401/409 | users | HTTP | operativo | — | alta | — |
| Auth | Google login | login button | google-session | users | HTTP 503 | bloccato da credenziali | Emergent off | media | OAuth first-party |
| Auth | Apple login | button | — | — | UI | soltanto UI | non implementato | bassa | Sign in with Apple |
| Decisions | Top / seed | Home | /decisions/top | decisions | HTTP+UI | operativo | — | critica | — |
| Decisions | Azioni (start/…) | sheets | /decisions/{id}/* | decisions, history | HTTP start/history | operativo | non tutte le azioni cliccate in UI | alta | E2E UI azioni |
| Decisions | Explanation | Perché adesso | /explanation | — | HTTP 200 | operativo | — | media | — |
| Decisions | Resolve AI | Risolvi | /resolve | — | HTTP 503 | bloccato da credenziali | LLM | alta | adapter + chiave o UX offline |
| Daily | Today summary | DailySummaryCard | /daily/today | derived | HTTP+UI | operativo | vuoto senza calendario | media | — |
| Memory | Add/list | Aggiungi/Memoria | /memory | memories | HTTP | operativo | — | alta | — |
| Memory | Ask AI | Memoria | /memory/ask | memories+KL | HTTP 503 | bloccato da credenziali | LLM | alta | provider LLM |
| Documents | List/empty | documenti | /documents | docs | HTTP+UI | operativo | — | alta | — |
| Documents | Upload | documenti/aggiungi | /documents/upload | docs+files | codice | parzialmente operativo | upload non rieseguito in audit | alta | test upload web |
| Documents | Insights/actions | document/[id] | /insights + FE actions | docs | codice/test iter | parzialmente operativo | UI dettaglio non aperta | media | aprire con file reale |
| Google Calendar | OAuth/sync | Home/Settings | connectors/google-calendar | connectors, vault | config-status | bloccato da credenziali | GOOGLE_OAUTH_* | alta | setup OAuth locale |
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

1. Profilo elenca “Documenti — In arrivo” ma tab Documenti è attivo.
2. Aggiungi: “Foto/Documento — In arrivo” mentre Documenti ha “Carica”.
3. Google/Apple login non operativi in locale (messaggi onesti).
4. Home CTA “Continua con Google” per calendar: richiede OAuth non configurato.
5. RN-web accessibility tree povero (testID poco esposti agli screen reader).
6. Dark UI: screenshot neri se contenuto non ancora montato (false alarm).

## Conteggi (questo audit)

Vedi output finale in chat: moduli analizzati, operative / parziali / UI-mock / bloccate credenziali.
