# ORA — Roadmap canonica verso 1.0

**Questo documento è la source of truth del progetto.** Versione corrente,
prossimo sprint, dipendenze, ordine delle feature, criteri di uscita e
percorso fino al lancio si leggono qui e solo qui.

| | |
|---|---|
| **Versione corrente** | **V3.21.2 — Call Failure & Recovery Hardening · PASS** |
| **Prossimo sprint** | **ORA Product Experience Rebuild — NOT STARTED** |
| Branch | `feature/ora-quiet-premium-design-system` |
| Ultimo checkpoint | `37af8a5` (lavoro) · `3baeaa1` (igiene) |
| Aggiornato | 2026-09-19 |

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
buchi a monte di Gemini fino a 837 ms *(diagnosi superata in V3.21.1: i buchi udibili erano locali — vedi V3.21.1)*; deriva di lingua nella
trascrizione d'ingresso. → **V3.21**

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

### V3.16 — Calendar Actions Complete · **PASS**
**Obiettivo** — il dominio calendario completo, non un terzo di esso.
**Deliverable** — adattatori `cancel` e `book` con la stessa disciplina di
`reschedule` · schema di conferma per tipo di missione · `created_entity_id`
separato dall'identità · guardia sul doppione col nome della missione
sull'evento · **ripresa di sessione Gemini Live** e voce **Charon** fissata su
ogni filo · il socket audio aspetta il fascicolo invece di ripiegare in
silenzio sul runtime classico · riaggancio garantito dopo il commiato.
**Exit criteria** — due telefonate reali, una CANCEL e una BOOK. ✅
- **CANCEL**: `ced_6266be8073c2` → `cancelled` qui e su Google, nessun altro
  evento toccato, secondo apply senza scritture.
- **BOOK**: `ced_53b89319a11d` → un solo evento canonico e uno solo su Google,
  25/09 15:00–15:30, `created_entity_id` valorizzato, `target.entity_id`
  vuoto, secondo apply senza duplicati.
**Debito lasciato** → **V3.21**: buchi dell'audio a monte di Gemini (17 sopra
i 100 ms sull'ultima chiamata, `inbound_gap_max` 934 ms, cuscino di 200 ms
insufficiente) *(diagnosi superata in V3.21.1: i buchi udibili erano locali — vedi V3.21.1)* · **reality gate della ripresa di sessione mai scattato** — il
filo non è più caduto, quindi il codice di ripresa è provato solo sui finti ·
ulteriore irrobustimento di voce e trasporto.

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

### V3.17 — Needs User Continuation · **PASS**
**Obiettivo** — `needs_user` smette di essere un vicolo cieco.
**Deliverable** — `CallMissionContinuation` (pausa · domanda mostrata · ripresa
· esito) · tre decisioni possibili, accetta / proponi altro / lascia perdere ·
la ripresa porta **il nome della missione originale**, eredita il legame e
riscrive l'obiettivo con quello che è stato deciso · due rotte e la decisione
dentro la scheda della telefonata · `request_user_confirmation` distinto da
`fail_mission`, con la proposta che arriva fino a chi deve rispondere.
**Exit criteria** — un esito `needs_user` si chiude con un'azione reale dopo
una risposta dell'utente. ✅ (seconda passata, 2026-09-15)
- autorità stretta → lo studio propone un'altra data → `needs_user`, una sola
  continuation, **zero mutation** prima della decisione;
- «Va bene così» → stessa `mission_id` logica, stesso evento, autorità estesa
  solo dalla decisione, doppio click senza seconda chiamata;
- la richiamata ha chiesto **l'alternativa accettata**, non l'orario di
  partenza — è il difetto che la prima passata aveva scoperto;
- una sola scrittura, Google coerente, secondo apply senza scritture.
**Debito lasciato** → **V3.21**: latenza di risposta (p50 1,6÷3,1 s, quasi
tutta a monte di Gemini — il nostro percorso critico è sotto il millisecondo).

