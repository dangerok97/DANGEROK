# ORA — Roadmap canonica verso 1.0

**Questo documento è la source of truth del progetto.** Versione corrente,
prossimo sprint, dipendenze, ordine delle feature, criteri di uscita e
percorso fino al lancio si leggono qui e solo qui.

| | |
|---|---|
| **Versione corrente** | **V3.15.1a — COMPLETATA** |
| **Prossimo sprint** | **V3.15.2 — Post-Call Hardening** |
| Branch | `feature/ora-quiet-premium-design-system` |
| Ultimo checkpoint | `37af8a5` (lavoro) · `3baeaa1` (igiene) |
| Aggiornato | 2026-09-14 |

Gli altri due registri restano quello che sono e non ripetono questo:
`CHANGELOG_AI.md` è il diario datato di che cosa è cambiato,
`DEVELOPMENT_STATE.md` è lo stato tecnico sprint per sprint.
`BACKLOG.md` deriva da qui, come ha sempre fatto.

> La versione precedente di questo file era l'audit funzionale del
> 2026-08-04 con le Fasi A–F. Quelle fasi **non sono state cancellate**: sono
> confluite nelle Ere 0–2 qui sotto, e dove una riga è stata superata da un
> lavoro successivo è detto per nome. Non si riscrive la storia.

---

## Parte I — Le ere già percorse

Undici ere, dal 4 agosto al 13 settembre 2026. Tutte **CHIUSE**: sono il
terreno su cui poggia tutto il resto, e nessuna è stata abbandonata a metà.

### ERA 0 — Bootstrap · CHIUSA
**Obiettivo** — un progetto che si sviluppa da solo, in locale, senza Emergent.
**Deliverable** — bootstrap autonomo su Cursor · sviluppo locale verificato ·
audit funzionale e prima roadmap (Fasi A–F) · autenticazione Google e Apple
unificata.
**Exit criteria** — login reale, ambiente locale riproducibile. ✅

### ERA 1 — Document Intelligence · CHIUSA
**Obiettivo** — un documento smette di essere un file e diventa una cosa che
ORA capisce.
**Deliverable** — Documents V2 come motore di azioni · Gemini reale su
documenti sintetici · migrazione a `google-genai` · **Multi-provider Manager**
con Gemini di riserva · primo Google Calendar write sync da documento.
**Exit criteria** — un PDF vero produce un evento vero in calendario. ✅
**Superata da** — le scritture in calendario passano oggi da
`GoogleCalendarSyncService.reschedule_draft` (Era 10 in poi), non più dal
percorso diretto di allora.

### ERA 2 — Engines · CHIUSA
**Obiettivo** — smettere di scrivere flussi a mano e avere motori che li
compongono.
**Deliverable** — Action Engine · Intent Classification Engine · Study Action
Flow · Travel Action Flow · Goal Engine Foundation (shadow) · Goal-aware Home ·
**Proactive Engine** · **Conversation Engine** (orchestratore, non chatbot) ·
AI Life Setup + Life Strategist · AI-first Life Experience.
**Exit criteria** — due flussi verticali completi (studio, viaggio) end-to-end
con sync reale. ✅
**Regola nata qui e ancora in vigore** — *collaborazione guidata, non chat
libera* (`D5 Chat libera` resta esplicitamente fuori perimetro).

### ERA 3 — Life Objects + Digital Twin · CHIUSA
**Obiettivo** — dare a ORA un modello della vita di qualcuno, non un elenco di
record.
**Deliverable** — Life Object Engine come nucleo (shadow) · arricchimento
narrativo e di ragionamento · integrità semantica e validazione AI ·
**Digital Twin Knowledge Model**.
**Exit criteria** — gli oggetti reggono senza UI dedicata. ✅

### ERA 4 — Quiet Premium · CHIUSA
**Obiettivo** — una lingua visiva sola, che non urla.
**Deliverable** — Visual Foundation v1 · Home Quiet Premium · Application
Shell V1 · Login Quiet Premium · Human Presentation Semantics.
**Exit criteria** — ogni superficie parla la stessa lingua. ✅
**Nota** — dà il nome al branch su cui il progetto lavora ancora oggi.

