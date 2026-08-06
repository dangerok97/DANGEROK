# ORA — Capability Matrix

**Audit tip:** `feature/life-object-engine`  
**Data:** 2026-08-06  
**Legenda stato:** `NON ESISTE` | `ARCHITETTURA` | `PROTOTIPO` | `PARZIALE` | `FUNZIONANTE` | `VERIFICATO` | `PRODUZIONE`  
**Livello verifica:** unit | API | browser (Playwright/Expo web) | real smoke (provider/device) | never

> **PRODUZIONE** non assegnato: nessun evidence di ops production-ready.  
> **Mobile nativo:** ovunque = **never** (non verificato).

| Modulo | Stato | Verifica | Note oneste |
|--------|-------|----------|-------------|
| Life Object Engine | FUNZIONANTE | unit+API (+Playwright API) | **SHADOW — verità canonica user**; Home V3 UI OFF; dedupe address/plate; Gemini fallback; altri motori restano e R/W oggetti |
| Home V3 Life Objects UI | ARCHITETTURA | never | Flag `LIFE_OBJECT_HOME_UI_ENABLED=0`; Home resta Goal-aware |
| Authentication (email/password) | VERIFICATO | unit+API+browser | Register/login/me; logout non invalida JWT |
| Google Login | PARZIALE | unit only | Codice+JWKS; reale bloccato da `GOOGLE_WEB_CLIENT_ID` |
| Apple Login | PROTOTIPO | unit only | Placeholder UI senza keys; iOS non verificato |
| Conversation Engine | VERIFICATO | unit+API+browser | Orchestrator non-chatbot; stub email/WA/banking |
| Intent Engine | VERIFICATO | unit+API+browser | Corpus IT 124+; psychology Playwright |
| Semantic Engine | VERIFICATO | unit+API+browser | Gap analyzer; Gemini opzionale |
| AI Life Strategist | VERIFICATO | unit+API+browser | Reasoning loop + fallback IT; Gemini live per conversazione NON VERIFICATO in questo audit (Gemini per Document Understanding sì, vedi riga sotto) |
| Life Setup / Life Experience | VERIFICATO | unit+API+browser+Gemini reale (documenti) | Anti-wizard; upload V2 + AI Document Understanding v2 (contesto vita, azioni AI, memory Brain/Knowledge, versioni harden). Gemini reale storico: rogito/bolletta/libretto/piano; tipi nuovi = fixture+fallback, smoke live **opzionale** |
| AI Document Reasoner | FUNZIONANTE | unit (+optional Gemini) | Post-OCR; Pydantic; fallback onesto; CI senza secret |
| Goal Engine | VERIFICATO | unit+API+browser | Shadow + Home context; **no Goal UX** |
| Action Engine (generic) | VERIFICATO | unit+API+browser | Guided flows |
| Study Action Flow | VERIFICATO | unit+API+browser+real Google | Plan/sessions/Home; mobile never |
| Travel Action Flow | VERIFICATO | unit+API+browser+real Google | Maps deep-link+Nominatim best-effort |
| Documents V2 | VERIFICATO | unit+API+browser (+Gemini/Google prior) | Flashcards/Interrogami web; mobile never |
| Document Intelligence | VERIFICATO | unit+API+browser+OCR | OpenAI live spesso skip; pipeline locale |
| Flashcard | VERIFICATO | unit+API+browser | Via Documents V2 study tools |
| Interrogami | VERIFICATO | unit+API+browser | Quiz su documento studio |
| Knowledge Graph | FUNZIONANTE | unit+API | API knowledge; UI dedicata assente |
| Brain | PARZIALE | unit/API soft | Merge/link da AE/CE/Home; UI Brain assente |
| Life Graph | FUNZIONANTE | unit+API | CRUD nodes/edges; poca/nessuna UI |
| Home V2 | VERIFICATO | unit+API+browser | Ranking 1.2 goal-aware + ORA TI CONSIGLIA |
| Proactive Engine | VERIFICATO | unit+API+browser | Real gens study/travel/calendar/docs; stubs empty |
| Google Calendar | VERIFICATO | unit+fake+real create/update | Delete/disconnect checklist incompleta |
| Apple Calendar | PROTOTIPO | unit/config | Web mock; iOS device never |
| Maps | PARZIALE | unit+API (+travel browser) | Deep link Google Maps; geocode soft-fail |
| Notifications (push) | NON ESISTE | never | Policy meta only; no expo-notifications |
| Email | ARCHITETTURA | unit (stub honesty) | Stub predisposto; UI «In arrivo» |
| WhatsApp | ARCHITETTURA | unit (stub honesty) | Stub CE/Life Setup; mai simulato |
| Finance / Open Banking | ARCHITETTURA | unit (stub honesty) | Stub; Profilo spese/banche «In arrivo» |
| Voice / STT | PROTOTIPO | browser stub UX | Mic → hint digita; nessun STT |
| Memory | PARZIALE | API (+ask LLM-gated) | Add/list OK; ask 503 senza LLM |
| Search (documents intelligent) | VERIFICATO | unit+API+browser | `/documents/search/intelligent` |
| Projects (generici) | PARZIALE | unit/API | `action_projects` / travel/study; no Projects hub UX |
| Settings | FUNZIONANTE | API+browser partial | Calendari/identities; social link gated |
| Weather / Health | ARCHITETTURA | unit (stub empty) | Proactive stub generators always `[]` |
| Decisions / Decision Engine | FUNZIONANTE | unit+API+browser partial | Core ranking; resolve AI LLM-gated |
| Daily Intelligence | FUNZIONANTE | unit+API | Summary; vuoto senza calendario |
| Permissions / Consents | FUNZIONANTE | unit+API | Registry; UI consensi minima |
| Behavioral Intelligence | FUNZIONANTE | unit+API | Observational; no primary UX |
| Auto-Link | FUNZIONANTE | unit+API | Proposals; no UI primaria |
| Context Assembler / Ingestion | FUNZIONANTE | unit+API | Dietro connettori |
| LLM Provider Manager | FUNZIONANTE | unit (+optional Gemini) | Failover Gemini→OpenAI→Ollama→Emergent |
| Mobile (iOS/Android native) | NON VERIFICATO* | never | *non è uno stato enum prodotto; evidenza: **never** su device |

\*Mobile non è un modulo prodotto separato nell’enum: per ogni feature UI sopra, verifica mobile = **never**.