### V3.18 — Structured Authority · **PASS**
**Obiettivo** — il mandato smette di essere prosa.
**Deliverable** — `CallMissionAuthority` accanto al mandato in parole:
operazione · oggetto · `TimeSlot` desiderato · alternative come date vere ·
`earliest` / `latest` / `same_day_only` · cambiamenti vietati per nome ·
`human_summary` separato dalla policy · `evaluate_authority()` come **unico
giudice**, deterministico, con quattro verdetti distinti (`allowed` ·
`needs_user` · `forbidden` · `invalid`) e un motivo in due forme · consultato
prima di ogni scrittura in tutti e quattro i punti (applica e riconcilia, per
le tre operazioni) · la decisione di V3.17 aggiunge un orario alla policy
invece di concatenare testo · la capability espone i vincoli strutturati.
**Exit criteria** — l'autorità si controlla per davvero al momento
dell'applicazione. ✅ 24 prove nuove, 371 su tutto l'arco.
**Compatibilità** — `may_agree_to` resta per presentazione e ripiego, **fuori
dal percorso decisionale**. Una missione senza policy non è una missione senza
regole: è più vecchia, `evaluate_authority` risponde `invalid` — che non è un
no — e a decidere restano i controlli di prima.
**Debito lasciato** → **V3.21**: il parafulmine dei 14 giorni è ancora lì,
perché serve alle missioni senza policy. Si potrà ritirare quando ogni
telefonata ne avrà una.

### V3.19 — Multi-Domain Application Layer · **PASS**
**Obiettivo** — l'application layer esce dal calendario.
**Deliverable** — contratto comune in otto doveri (`remembers` · `authority` ·
`look` · `translate` · `apply` · `reconcile` · `detect_conflict` · `says`),
scritto una volta in `telephone/domains/__init__.py` come `Protocol` e
verificabile da `follows_the_contract()` · registro per coppia
`(dominio, operazione)`, consultato dal runtime in due punti soli e senza un
solo `if` sul nome di un dominio · **due domini nuovi**, scelti dopo un censimento
dei percorsi di scrittura veri: `commitments` (le decisioni, dietro
`ActionCenterService` — macchina a stati, audit scritto prima della mutazione,
campo legacy allineato) e `study` (le sessioni di piano, dietro
`StudyPlanService.session_action` — avanzamento ricalcolato ed evento Google
risincronizzato) · legame generico `bind_a_domain_target()` che chiede al
dominio che cosa fotografare · `evaluate_authority()` resta **l'unico giudice**
per tutti e tre.
**Exit criteria** — aggiungere un dominio non tocca `application.py`. ✅ 31
prove nuove, 336 su tutto l'arco telefonico. Le nove domande — successo ·
`needs_user` · autorità che vieta · doppia applicazione · morte prima della
scrittura · morte dopo · conflitto · recupero · nessun mandato — poste a
entrambi i domini nuovi, e il calendario ancora verde.
**Onestà** — `application.py` **è** stato toccato: due righe, per chiedere al
registro la coppia invece del solo dominio. È una generalizzazione fatta una
volta; il quarto dominio non ne tocca nessuna.
**Debito lasciato** → **V3.21**: una sessione di studio si può rimandare e non
anticipare, perché `session_action` sposta per differenza e non esiste una
seconda porta che accetti un istante. Un accordo che la anticipasse viene
fermato e raccontato, non forzato — aprire quella porta vorrebbe dire un
secondo scrittore per `starts_at`, che è la cosa che questo sprint esiste per
non fare. Nessuno dei due domini nuovi è ancora passato da un reality gate su
telefono vero: il contratto è provato, la chiamata no.
**Dipendenze** — V3.18.