### ERA 5 — Conversational Life Setup · CHIUSA
**Obiettivo** — il primo accesso è una conversazione, non un wizard.
**Deliverable** — Life Setup Gate pre-Home · Minimum Life Context ·
Walkthrough e correzioni · **AI-Native Conversational Rendering**.
**Exit criteria** — nessun modulo da compilare al primo avvio. ✅

### ERA 6 — Life Map / Memory / Epistemic Authority · CHIUSA
**Obiettivo** — ORA ricorda, e sa da dove sa quello che sa.
**Deliverable** — Contesti Life Map V1 · identità semantica e deduplicazione ·
Life Memory (Prompt 6) · loop di chiarimento · **autorità epistemica della
memoria**.
**Exit criteria** — ORA può dire *come* sa una cosa. ✅
**Evento** — qui cade l'**ORA Cognitive Reset**: Prompt 7.x abbandonato
(2026-08-12). Vedi *Debito dichiarato*.

### ERA 7 — AI-Native Cognitive Core · CHIUSA
**Obiettivo** — un nucleo che ragiona con strumenti, non una catena di if.
**Deliverable** — Prompt 7 V2 · retrieval di contesto personale · tool use
generico e conoscenza esterna ancorata · Life OS plans · **Generative
Workspaces** · adattamento persistente degli oggetti · superficie di produzione.
**Exit criteria** — il ciclo cognitivo regge il prodotto vero. ✅

### ERA 8 — Continuous Life Reasoning · CHIUSA
**Obiettivo** — ORA pensa anche quando nessuno le parla.
**Deliverable** — Context Broker V3 · Memory Proposal governata · Situation
Model · Calendar Intelligence · **Life Change Signal** · Impact Reasoning
(«SO WHAT?») · Attention & Intervention («SHOULD I SPEAK?») · orchestrazione
event-driven · recovery allo startup.
**Exit criteria** — un cambiamento nella vita produce un pensiero senza che
nessuno prema niente. ✅

### ERA 9 — Product Experience 3.0 · CHIUSA
**Obiettivo** — smettere di essere un insieme di motori e diventare un prodotto.
**Deliverable** — Product Experience Foundation · Home 3.0 come cruscotto
canonico · Conversation Resume (`WAITING_USER`) · **Life Guidance
Intelligence**.
**Exit criteria** — una conversazione interrotta riprende da sola. ✅

### ERA 10 — Connected / External Life · CHIUSA
**Obiettivo** — ORA guarda fuori: luoghi, posta, denaro.
**Deliverable** — Life Setup progressivo e Life Profile · Universal Research ·
Comparison & Recommendation · **Life Presence & Location** (zone, routine,
pendolarismo) · **Ambient Presence & Intelligent Delivery** · **Personal Agent
& Action Engine** · **Connected Life** (Gmail come sensore) · **Financial
Intelligence** · **Life Map & Universal Search** · **Autonomy Reality Gate**
(V3.2 / V3.7 / V3.8 / V3.9 riprovati sul vero).
**Exit criteria** — i sensori esterni alimentano il ragionamento senza lavoro
manuale. ✅

---

## Parte II — L'arco dell'azione nel mondo reale (V3.13 → V3.22)

Qui ORA smette di capire e comincia a **fare**. È l'arco aperto.

### V3.13 — Voice + Real Telephone · **PASS**
**Obiettivo** — ORA parla al telefono con un essere umano che non la conosce, e
conduce una commissione dentro un mandato scritto prima.
**Deliverable**
- Voice Interface · Multimodal Life Understanding
- Real Telephone Transport (Vonage, NCCO, WebSocket PCM)
- Real-Time Speech Runtime classico (Deepgram Nova-3 / Aura-2)
- **Runtime a missione su Gemini Live** dietro `ORA_VOICE_RUNTIME`
- `CallMissionPacket` — la missione, non la persona (~280 token, senza numero
  di telefono)
- **Contratto di presentazione** — «sono l'assistente di X», mai X
- **Confirmation gate backend-side** — «alle 18 abbiamo posto» ≠ «l'ho
  spostato alle 18», e a deciderlo non è chi parla
- Apertura proattiva · voce Kore · contratto di commiato · sicurezza in
  chiusura · barge-in
