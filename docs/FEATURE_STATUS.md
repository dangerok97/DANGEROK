# ORA — Feature Status (conciso)

**Branch tip:** `feature/life-experience-ai` @ `09404f1` · **2026-08-06**  
Stati: `NON ESISTE` | `ARCHITETTURA` | `PROTOTIPO` | `PARZIALE` | `FUNZIONANTE` | `VERIFICATO` | `PRODUZIONE`

| Feature | Stato | Una riga |
|---------|-------|----------|
| Conversation | VERIFICATO | Orchestrator CE → Intent/Semantic/AE; Playwright travel+study; non chatbot |
| Intent | VERIFICATO | Classificazione IT deterministica; corpus+Playwright psicologia |
| Semantic | VERIFICATO | Extract+gap; domande atomiche; browser gap scenarios |
| AI Life Strategist | VERIFICATO | Reasoning loop + Gemini strutturato + fallback IT; unit+Playwright Life Exp |
| Life Setup / Life Experience | VERIFICATO | First-launch conversazionale; benefit Home/Proactive; stub integrazioni |
| Goal | VERIFICATO | Shadow Study/Travel + Home goal context; **no tab Obiettivi** |
| Action | VERIFICATO | Sessioni guidate open/answer/preview/confirm |
| Study | VERIFICATO | Piano+sessioni+tools+Google sync reale (prior) |
| Travel | VERIFICATO | Travel Project+Maps+Google sync reale (prior) |
| Documents V2 | VERIFICATO | Hub dinamico web; flashcards/Interrogami/search |
| Knowledge Graph | FUNZIONANTE | API `/knowledge`; non esposto come prodotto UI |
| Brain | PARZIALE | Link/merge da flussi; nessuna Brain UI |
| Home | VERIFICATO | Dashboard Adesso/Perché/situazione/consigli; web E2E |
| Proactive | VERIFICATO | ORA TI CONSIGLIA ≤3; stub email/finance/weather/health |
| Google Calendar | VERIFICATO | OAuth+write sync; create/update real; delete checklist open |
| Google Login | PARZIALE | Codice pronto; credenziali web spesso assenti |
| Apple Login | PROTOTIPO | UI + verify path; keys/device mai |
| Maps | PARZIALE | Deep link + stima; non traffic/POI reali |
| Notifications | NON ESISTE | Nessun push; solo policy futura in Proactive |
| Email | ARCHITETTURA | Stub onesto; Profilo «In arrivo» |
| WhatsApp | ARCHITETTURA | Stub onesto; mai messaggi finti |
| Finance | ARCHITETTURA | Open Banking stub; Dashboard spese «In arrivo» |
| Settings | FUNZIONANTE | Accesso, calendari, identities; gated social |
| Authentication | VERIFICATO | Email/password JWT; session web AsyncStorage |
| Memory | PARZIALE | CRUD ricordo; ask AI dipende da LLM |
| Search | VERIFICATO | Search intelligente documenti (web) |
| Projects | PARZIALE | Study/Travel projects reali; hub Progetti assente |
| Document Intelligence | VERIFICATO | Classify/OCR/events/ask (web+API) |
| Flashcard | VERIFICATO | Genera/ripassa da documento studio (web) |
| Interrogami | VERIFICATO | Quiz da documento (web) |
| Voice | PROTOTIPO | Origin `voice` accettato; STT non cablato |

## Non negoziabili di onestà

- PREDISPOSTO ≠ FUNZIONANTE (Email, WhatsApp, Finance, Weather, Health).
- VERIFICATO qui = pytest + Playwright Expo **web** (+ real smoke dove documentato). **Mai** mobile nativo.
- PRODUZIONE = quasi mai; non usata in questa tabella.