### V3.20 — Autonomous Action Loop V1 · **PASS**
**Obiettivo** — un giro solo, dall'innesco al mondo cambiato, senza scorciatoie.
**Fatto** — `autonomy/` è un filo sottile che non apre nessun motore:
`AutonomousActionPlan` tiene il proposito (nove stati, `authority_state` e
`verified` separati apposta da `state`), `advance()` è un passo che rilegge il
mondo invece di ricordarselo — chiamato due volte dà due volte la stessa
risposta, che è l'unico modo in cui un giro si riprende dopo un processo morto.
Due percorsi d'ingresso: una richiesta di una persona arriva fino al calendario
cambiato; un segnale arriva fino alla proposta e **si ferma lì**. La chiave del
piano è il suo `_id`, e l'innesco è la missione — non la telefonata — perché una
commissione fermata e ripresa è un proposito solo. Ganci sottili su
`prepare` · `place` · fine chiamata · decisione · recupero. Porte di sola
lettura più una per fermarsi; il sì passa da dove è sempre passato.
**Exit criteria — superati** — un ciclo reale completo (richiesta → piano →
autorità → telefonata → esito → applicazione → stato canonico → resoconto)
senza bypass e senza doppie scritture; `completed` solo dopo che il dominio ha
guardato lo stato canonico e ha detto che ci è arrivato. 22 prove nuove, 432
verdi su tutto l'arco V3.13÷V3.20.
**Reality gate — superato su telefono vero** (17/09/2026, `plan_046df24ad4294171`).
Un giro solo, dalla capacità vera alla porta vera: `waiting_authority` ·
`authorised` · `executing` · `completed`, con `authority_state` che resta un
campo suo. Una missione logica, un record di applicazione, una scrittura su
Google — «TEST ORA — continuazione» spostato dalle 18:00 alle 19:00 del 30
settembre, `sync_status: synced`. `verified` è diventato vero soltanto dopo che
`landed()` ha riletto lo stato canonico, e un secondo `advance` non ha prodotto
niente. Frase finale a chi aveva chiesto: «Fatto — Appuntamento spostato alle
19:00.»
Alla prima chiamata non ha risposto nessuno: `ring_timeout`, nessuna
applicazione, e il recupero periodico ha chiuso il piano appeso a `failed` da
solo — il caso che il ciclo deve saper raccontare, capitato per davvero.
**Caller ID italiano — PASS.** `+3907611810322` sia nel registro Vonage sia
nell'NCCO servito dal backend. Il numero UK non è più né in configurazione né
sull'account.
**Debito lasciato** → **V3.21**: il percorso da segnale usa la `dedupe_key` dei
Life Change Signal ma non è agganciato all'attention pass, quindi una proposta
di ORA nasce solo se qualcuno la apre; `needs_an_external_mission()` risponde
sempre sì, perché oggi l'unica azione esterna è il telefono. E quello che si
sente: 2,0 s dal «pronto» alla voce (2770 · 1721 · 1977 ms di primo audio
Gemini, contro 0,68 ms di percorso nostro), undici buchi sopra i 100 ms e due
interruzioni dentro un turno sopra il secondo (1235 e 1153 ms) — misurato sulla
chiamata del gate, ed è la stessa cosa dichiarata da V3.16 *(diagnosi superata in V3.21.1: i buchi udibili erano locali — vedi V3.21.1)*. Più la deriva di
lingua: la controparte è stata trascritta in portoghese a metà telefonata.
**Dipendenze** — V3.19.