- **BeatCredits** e barriera a scadenza monotona nel playback
**Exit criteria** — otto telefonate reali; zero riagganci su chi sta parlando;
zero burst; nessuna interruzione udibile. ✅
**Debito lasciato** — p90/p95 del playback regrediti sulla chiamata 8;
buchi a monte di Gemini fino a 837 ms; deriva di lingua nella trascrizione
d'ingresso. → **V3.21**

### V3.14 — Call History · **PASS**
**Obiettivo** — chi ha chiesto la telefonata deve poter sapere com'è andata,
in italiano.
**Deliverable** — elenco Chiamate · dettaglio · trascrizione a richiesta ·
**stati di presentazione distinti da quelli interni** (com'è finita la linea,
com'è finita la missione, come si dice a una persona) · Chiamate nella sidebar
desktop fra ORA e Attività.
**Exit criteria** — la scheda risponde alla domanda per cui è stata aperta
senza mostrare un solo stato interno. ✅
**Debito lasciato** — paginazione sospesa (si leggono 300 righe e si impagina
in memoria); stato `segreteria` dichiarato e mai emesso. → **V3.21**

### V3.15 — Post-Call Application Layer · **PASS**
**Obiettivo** — chiudere il buco fra «hanno confermato» e «è spostato».
**Deliverable**
- **`CallMissionBinding`** — l'oggetto si decide *prima* della telefonata e non
  viaggia con la voce; nessuna ricerca per somiglianza dopo
- **`CallMissionApplication`** con chiave `missione|operazione|oggetto` come
  `_id`: a dire se una cosa è già stata fatta è il database, non un `if`
- adattatore calendario dietro un registro di domini — **solo `reschedule`**
- autorità, precondizioni, concorrenza ottimistica, stato `conflict`
- se l'applicazione fallisce **la telefonata resta riuscita**, e la scheda lo
  dice invece di rassicurare
- `PhoneCall.wrote` finalmente scritto, come annotazione e non come meccanismo
**Exit criteria** — un esito validato muta lo stato canonico di ORA, una volta
sola e solo quando è vero. ✅

### V3.15.1 — Reality Gate · **PASS**
**Obiettivo** — dimostrarlo sul vero, non sui finti.
**Deliverable** — telefonata reale con evento reale su Google Calendar.
**Exit criteria** (tutti verificati)
1. evento reale alle 16:00 · 2. la controparte conferma le 18:00 ·
3. **stesso** `google_event_id` passa alle 18:00 con durata conservata ·
4. nessun doppione · 5. `application_status = applied` · 6. `wrote` valorizzato ·
7. history coerente · 8. secondo apply senza scritture · 9. `needs_user` non
tocca niente. ✅
**Misure** — applicazione completa in ~2,1 s dalla chiusura sessione, di cui
~1,6 s di andata e ritorno con Google.

### V3.15.1a — Repo Hygiene · **PASS**
**Obiettivo** — togliere dal repo due artefatti non portabili.
**Deliverable** — eliminato il percorso macchina-specifico in
`test_confirmation_gate_v313.py` (ora legge `telephone.live.THE_SIX`, lo schema
che parte davvero: niente skip, più copertura) · sostituite tutte e 7 le
occorrenze del numero personale con `393000000000`.
**Exit criteria** — zero path utente, zero numeri reali, zero skip dovuti alla
macchina, 240 prove verdi. ✅

---

### V3.15.2 — Post-Call Hardening · **PROSSIMO**
**Obiettivo** — rendere robusto quello che V3.15 ha reso possibile. L'anello
debole non è più «sa scrivere», è «sa cosa fare quando la scrittura non
riesce».
**Deliverable previsti**
- ritentativo governato: oggi `failed` e `conflict` sono terminali per quella
  chiave, e Google giù per tre secondi significa calendario mai aggiornato
- recupero dei record rimasti `pending` (processo morto a metà applicazione)
- **reality gate del conflitto**: è l'unico ramo dell'application layer mai
  provato sul vero
- osservabilità dell'applicazione (quante riuscite, quante in conflitto, perché)
**Exit criteria** — un'applicazione fallita per causa transitoria arriva a
destinazione senza che nessuno la ripeta a mano; un `pending` non resta
`pending`; il conflitto è dimostrato su una telefonata vera.
**Dipendenze** — V3.15.1a. **Nessun `book`/`cancel` qui.**

### V3.16 — Calendar Actions Complete
**Obiettivo** — il dominio calendario completo, non un terzo di esso.
**Deliverable previsti** — adattatori `cancel` e `book` con la stessa
disciplina di `reschedule`: autorità, precondizioni, idempotenza, conflitto.
**Exit criteria** — disdire e prenotare al telefono mutano il calendario
canonico con le stesse nove prove di V3.15.1.
**Dipendenze** — **V3.15.2 chiusa.** Non prima.
**Perché aspetta** — oggi una disdetta riuscita lascia il calendario pieno: la
persona non si presenta a un appuntamento che risulta ancora suo. È lo stesso
buco di V3.15, in due domini gemelli — e va chiuso con un meccanismo già
irrobustito, non insieme all'irrobustimento.

### V3.17 — Needs User Continuation
**Obiettivo** — `needs_user` smette di essere un vicolo cieco.
**Deliverable previsti** — la decisione che ORA non poteva prendere torna alla
persona, viene presa, e **la commissione riprende da dove si era fermata** —
senza rifare la telefonata da capo.
**Exit criteria** — un esito `needs_user` si chiude con un'azione reale dopo
una risposta dell'utente.
**Dipendenze** — V3.16.

### V3.18 — Structured Authority
**Obiettivo** — il mandato smette di essere prosa.
**Deliverable previsti** — `may_agree_to` diventa una struttura verificabile
(finestre temporali, limiti, alternative) invece di testo libero che nessuno
interpreta.
**Exit criteria** — l'autorità si controlla per davvero al momento
dell'applicazione, e il limite dei 14 giorni — oggi un parafulmine, non un
controllo — può essere ritirato.
**Dipendenze** — V3.17.
**Perché serve** — finché ORA tratta solo orari dello stesso giorno regge; il
giorno che negozia una data, non c'è nessun cancello.

### V3.19 — Multi-Domain Application Layer
**Obiettivo** — l'application layer esce dal calendario.
**Deliverable previsti** — secondo e terzo dominio dietro il registro già
esistente; il confine adattatore/registro nato in V3.15 messo alla prova da
domini che non si somigliano.
**Exit criteria** — aggiungere un dominio non tocca `application.py`.
**Dipendenze** — V3.18.

### V3.20 — Autonomous Action Loop V1
**Obiettivo** — ORA non aspetta che le si chieda di agire.
**Deliverable previsti** — dal segnale (Era 8) alla proposta d'azione
all'autorità all'esecuzione, in un giro solo e governato.
**Exit criteria** — un'azione reale nasce da un pensiero di ORA e non da una
richiesta, con autorità esplicita.
**Dipendenze** — V3.19.

### V3.21 — Telephone Product Hardening
**Obiettivo** — saldare tutto il debito dichiarato di V3.13 e V3.14.
**Deliverable previsti** — p90/p95 del playback · stato `segreteria` con un
segnale affidabile · paginazione Call History · deriva di lingua · buchi a
monte del fornitore.
**Exit criteria** — nessun debito telefonico dichiarato resta aperto.
**Dipendenze** — V3.20.

### V3.22 — Call UX Final
**Obiettivo** — la telefonata come funzione di prodotto finita, non come
capacità tecnica.
**Deliverable previsti** — la superficie completa intorno alla chiamata:
avviarla, seguirla, capirla, riprenderla.
**Exit criteria** — una persona che non ha mai letto questa roadmap sa usarla.
**Dipendenze** — V3.21. **Chiude l'arco V3.**

---

## Parte III — Da V4 a ORA 1.0

Nessuna di queste è cominciata. Sono **PIANIFICATE**, e l'ordine è quello.

| Versione | Obiettivo | Exit criteria |
|---|---|---|
| **V4 — Proactive ORA** | ORA parla per prima quando serve, e tace quando non serve | La proattività è utile misurata, non solo possibile |
| **V5 — Long-Running ORA** | commissioni che durano giorni, non un turno | Un obiettivo sopravvive a riavvii, attese e interruzioni |
| **V6 — Learning & Personal Adaptation** | ORA impara come sei, in modo governato | L'adattamento è spiegabile e reversibile |
| **V7 — Unified ORA Intelligence** | un'intelligenza sola, non motori affiancati | Nessuna superficie ragiona per conto suo |
| **V8 — Mobile & Daily Product** | ORA vive nella giornata, sul telefono | Uso quotidiano reale su device |
| **V9 — Privacy, Safety & Trust** | il patto con chi si fida | Audit, cancellazione, minima divulgazione dimostrate |
| **V10 — Reliability / Production Infrastructure** | regge senza qualcuno che guarda | Deploy, backup con restore provato, CI, osservabilità |
| **V11 — Closed Alpha** | primi utenti veri, pochi e seguiti | Sopravvive a persone che non sono l'autore |
| **V12 — Private Beta** | più utenti, meno mani | Difetti trovati da altri, non da noi |
| **V13 — Public Beta / RC** | candidato al rilascio | Nessun difetto bloccante aperto |
| **ORA 1.0** | **Lancio** | Vedi sotto |

---

## Parte IV — Che cos'è ORA 1.0

La 1.0 è raggiunta quando ORA sa fare **stabilmente** tutto questo, in fila e
senza che qualcuno tenga insieme i pezzi:

```
capire il contesto
  → capire cosa conta
    → ricevere o proporre un obiettivo
      → ottenere l'autorità corretta
        → agire nel mondo reale
          → gestire le eccezioni
            → riconciliare il risultato col proprio stato
              → informare la persona
                → imparare e adattarsi in modo governato
```

Il verbo che conta è **stabilmente**. Ognuno di questi passaggi oggi esiste
almeno una volta; nessuno esiste ancora per ogni dominio e in ogni condizione.

---

## Parte V — I gate di lancio

Nessuno di questi si salta, e nessuno si dichiara chiuso senza una prova
sul vero.

| Gate | Stato oggi | Dove si chiude |
|---|---|---|
| **Context affidabile** | in piedi | Ere 6–8, 10 |
| **Reasoning stabile** | in piedi | Ere 7–8 |
| **Actions reali** | **prima prova superata** | V3.15.1 · si allarga fino a V3.20 |
| **Calendar completo** | **un terzo** (solo `reschedule`) | V3.16 |
| **Phone production-ready** | funziona, non è di prodotto | V3.21 · V3.22 |
| **Needs-user continuation** | vicolo cieco | V3.17 |
| **Reconciliation robusta** | riesce, non ritenta | V3.15.2 |
| **Proactivity utile** | esiste, non misurata | V4 |
| **Recovery / idempotenza** | idempotenza ✅, recovery ✗ | V3.15.2 · V10 |
| **Mobile completo** | no | V8 |
| **Privacy / audit** | principi in vigore, audit no | V9 |
| **Production infra** | no | V10 |
| **Alpha / Beta superate** | no | V11 · V12 · V13 |

---

## Debito dichiarato

Cose vere, aperte, che non appartengono a nessuno sprint finché qualcuno non
decide.

**L'architettura cognitiva Prompt 7.x** — 29 voci non tracciate
(`backend/conversation_engine/cognitive/` + 14 test, `frontend/app/cognitive/`,
`backend/llm/{capabilities,health}.py`, otto script QA). Lavoro vero che non è
in nessun commit; backup solo in `stash@{1}`. Porta con sé un
`test_provider_resilience_v741.py` che non importa. **Decisione richiesta: o
entra, o si dichiara abbandonato.** Non è una feature, è una scelta.

**Rossi preesistenti** nella suite completa (`knowledge_*`, `life_graph`,
`iter*`, `travel_action_flow`) — confermati estranei al lavoro telefonico, mai
indagati.

**`FEATURE_STATUS.md`** — fermo al 2026-08-06. È una matrice di feature, non
una roadmap, e non è stato riallineato con questo documento.

**Fuori perimetro, per scelta** — chat libera (`D5` della vecchia roadmap):
ORA è collaborazione guidata. La regola è dell'Era 2 e non è mai cambiata.