### V3.20.1 — Contact Resolution & Mission Preparation · **PASS**
**Obiettivo** — ORA arriva da una frase a una telefonata che si può fare, senza
che una persona debba preparare a mano numero, contesto e copione.
**Fatto** — `preparation/` in cinque pezzi. Il **risolutore** cerca chi
chiamare in ordine di certezza — rubrica, contesto ORA (telefonate già fatte,
calendario, nodi e ricordi), web pubblico, e infine la domanda — e la
provenienza viaggia sempre col numero, perché «Rubrica» e «Trovato sul web»
sono due cose diverse davanti alla stessa cifra. Il contratto delle fonti è
scritto per la rubrica di iOS che arriverà: dovrà rispondere a `look_for` e si
infila davanti a tutte le altre. **Sul web si cercano attività, non persone**:
non per prudenza, perché sono due operazioni diverse, e nel dubbio si risponde
«persona» — che è la risposta che porta a chiedere. Il **recupero del
contesto** guarda prima di chiedere: la partita di venerdì, l'impegno aperto,
la sessione di studio, la telefonata già fatta. Il **valutatore** è AI per
capire che cosa manca e deterministico per decidere: un modello può abbassare
il verdetto, mai alzarlo sopra quello che i fatti permettono. Il **riassunto**
porta sette cose e nessun identificativo. E il **cancello** vuole due sì —
`number_confirmed` e `conversation_ready` — scritto in un posto solo.
**Exit criteria — superati** — «Chiama Lorenzo e digli di spostare la partita a
calcetto» diventa una missione pronta chiedendo una cosa sola, l'orario nuovo;
un numero non confermato produce zero telefonate. 23 prove nuove, **455 verdi**
su V3.13÷V3.20.1.
**Verificato davvero dalla UI** (`frontend/e2e-evidence/v3201/`, due percorsi
Playwright su app in esecuzione): risoluzione del contatto con provenienza ·
domanda dinamica su quello che manca · numero accettato · missione pronta
raccontata al futuro · cancello negativo, in cui il pulsante per chiamare non
è disabilitato ma **non esiste**.
**Final hardening — fiducia nei numeri e web reale · PASS.**
La fiducia sta sulla **coppia identità + numero**, in `trusted_numbers`
(`preparation/trust.py`): nuovo, perché nel progetto non c'era un posto per «che
cosa ha confermato la persona» — la rubrica dice che cosa c'è sul telefono, ed è
un'altra cosa. Tre stati, nessuno cancella: `active` · `stale` (sostituito) ·
`rejected`. Un numero **nuovo**, da qualunque fonte, aspetta un sì; uno **già
confermato** per la stessa identità si riusa senza richiederlo, dicendo quale
sarà e perché, con «Cambia numero» sempre disponibile. Un cambio mette il vecchio
a `stale` e fa aspettare il nuovo; un rifiuto non si ripropone più; un numero
diverso per la stessa persona **non sovrascrive** quello confermato — si mostrano
tutti e due. Lo stesso numero per un'altra identità non eredita niente. «Chiama
il 333…» vale per quella richiesta; «il numero di Lorenzo è 333…» vale per
Lorenzo. Il cancello rilegge la fiducia al momento di preparare la chiamata.
**Ricerca web reale** su una vera attività (Hotel Excelsior, Lido di Venezia):
sito ufficiale proposto per primo, corroborato da un'altra fonte, gli altri numeri
visibili come alternativa, e la conferma comunque richiesta. Il gate ha trovato
e fatto correggere tre difetti che la fonte finta nascondeva: `_host()` non
esisteva e ogni risultato vero cadeva in silenzio; una pagina su **un'altra**
farmacia passava per buona; un portale col nome della località passava per sito
ufficiale. Nessuna telefonata fatta. 23 prove nuove, **478 verdi** su
V3.13÷V3.20.1; cinque schermate in `frontend/e2e-evidence/v3201-final/`.
**Rubrica iOS (Contacts / `CNContactStore`) — CONTRACT READY · PRODUCTION
INTEGRATION PENDING.** La fonte `AddressBook` e il contratto `ContactSource`
sono pronti a riceverla; oggi risponde «niente», perché `contacts.read` si può
dare solo da un telefono e non è ancora stata data.
**Debito lasciato** → **V3.21**: rubrica iOS vera; la ricerca web dipende da
quello che il motore restituisce, che cambia da un giro all'altro — la seconda
ricerca mirata al sito ufficiale lo attenua, non lo elimina; Google Places
(la scheda a destra nei risultati) scartata perché a pagamento; il legame
generico `bind_a_domain_target` esiste ma la preparazione lega solo il
calendario.
**Dipendenze** — V3.20.

### V3.21 — Telephone Product Hardening
**Obiettivo** — saldare tutto il debito dichiarato di V3.13 e V3.14.
**Deliverable previsti** — p90/p95 del playback · stato `segreteria` con un
segnale affidabile · paginazione Call History · deriva di lingua · **buchi
nell'audio** — *causa aggiornata in V3.21.1*: i buchi udibili sopra il secondo
non venivano da Gemini ma dal processo stesso, fermato ~450 ms da ogni client
HTTP creato durante la chiamata (caricamento dei certificati); i buchi di
Gemini, fino a ~200 ms, vengono assorbiti dalla coda · **reality gate
della ripresa di sessione**, mai scattato perché il filo non è più caduto ·
ulteriore irrobustimento di voce e trasporto · **latenza di risposta**,
p50 fra 1,6 e 3,1 secondi su telefonate vere — *aggiornato in V3.21.1*:
~1,1 s era l'attesa di silenzio del VAD di Gemini, configurabile e ridotta;
resta a monte ~0,7 s di generazione.
**Exit criteria** — nessun debito telefonico dichiarato resta aperto.
**Dipendenze** — V3.20.

#### V3.21.1 — Live Conversation Quality + Language Stability · **PASS**
**Latenza.** Il percorso locale era già quasi nullo (57–113 ms dal primo audio
Gemini alla linea). Il grosso era l'attesa di silenzio del VAD di Gemini,
configurabile: misurata su Gemini vero senza telefono — default 1781 ms,
700 ms → 1495, **500 ms → 1182** (mediane). `silenceDurationMs: 500` con
`END_SENSITIVITY_HIGH`, regolabile da `GEMINI_LIVE_SILENCE_MS` (300–2000).
Sulle chiamate vere: apertura **1596 · 1498 ms** (era 2770), turni p50
**1498 ms** (erano 1,7–2,8 s). Resta a monte ~0,7 s di generazione Gemini.
**Scatti — causa trovata, era locale.** La diagnosi precedente, che li
attribuiva a Gemini, era incompleta: la nuova strumentazione l'ha corretta. Ogni `httpx.AsyncClient()` nuovo
ferma l'event loop ~450 ms (max 761) per caricare i certificati: due, aperti
dalla sincronizzazione di sfondo durante l'apertura, sono i due buchi da
1235/1152 ms del gate V3.20. Preso sul fatto da un testimone degli stalli al
riaggancio (548 ms, `carrier.hang_up → ssl.create_default_context`).
Rimedio: contesto TLS condiviso nel carrier (0,1 ms) e letture di sfondo
rimandate mentre una telefonata parla. I gap di Gemini non si sentivano:
21/21 assorbiti dalla coda. Ogni buco ora lascia una fotografia classificata
A/B/C/D.
**Lingua.** La deriva era nella trascrizione della controparte. La lingua
viaggia nel pacchetto (`language="it"`) e arriva a `speechConfig.languageCode`
e a entrambe le trascrizioni (`languageCodes`) — campi verificati come
esistenti sul server, che rifiuta quelli inventati. Rilevatore di deriva
deterministico: zero derive in due chiamate vere. Charon su ogni setup.
**Debito lasciato** → blocchi V3.21 successivi: barge-in e nomi propri non
esercitati dal vivo (solo prove automatiche); con due domande in una frase,
un «no» parziale chiude la missione senza richiedere il pezzo mancante; 33
altri punti del progetto creano ancora client HTTP senza contesto condiviso;
le suite ambient v38 sono instabili anche su HEAD (DB condiviso, verificato
A/B). Due tentativi di chiamata sono finiti per errore a un numero di terzi
(lo script sceglieva «l'ultimo numero»): corretto, destinatario verificato.

#### V3.21.1a — General Phone Capability + Message Delivery · **FINAL PASS**
**Il problema.** In chat ORA rispondeva «non posso telefonare»: lo strumento
era descritto solo per studi e attività, e chiedeva un numero obbligatorio.
**Capacità dichiarata dal vero.** Il prompt riceve `what_ora_can_do`, derivato
dagli strumenti realmente disponibili: con lo strumento presente «puoi
telefonare», senza nessuna promessa. `prepare_a_phone_call` vale per chiunque
(persone private comprese), `counterparty` al posto del numero obbligatorio.
**Nuova missione `deliver_message`.** Il messaggio viaggia nel mandato con le
parole di chi lo manda, mai nel motivo; il modello Live non lo vede finché
`recipient_confirmed` non ha verificato la persona. Persona sbagliata →
nessuna rivelazione; risposta del destinatario catturata; esiti
delivered / recipient_unavailable / wrong_person / no_answer / failed /
needs_user; nessuna scrittura applicativa; storico in parole umane
(«Messaggio consegnato a Giulia.», «Giulia ti ha risposto: "…"»).
**Contatto e conferme (V3.20.1 invariato).** Rubrica, numeri già confermati
riusati anche per richieste relazionali («la mia ragazza»), numero nuovo →
«Ho trovato X, numero (provenienza). È questo il numero corretto?», poi il
riassunto con il messaggio fra virgolette e «Vuoi che la chiami?».
**Trovati e corretti durante la prova in app.** (1) La richiesta stessa
(«chiama…») contava come «sì» e rendeva affidabile un numero mai confermato:
ora il sì si legge solo dalle parole della persona, prima parola, e mai dal
testo della richiesta. (2) Il modello riassumeva la conferma in «Ok.» o in
«È questo il numero corretto?» senza numero: la frase dello strumento
(`say_this`) fa fede, cercata nelle osservazioni del turno. (3) Un solo «sì»
confermava il numero **e** dava il via libera, saltando il riassunto: il via
libera ora vale solo per un riassunto mostrato in un turno precedente.
**Prova.** Chat reale: «Chiama la mia ragazza e dille che la amo» → contatto
di prova Giulia Test con provenienza → «sì» → riassunto con «la amo» →
fermo a READY, nessuna telefonata creata. Contatto e record di prova rimossi.
Regressione telefono + chat: 1126 test verdi.
**Final gate (2026-09-19, telefonata vera autorizzata dal CPO).** Dalla chat:
«Chiama la mia ragazza e dille che la amo» → «Ho trovato Asia, +39 327 •••
••11 (Rubrica — ragazza). È questo il numero corretto?» → «sì» → riassunto
con «la amo» e «Vuoi che la chiami?» → «Sì» → «Sto chiamando Asia…». Il
secondo sì compone dalla stessa porta della route (`telephone/placing.py`,
unico `carrier.place`), senza API manuali. In linea: caller ID italiano,
Charon, it-IT, zero derive, una connessione Live, zero riconnessioni;
«Ciao, sono l'assistente di Francesco. Parlo con Asia?» → «Sì» →
«Francesco mi ha chiesto di dirti che ti ama» → risposta acquisita → saluto →
riaggancio. Esito `delivered`, nessuna application, piano `completed`, una
sola telefonata. In chat, senza id né stati: «Messaggio consegnato… Ti ha
risposto: «…»».
**Bug emersi dal vero e corretti.** (1) La chat rileggeva la conversazione un
istante prima che la riga dell'esito arrivasse: ora aspetta `chat_told_at`,
scritto dopo la riga, e un salvataggio vecchio non lo cancella. (2) «Ciao!»
non era riconosciuto come congedo: tre saluti in più («Arrivederci», «Buona
giornata»…). (3) Nome del profilo in minuscolo («francesco»). (4) «a Asia»
→ «ad Asia». Più: apertura «Ciao» per una consegna, attribuzione esplicita
del messaggio al mittente, «Questo non posso deciderlo per lui».
**Debito.** L'apertura è stata interrotta dal «Pronto?» sovrapposto e ripetuta
(`opening_state` resta `pending`); «Parlo con Asia?» detto due volte; la
risposta è la trascrizione letterale del modello («Dirgli anche io tanto»),
non corretta a posteriori. Tunnel quick di Cloudflare instabile: serve un
indirizzo fisso prima del lancio. Due telefonate «autorizzate» e mai composte
del 18/09 (vecchio percorso) restano nello storico.

#### V3.21.2 — Call Failure & Recovery Hardening · **PASS**
**Apertura.** Stati `not_started · speaking · interrupted · identity_pending ·
completed`. Causa del doppio «Parlo con Asia?» trovata: con una sola parola
chiave il registro dell'apertura ne esigeva due, e la nota faceva ripetere la
domanda. Interrotta a metà, la nota arriva subito e dice solo il pezzo
mancante («Hai già detto di chi sei l'assistente: di' soltanto «Parlo con
Asia?»»).
**Esiti.** `result_of(call)` legge insieme linea ed esito validato:
success · no_answer · busy · voicemail · recipient_unavailable · wrong_person
· not_connected · transport_failure · live_runtime_failure · partial ·
needs_user · not_started. Per chi legge: «Non ha risposto.», «Il numero era
occupato.», «Ha risposto la segreteria.», «La chiamata si è interrotta prima
che riuscissi a concludere.», «Non avviata». Nessun codice tecnico in UI.
**Segreteria.** `machine_detection: continue` di Vonage (evento `human`
visto sul vero) + frasi da messaggio registrato: si dichiara solo con due
segnali; uno solo resta `suspected`. Nessun messaggio lasciato; il messaggio
di una consegna non esce nemmeno se la segreteria dice «sono Asia».
**Linea che cade.** Senza esito: `failed` se non era cominciata, `needs_user`
con una proposta sul tavolo, altrimenti `partial` — con `ended_because`
(`line_dropped` / `live_runtime_failure`). Un esito già validato resta.
**Risposte parziali.** «No» di ≤3 parole dopo due domande: `complete_mission`
e `fail_mission` respinti («una cosa alla volta»), al massimo due volte.
**Piano.** Una chiamata `failed`/`expired` è finita: prima il piano di una
chiamata non risposta tornava «authorised» per sempre. Nessuna risposta e
occupato ora avvisano il piano anche senza conversazione. Recupero: chiamate
«in corso» senza notizie oltre durata+15 min → chiuse; zero piani bloccati.
**Fantasmi.** Un sì vale due ore: le due chiamate del 18/09 (vecchio percorso
chat senza tasto per comporre) sono ora `expired` → «Non avviata»; `dial`
rifiuta una chiamata scaduta.
**Storico.** Paginazione vera: cursore `authorised_at|id`, filtro su
`status_reads` scritto a ogni salvataggio, conteggio reale, indici; verificata
sull'API: 61 chiamate in 13 pagine, zero duplicati.
**HTTP sul percorso Live.** `websockets.connect` verso Gemini creava un
contesto TLS nuovo a ogni apertura (~450 ms di loop fermo), anche alla ripresa
a metà telefonata: ora usa quello condiviso. Il resto dei 33 punti resta debito.
**Tunnel.** Prima di comporre si prova l'indirizzo pubblico: se non risponde
la chiamata non parte e il motivo scritto è «tunnel», non Gemini. Il quick
tunnel è caduto due volte durante lo sprint: debito V10 / pre-production.
**REAL GATE A — ripresa di sessione: PASS** (numero verificato dell'utente).
Fault injection DEV-ONLY (`ORA_DEV_DROP_LIVE_AFTER_TURNS`, spenta di default,
impossibile con `ENVIRONMENT=production`): connessione 1 chiusa dopo 2 turni,
connessione 2 ripresa con handle in 926 ms, stessa `mission_id` su entrambe,
una sola chiamata carrier, nessuna seconda apertura, Charon + it-IT su
entrambe, messaggio consegnato, risposta acquisita, saluto e riaggancio.
Trovato dal vivo e corretto: la ripresa buttava l'audio già generato e
completo (messaggio tagliato e ripetuto); ~5,5 s di silenzio dopo il «sì»
per sbloccare il messaggio → regola «saluta subito mentre aspetti».
**REAL GATE B — nessuna risposta: PASS** (al quarto giro). Trovati dal vivo e
corretti: Vonage manda `completed` e `timeout` nello stesso millisecondo con il
motivo in `detail`, e il primo diceva «hanno riagganciato»; il valutatore della
preparazione inventava una domanda su un messaggio già completo; la guida
della chat accorciava la conferma del numero; riepilogo al femminile fisso.
Ultimo giro: `failed / no_answer`, piano `failed` («Non ha risposto.»), zero
application, una chiamata, esito in chat.
**REALITY GATE PENDING:** occupato e segreteria — non producibili in modo
controllato senza chiamare terzi; coperti da prove con i payload dell'operatore.
**Debito.** Ritardo di due giri Gemini per sbloccare il messaggio di una
consegna; quick tunnel; 33 client HTTP fuori dal percorso Live; frasi
dell'apertura e dei saluti ancora affidate al modello.

#### Debito registrato durante V3.21 — ORA Product Experience Rebuild · **NOT STARTED**
**Priorità** — alta. Emerso dall'audit completo dell'app reale (video 2026-09-19).
Non è semplice polish: l'esperienza principale non rappresenta ancora ORA come
assistente di vita unico, coerente e operativo.

**Scope registrato** — redesign completo di Chat ORA · redesign Home / «Cosa
conta davvero ora» · sincronizzazione canonica di «Domande per te» fra chat e
Home · aggiornamenti ORA con provenance, contesto, stato e next step · riduzione
della latenza del motore conversazionale (distinta dalla telefonia) · place
presence affidabile per entrata/uscita/rientro · navigazione intelligente con
traffico, tempi, consiglio e ora di partenza prima dei link alle mappe ·
riallineamento UI di Call Preparation · Vita/Conosciamoci · Documenti · shell e
design system Quiet Premium unificati.

**Reference visuali approvate** — `ora_il_tuo_assistente_quotidiano.png` ·
`dashboard_ora_più_tempo_per_te.png` ·
`preparazione_sicura_della_telefonata.png` ·
`conosciamoci_il_percorso_ora.png` ·
`dashboard_ora_per_i_documenti_sanitari.png`.

**Regola** — debito solo registrato in roadmap: non si implementa durante il
lavoro telefonico corrente. Quando verrà aperto, le reference sono target
visivi autorevoli e il pass richiederà app reale, screenshot comparativi e
reality gate funzionali sui difetti osservati.

L'ordine resta: V3.21.1a ✅ → V3.21.2 ✅ → ORA Product Experience Rebuild → V3.22 → V4.

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
| **Actions reali** | **sì** — un giro intero, dall'innesco allo stato canonico | ✅ V3.20 |
| **Ciclo autonomo** | **V1** — richiesta fino in fondo, segnale fino alla proposta | ✅ V3.20 |
| **Calendar completo** | **sì** — spostare, disdire, prenotare | ✅ V3.16 |
| **Application multi-dominio** | **sì** — calendario · impegni · studio, un contratto solo | ✅ V3.19 |
| **Phone production-ready** | funziona, non è di prodotto | V3.21 · V3.22 |
| **Needs-user continuation** | **sì** — si ferma, si decide, riprende | ✅ V3.17 |
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

**L'architettura cognitiva Prompt 7.x — DECISA: non entra** (2026-09-14).
Ottantasei file e circa 9.900 righe che nessuna riga del prodotto importava: né
il backend, né una rotta del frontend, né `llm/__init__.py`. Un secondo stack
cognitivo accanto a quello che regge il prodotto, e due modi di fare la stessa
cosa sono peggio di uno solo.

Rimosso dal working tree insieme ai suoi quattordici test, ai due moduli
`llm/{capabilities,health}.py` che solo lui usava, alla rotta
`frontend/app/cognitive/` mai raggiungibile e a
`test_provider_resilience_v741.py`, che non importava nemmeno.

**L'idea non è persa.** Il backup vive in `stash@{1}` — verificato, 57 file
cognitivi — e il problema che provava a risolvere è esattamente quello di
**V7 — Unified ORA Intelligence**: un'intelligenza sola invece di motori
affiancati. Quando V7 comincerà, quel codice è materiale da leggere, non da
riapplicare.

**Rossi preesistenti** nella suite completa (`knowledge_*`, `life_graph`,
`iter*`, `travel_action_flow`) — confermati estranei al lavoro telefonico, mai
indagati.

**`FEATURE_STATUS.md`** — fermo al 2026-08-06. È una matrice di feature, non
una roadmap, e non è stato riallineato con questo documento.

**Fuori perimetro, per scelta** — chat libera (`D5` della vecchia roadmap):
ORA è collaborazione guidata. La regola è dell'Era 2 e non è mai cambiata.
