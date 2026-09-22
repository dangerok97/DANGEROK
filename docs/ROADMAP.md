# ORA — Roadmap canonica verso 1.0

**Questo documento è la source of truth del progetto.** Versione corrente,
prossimo sprint, dipendenze, ordine delle feature, criteri di uscita e
percorso fino al lancio si leggono qui e solo qui.

| | |
|---|---|
| **Versione corrente** | **V3.21.3e — Vita State Semantics Final Fix · verifica cloud finale pendente** |
| **Prossimo sprint** | **V3.21.4 — Cloud Foundation Final** |
| Branch operativo | `staging/cloud` |
| Ultimo checkpoint | `8855b6d` (sync cloud e consenso posizione) |
| Aggiornato | 2026-09-22 (roadmap rivista: iPhone e alpha anticipati) |

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

### V3.15.2 — Post-Call Hardening · **APERTO: essenziale prima dell’alpha, completamento V5**
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

#### Debito registrato durante V3.21 — ORA Product Experience Rebuild · **CHIUSO da V3.21.3**
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

#### V3.21.3 — ORA Product Experience Rebuild · **PASS**
**Design system.** Un'unica grammatica (`src/theme/oraSurface.ts` + `ora-ui`):
bianco caldo, blu ORA profondo per la gerarchia, un solo blu luminoso per CTA
e stato attivo, bordi da un capello, ombre appena percettibili, raggio 22.
La barra laterale è un componente solo (`SideRail`), usato dalla barra delle
tab e da `DesktopShell`: le schermate fuori da `(tabs)` — conversazione,
Conosciamoci, preparazione telefonata — avevano navigazioni diverse o nessuna.
**Home.** Composizione della reference: focus di oggi con CTA e «Perché ora?»,
Domande per te, Aggiornamenti di ORA, composer; a destra data, calendario,
prossimi appuntamenti e ORA in sintesi. «Oggi» e «Più avanti» non sono più
duplicati al centro sul desktop.
**Domande per te — bug chiuso.** Si rispondeva in chat e la domanda restava
aperta in Home: ora un messaggio nella conversazione che aveva chiesto chiude
la domanda (`answered_in_thread`), una riconciliazione chiude quelle già
risposte in passato, e una telefonata finita chiude le domande della sua chat.
**Aggiornamenti — provenienza.** Ogni riga porta COSA, DA DOVE («Appuntamento
in calendario il 18 settembre», «Me l'hai chiesto tu il …»), PERCHÉ CONTA,
STATO, COSA SERVE A TE («Non serve nulla per ora.») e un'azione. Niente è
inventato: senza fonte la riga dice che nasce dal lavoro di ORA.
**Chat.** Sul desktop ha la barra laterale, l'intestazione personale, le
scorciatoie sotto il composer e una colonna di contesto alimentata dalla
stessa risposta canonica della Home.
**Navigazione.** `open_navigation` confronta auto, mezzi e bici con i tempi
del provider, consiglia il più veloce e dice entro quando partire per il primo
impegno; la chat lo disegna come «Le migliori opzioni per te». Senza provider
di routing **non si inventa niente**: si dice perché il confronto non c'è e
restano i link alle mappe.
**Presenza.** Tre eventi canonici invece di due: `entered`, `exited`,
`returned` (finestra di otto ore), con l'isteresi di sempre. Provato dal vivo
con posizioni simulate: entrato → uscito → tornato.
**Preparazione telefonata.** Tre passi (contatto trovato · privacy e intenti ·
pronto per chiamare) con la colonna «La tua richiesta» e «Riepilogo chiamata».
Chi chiamare si legge anche dalla frase («Chiama Asia e dille che…»), che prima
lasciava la schermata senza contatto. E c'è il tasto che mancava dal V3.21.1a:
**«Chiama ora» compone davvero**, passando dalla route del prodotto.
**Conosciamoci e Documenti.** Percorso con «Quello che ORA sa già», «Cosa manca
per aiutarti meglio» e un solo prossimo passo; Documenti con tre capacità, il
riepilogo vero di ogni documento, stato come badge, Apri/Riepilogo/Azioni e
«Azioni suggerite» costruite sui documenti reali.
**Latenza della chat — misurata, non ipotizzata.** Fasi per turno nel trace:
contesto **4–18 ms**, strumenti 0–40 ms, modello **3,9–19,7 s**. Il tempo è
tutto del provider e varia di quattro volte fra due turni uguali; il prompt di
sistema pesa 58.432 caratteri (~15k token) e un confronto con un prompt ridotto
non ha dato una differenza leggibile sopra la varianza. Mitigazione fatta: al
posto di «Sto ragionando…» la chat mostra lo strumento che sta davvero girando
(«Controllo il tuo calendario…»), letto dal ciclo, mai inventato.
**Reality gate.** A: Home → Rispondi → risposta in chat → Home aggiornata
(5 → 4, la domanda sparisce). B: aggiornamento con fonte e azione. C: «Portami
a lavoro» risolve prima il luogo (nessun luogo salvato: chiede quale) —
**confronto dei tempi non dimostrabile senza provider di routing**. D: entrato
/uscito/tornato canonici. E: latenza prima/dopo sopra. F: la preparazione usa
MissionPreparation e i numeri già confermati. G: i documenti mostrano stato e
riepilogo dal backend.
**Test.** 22 prove nuove sul backend (`test_product_experience_v3213.py`) più
la regressione; nel frontend corrette tre guardie ferme a prima di Chiamate.
**Debito.** Provider di routing e luoghi salvati assenti in questo ambiente:
il modulo dei tempi non ha dati veri. Latenza della conversazione = latenza del
modello. Restano rosse due guardie del frontend precedenti a questo sprint
(px19 su `settings.tsx`, px11 sulla frase di conferma).

#### V3.21.3a — Product Experience Final Reality Gate · **PASS (3 su 4) · navigazione BLOCKED**

Quattro cose che il V3.21.3 aveva dichiarato fatte senza esserlo.

**1 · «Domande per te» non è più uno storico. · PASS**
Il legame fra le fasi di uno stesso lavoro adesso è un identificativo, non una
somiglianza di testo: `WorkRefs.preparation_id` nasce nel ciclo cognitivo
(`active_preparation_id`), viaggia con la domanda, e una fase nuova ne chiude
la precedente anche se sono nate in due conversazioni diverse. In più, a ogni
apertura della Home: una preparazione finita o sparita non aspetta più niente,
di ogni lavoro resta solo la domanda corrente, e un thread mai ripreso dopo due
giorni si lascia andare.
**Due difetti veri trovati dalle prove sul campo.** (a) `reconcile_with_threads`
guardava `updated_at` della conversazione per capire se «era andata avanti» —
ma quel campo si muove anche quando a parlare è ORA, un istante prima che la
domanda venga scritta: ogni riga sembrava viva e non si chiudeva mai niente.
Adesso si guarda l'ultimo messaggio **della persona**. Sui dati veri: sette
domande aperte, due chiuse subito perché nessuno aveva più ripreso quelle chat.
(b) La scorciatoia del punto 4 costruiva una decisione senza
`uncertainty.blocking`: la domanda si leggeva in chat e in Home non compariva.
**Reality gate** (account nuovo, conversazione unica, screenshot):
fase 0 → 0 domande · fase 1 «chiama Giulia Test» → **1** · fase 2 numero dato →
**0** · fase 3 conferma → **1** (solo quella corrente) · fase 4 conclusione →
**0**. Mai più di una, zero alla fine.

**2 · Gli aggiornamenti dicono da dove vengono. · PASS**
Un vocabolario solo (`agent/models.py::DA_DOVE`, `how_we_say_the_source`) per
tutte e quattro le sorgenti che finiscono in «Aggiornamenti di ORA»: prima solo
il lavoro dell'agente portava la provenienza, i suggerimenti no.
«Nata dal lavoro di ORA» era una perifrasi per «non lo so»: adesso una fonte
che non si ricostruisce si dichiara — **«originale non disponibile»**.
E l'articolo non promette più quello che ORA non sa: senza un riferimento a cui
agganciarsi, «Ritiro **del** certificato» diventa «Ritiro **di un**
certificato» più «Non riesco ancora a capire di quale certificato si tratti».
Si tocca solo la preposizione, mai il sostantivo.
**In app**: «A che ora e dove vedrai Giulia giovedì?» · «Fonte: una deduzione
mia da quello che so della tua vita del 20 settembre».

**3 · Navigazione intelligente · `INTELLIGENT NAVIGATION REAL DATA — BLOCKED BY ROUTING PROVIDER`**
Censimento, disegno iOS-first e cosa serve esattamente: `docs/NAVIGAZIONE_INTELLIGENTE.md`.
Il confronto fra i modi, il consiglio del più veloce e l'orario di partenza dal
primo impegno **esistono e sono collegati**; manca la fonte dei tempi
(`ROUTING_PROVIDER`/`ROUTING_API_KEY` non configurate). La strada consigliata è
MapKit sul telefono — nessun costo dentro un'app iOS firmata. Non si dichiara
PASS e non si accende niente a pagamento senza approvazione.

**4 · Latenza della conversazione · misurata e ridotta di una generazione**
Benchmark controllato, stessa richiesta, ordine di produzione: **mediana 3,31 s
· p90 6,06 s · 8 su 8**. Per provider (serie separate): gemini2 5,94/7,49 ·
mistral 5,88/8,14 · groq 10,06/11,84 · openai 16,31/16,60. Gemini è a credito
esaurito (402) e costa 2,5 s solo al primo turno, poi va in panchina.
**Il prompt non è la leva**: ridurlo da 58.432 a 6.000 caratteri non ha dato
nessun miglioramento leggibile sopra la varianza.
**La leva era strutturale**: certi strumenti restituiscono già la frase esatta
che la persona leggerà, e quella frase vince comunque su quello che il modello
scrive dopo — la generazione successiva veniva prodotta, pagata e buttata.
Adesso la decisione si costruisce da quella frase e passa dalla validazione
come tutte le altre: **una generazione in meno per turno**, cioè 3-6 secondi su
ogni preparazione di telefonata. Turni del gate: 5,1 · 8,8 · 23,3 · 7,6 · 6,4 s.
Un errore interno resta quello che era: si fallisce in fretta, non si maschera
con un altro provider **e non si mette in panchina nessuno** — è un errore
nostro, e punire un provider sano lo nasconderebbe soltanto. Ci avevo provato,
partendo da una misura che si è poi rivelata un artefatto del banco di prova
(un file `google.py` nello scratchpad che oscurava il pacchetto vero); la
prova `test_a_our_own_mistake_does_not_bench_a_healthy_provider` ha fermato la
modifica, ed è stata revocata.

**5 · Un difetto trovato per strada, e chiuso.**
«Chiama Giulia Test», nessuna Giulia in rubrica, e ORA proponeva **«Francesco
Test»** — stesso cognome, altra persona — come se l'avesse trovata: la conferma
veniva chiesta su una premessa falsa. Adesso, quando il nome trovato somiglia
ma non coincide, ORA lo dice: «Non ho un numero per Giulia Test. Quello che ci
somiglia di più è …». Zero parole in comune resta un ritrovamento legittimo
(«la mia ragazza» → Giulia), e lì non c'è niente da correggere.

**Prove.** 14 nuove (`test_final_reality_gate_v3213a.py`) più la regressione.
Il finto database ha imparato `$ne` e la proiezione: senza, una scrittura
«tutte quelle del lavoro tranne questa» chiudeva anche la domanda appena nata —
un difetto del doppio, non del codice vero.

**Debito.** Le domande aperte prima di questo sprint non hanno un
identificativo di lavoro: si chiudono per abbandono dopo due giorni, non per
supersessione. Fra conversazioni diverse, due domande sulla stessa missione si
legano solo se esiste un oggetto canonico (preparazione, piano, situazione).

#### V3.21.3b — Home Navigation & Action Integrity · **PASS**

**Cinque link, una sola pagina.** «Vedi agenda», «Vedi tutto», «N da
rispondere», «N aggiornamenti» e «Apri dettagli» finivano tutti su «Situazione
completa» — o non facevano niente. Sono cinque domande diverse e adesso hanno
cinque superfici: `/agenda` (quando succedono le cose), `/ora-sintesi` (come
stanno le cose, le stesse quattro voci del widget con dentro gli elementi
veri), `/domande` (solo quelle aperte adesso, con risposta che parte da lì),
`/aggiornamenti` (l'elenco) e `/aggiornamento/{id}` (il contratto del
V3.21.3a per esteso: cosa, da dove viene, perché conta, cosa sto facendo, cosa
serve a te, prossimo passo).
Le pagine leggono gli stessi dati canonici dei widget — `elencoAggiornamenti`
è una funzione sola usata da Home, elenco e dettaglio — così i numeri non
possono scollarsi: Home dice «4 da rispondere», la pagina ne mostra 4.

**Agenda.** Nuova porta `/api/agenda`, che legge gli stessi nodi `event` del
riepilogo giornaliero: niente seconda verità sul calendario. Tiene i giorni
vuoti («Niente in programma») perché «giovedì sei libero» è un'informazione, e
dice da dove viene ogni appuntamento (Google Calendar, Calendario di Apple,
aggiunto qui) e che cosa c'entra ORA, quando c'entra davvero.

**Meteo, vero.** Al posto del bottone «Perché ora?» nell'intestazione c'è il
tempo che fa — nella colonna centrale accanto al saluto, come nella reference,
non appoggiato alla colonna del calendario. I dati arrivano da Open-Meteo
(nessuna chiave, nessun costo, spegnibile con `WEATHER_PROVIDER=none`) e il
punto da cui si guarda è la **posizione vera del telefono**, la stessa che
alimenta la presenza; senza posizione si dice «non so ancora dove sei», senza
provider «Meteo non disponibile». Nessun grado inventato, mai.
La riga parla italiano: «Mattina serena», «Pomeriggio nuvoloso», «Sera di
pioggia» — gli aggettivi si accordano con il momento della giornata.
Il modulo si apre: `/meteo` mostra percepiti, umidità, vento, pioggia, alba e
tramonto, le prossime dodici ore e i prossimi cinque giorni.
**«Perché ora?» resta dentro la card del focus**, dov'è la cosa che spiega.

**La barra laterale.** Sotto «Una vita più semplice, insieme.» c'erano due
rettangoli arrotondati a fare da colline. Adesso c'è un'immagine vera —
`assets/images/rail-calm.png`, creste in foschia, generata da
`frontend/scripts/make-rail-image.py` e versionata con il resto: nessun URL
remoto. L'immagine riempie la card e il testo le sta sopra, appoggiato al
cielo, come nella reference. La barra ci sta tutta senza scorrimento e la card
non si sovrappone più a «Documenti» nemmeno a 700 px di altezza. Essendo il
componente condiviso, vale per Home, Vita, ORA, Chiamate, Attività, Documenti.

**Nessuna CTA morta.** Audit dell'intera Home, cliccando davvero: Continua →
workspace dell'obiettivo, «Perché ora?» → spiegazione inline, «…» → menu,
Rispondi → conversazione, calendario ‹ › e Oggi → il mese cambia, composer →
scrive. Nove CTA su nove vive, più le sei di navigazione. «Apri dettagli»
compare solo quando c'è un dettaglio da aprire, e la freccia del meteo solo
quando il meteo si può aprire.

**Prove.** 18 nuove sul backend (`test_home_navigation_v3213b.py`: meteo
acceso/spento, accordo grammaticale, posizione dal GPS, agenda con giorni
vuoti, ore e fonte) più la guardia del frontend `test:v3213b`, che tiene ferme
le cinque destinazioni distinte, il meteo cliccabile e l'immagine della barra.
Reality gate dall'app vera: sei percorsi, sei pagine diverse, più indietro,
refresh e rotta diretta.

**Debito.** `/situazione` resta dov'è per i suoi usi; non è più la
destinazione di nessuno dei link della Home. La pagina del meteo non ha ancora
le allerte, e l'agenda si ferma a sette giorni (quattordici dalla porta).

#### V3.21.3c — Vita / Conosciamoci Flow Integrity · **FINAL PASS**

**Una sola superficie.** La voce «Vita» apriva `/contesti` — un'altra
grammatica per la stessa domanda — mentre il percorso approvato viveva a
`/life-setup` e ci si arrivava solo al primo accesso: due esperienze
concorrenti per la stessa persona. Adesso Vita apre `/vita`, che è
«Conosciamoci». `/contesti` resta raggiungibile da un link ma non è la
destinazione di nessuna voce di menu, e i suoi dati non sono stati buttati: le
situazioni in corso vivono in fondo alla pagina, sotto **«In questo periodo»**,
dalla stessa mappa della vita di prima.

**Il difetto vero: «Continua con Casa» non continuava.** Casa era al 92% e il
bottone non apriva niente; Studio al 67% aveva tre cose mancanti e nessuna
raggiungibile. Sotto c'erano due vocabolari: le **domande guidate** (che sanno
come si chiede una cosa) e gli **obiettivi di conoscenza** (da cui nasce la
percentuale). Quello che stava solo nel secondo non aveva alcun modo di essere
risposto. `life_profile/gaps.py` costruisce adesso la domanda dall'obiettivo
stesso — l'etichetta che la persona legge fra i «cosa manca» diventa la
richiesta, e la risposta si scrive **sotto lo stesso riferimento che la
percentuale conta**. Quando l'obiettivo dice che un documento è la strada
migliore, la domanda nasce già come richiesta di documento.

**Le cose che mancano sono porte.** Ogni voce di «cosa manca» apre quella
domanda lì (`go-to-area` con `ref`, e l'area la decide il riferimento, così un
link non manda nessuno nella stanza sbagliata). Le aree si scelgono dal
percorso a sinistra e dalla colonna a destra: prima erano disegni.

**Prima il riepilogo, poi la domanda**, come nella reference. Chi apre un'area
vede quello che ORA sa già — **con i fatti, non con i conteggi**: «Tipo:
Università», «Fase: Verso la fine», con le parole dell'opzione che la persona
aveva scelto, non l'identificativo di magazzino — poi cosa manca, poi
«Prossimo passo consigliato» con **«Continua con X»** e **«Lo faccio più
tardi»**. Al primo giro si va dritti alla domanda: non c'è ancora niente da
riepilogare.

**«Entra in ORA» è sparito**: non voleva dire niente, la persona è già dentro.
**«Perché queste domande?»** era un bordo che sembrava un bottone: adesso si
apre e dice a che cosa servono le risposte — e ogni area dice la sua
(`LifeArea.purpose`), come nella reference.

**Riprendere è riprendere.** `?area=casa` era un parametro decorativo: adesso
apre quell'area e la sua prima cosa mancante, una volta sola, poi la persona è
libera di muoversi.

**Reality gate, dall'app vera.** A: barra → `/vita`, con «Conosciamoci» e
«PROFILO VITA». B: «Continua con Famiglia e relazioni» → prima cosa mancante
(«Nucleo familiare»). C: risposta → **52% → 70%** per l'area e **84% → 86%**
in totale, dalla stessa sorgente che alimenta la colonna di destra. D: «Lo
faccio più tardi» → torna alla Home, percentuale invariata. E: rientro con
`?resume=1&area=studio` → Studio aperto sulla sua prima cosa mancante. F:
click sulla colonna di destra → stesso pannello centrale.

**Prove.** 12 nuove sul backend (`test_vita_flow_v3213c.py`) più la guardia
`test:v3213c`. Due prove esistenti scadevano col calendario — date scritte a
mano di tre giorni prima, che la regola dell'abbandono chiudeva — e adesso
contano i momenti da adesso. La guardia che vieta a un client di dichiarare
una percentuale è stata estesa a `ref`, che è una scelta e non un numero.

**Debito.** La reference ha in alto a destra una fotografia editoriale: quel
file non è nel repository e non lo si inventa — resta la frase scritta a mano,
e la foto è una decisione di contenuto da prendere. `/contesti` esiste ancora
come rotta: non è più concorrente, ma prima o poi va assorbita o archiviata.

#### V3.21.3d — Vita Visual & Semantic Finalization · **PASS**

**Un fatto di lavoro presentato come fatto di famiglia.** Sotto «Famiglia e
relazioni» si leggeva «Di chi ti prendi cura: **nella Guardia di Finanza**», e
quella riga faceva anche salire la percentuale dell'area. Il valore era vero;
la cosa che diceva, no — e non è un difetto di stringhe, quindi non si è
corretto con una stringa.

Le cause erano due, entrambe generali. **Prima**: il nucleo «responsabilità»
del Minimum Life Context si lascia soddisfare da prove prese da tutta la vita
— `lavoro.ruolo`, `studio.active`, `casa.owned` — perché per il suo scopo va
bene così; ma usato come obiettivo di un'area rispondeva alla domanda
sbagliata. Adesso le prove di un fondamento vengono filtrate sull'area a cui è
attaccato. **Seconda**: la presentazione non chiedeva mai se un fatto
appartenesse all'area in cui stava per finire. Adesso lo chiede
(`human.appartiene_all_area`): un riferimento appartiene all'area che possiede
il suo dominio, o a quella con cui ha una relazione canonica scritta; nel
dubbio **non si mostra**. E un riferimento trasversale che ripete parola per
parola un fatto di un'altra area è un'eco: non si mostra e non conta.

**Le parole, in un posto solo.** `life_profile/human.py` tiene etichette,
frasi e valori: nessun campo interno arriva sotto gli occhi di qualcuno, e
`true`, `null`, `unknown`, `doc_bd558d…` non compaiono mai. «Quello che ORA sa
già» adesso si legge come memoria — *Lavori nella Guardia di Finanza*, *Hai
un'auto*, *Vivi in affitto*, *Non hai figli*, *Hai caricato una polizza* —
invece che come un modulo compilato. Le opzioni si dicono con l'etichetta che
la persona aveva scelto, non con il loro identificativo.

**Audit di tutte e dieci le aree**, sul profilo vero: ogni riga mostrata
appartiene alla sua area, nessun codice interno, nessun valore grezzo.

**Percentuali.** Il conto non è cambiato ed è spiegabile: i pesi di Famiglia
sono 0,9 + 1,0 + 0,65 + 0,6 + 0,5 = 3,65, e rispondere a «nucleo familiare»
(0,65) porta 1,9/3,65 = 52% a 2,55/3,65 = 70% — esattamente il salto
osservato. Quello che è cambiato è **cosa conta**: l'eco dal lavoro non fa più
salire la famiglia. La percentuale nasce solo nel backend; la schermata la
mostra e basta, e una guardia lo tiene fermo.

**Un difetto trovato per strada.** Cliccando un'area già completa — Lavoro al
100% — il pannello mostrava Studio: la scelta veniva scartata in silenzio.
Adesso, finito il primo giro, un'area scelta resta aperta anche se non ha più
niente da chiedere.

**La testata editoriale.** Due tentativi di *disegnarla* sono finiti male —
una sfumatura beige, poi oggetti con sfumature e ombre — e sono raccontati
dentro `scripts/make-vita-header.py` perché nessuno li rifaccia: la
differenza fra una fotografia e un disegno non è la cura dei contorni, ed è
inutile inseguirla con Pillow. L'asset adesso **si ritaglia dalla reference
approvata** (`Vita - conosciamoci target.png`), che è l'immagine che il
prodotto ha già scelto: pianta, portapenne, libri, lampada, luce calda. Il
ritaglio è in frazioni, così regge una riesportazione; l'uscita
(`assets/images/vita-header.png`) è versionata, la reference no — è un file di
lavoro, e lo script dice dove cercarlo. La fascia occupa tutta l'intestazione,
con la frase manoscritta scritta dall'interfaccia sulla sua parete vuota:
dentro l'immagine non si potrebbe più correggere.

**Modifica.** Accanto a «Quello che ORA sa già» c'è «Modifica», come nella
reference: riapre quel fatto e lo richiede. La risposta riscrive lo stesso
riferimento — nessuna seconda copia, niente da riconciliare dopo.

**Prove.** 15 nuove (`test_vita_semantics_v3213d.py`) più la guardia
`test:v3213d`; aggiornate due prove del V3.3 e del V3.21.3c che fissavano la
forma vecchia.

**Debito.** La testata è un'illustrazione, non una fotografia: la scena della
reference (still life fotografico) resta una decisione di contenuto. Le
etichette senza una frase dedicata restano nella forma «Nome: valore».
`/contesti` esiste ancora come rotta.

#### V3.21.3e — Vita State Semantics Final Fix · **verifica cloud finale pendente**

**Famiglia al 100%, cliccata, diceva «In corso».** E Lavoro al 100% pure, con
sotto «Continua con Lavoro» e «Lo faccio più tardi»: un invito a continuare
una cosa finita e il permesso di rimandare il niente. Il V3.21.3d **resta
valido** — quello che ha sistemato è sistemato; qui si chiude la semantica
degli stati, che era l'ultima cosa rimasta a smentirsi da sola.

**Prima causa: la selezione riscriveva lo stato.** In `GuidedSetupScreen.tsx`
la funzione che dice come sta un'area cominciava con
`if (area.current) return 'In corso'`, e un chip scritto a mano ripeteva «In
corso» sotto il titolo. Così un clic — che è evidenza visiva e nient'altro —
diventava un'informazione sulla vita di qualcuno. Adesso le tre cose sono
separate e lo restano anche nel payload: `selected` è dove stai guardando,
`in_progress` è dove c'è davvero una domanda aperta adesso, `percent`/`state`
sono quello che ORA sa e non dipendono da nessuna delle due. Al 100% un'area
dice «Conosciuta», selezionata o no. Aprire una qualsiasi delle dieci aree non
cambia una virgola dello stato delle altre nove, e una prova lo verifica area
per area.

**Seconda causa: «la prossima area» era l'ordine del menu.** Il client faceva
`areas.find(a => a.percent < 100)` e ci scriveva accanto «Casa è quasi
completa» — una frase che nessuno aveva verificato. La graduatoria adesso sta
in un posto solo, `life_profile/recommend.py`, ed è deterministica: un'area
quasi completa a cui manca una cosa sola (il passo più corto) · poi un'area a
cui manca una cosa sola ovunque sia · poi un'area di cui ORA non sa ancora
niente · infine quella dove resta più peso da imparare; a parità vince
l'ordine del percorso. Torna anche un `reason_code` che le prove controllano,
mentre l'interfaccia mostra solo la frase. Sul profilo vero le due
regole vecchie **non erano nemmeno d'accordo fra loro**: il client diceva Casa
(prima della lista), il backend diceva Studio (più peso da imparare) — due
consigli diversi nella stessa schermata, ed era esattamente il problema. La
regola nuova dice **Casa**, come il client, ma adesso è vera: 92%, un solo
buco. E `_suggest` della completezza delega alla stessa funzione, così una
seconda classifica non può più nascere.

**Un'area completa si dichiara finita e tace.** Niente «Continua con», niente
«Lo faccio più tardi», niente «Cosa manca»: solo *«Di Lavoro so già tutto
quello che mi serve.»* Sotto, staccato da una riga e un po' d'aria perché
parla di un'altra area, «Prossima area consigliata» con il motivo e la sua
CTA.

**Via il doppione.** Dentro il pannello di un'area c'era un riepilogo globale
— «ORA ha un buon punto di partenza», la percentuale, «Prossimo passo
consigliato» — che ripeteva «Profilo Vita» due centimetri più su. Un secondo
posto dove leggere lo stesso numero è un secondo posto dove può diventare
diverso. Il pannello adesso risponde a una domanda per volta: cosa ORA sa ·
cosa manca · come sta quest'area · dove andare dopo.

**Un difetto trovato dal gate.** Salute era al 52% con una cosa mancante che
non si poteva chiedere: `salute.visita` era stato **rifiutato**, ma il flusso
guidato scriveva i rifiuti nel proprio meta e la proiezione della completezza
li legge da `refused_keys`. I due non si parlavano, e quella cosa restava per
sempre fra i «cosa manca» con una pastiglia che non apriva niente. Adesso il
flusso scrive in tutti e due e la proiezione li unisce, anche all'indietro. Ne
esce un terzo stato, che è diverso sia da «completa» sia da «da fare»: *«Di
Salute e benessere non ho altro da chiederti. Quello che manca me l'hai
lasciato da parte, e va bene così.»* La percentuale **non** sale: un rifiuto
dice qualcosa sulla conversazione, non sulla vita.

**Gate sull'app vera** (1672×941, profilo reale): Famiglia 100% selezionata ·
Lavoro 100% selezionato · Mobilità 86% · Salute 52% · la colonna delle dieci
aree · «Continua con Mobilità» che apre davvero la domanda del libretto. Le
dieci righe della colonna coincidono con il backend su percentuale, stato e
«in corso».

**Prove.** 20 nuove (`test_vita_state_semantics_v3213e.py`) più la guardia
`test:v3213e`, che fissano tutte e sei le proibizioni: selezione che diventa
stato · CTA di rinvio su un'area completa · «continua con sé stessa» su
un'area completa · riepilogo globale duplicato nel pannello · consiglio senza
`reason_code` · percentuale o stato divergenti fra pannello e colonna.

**Debito.** Un obiettivo di Finanze ha il riferimento di Patrimonio
(`patrimonio.risparmi`): è una scelta del catalogo, non un difetto di stato,
ma è un punto dove due aree parlano della stessa cosa e Patrimonio è al 100%
senza di essa. `/contesti` esiste ancora come rotta. Le etichette senza una
frase dedicata restano nella forma «Nome: valore».

**Recupero cloud, 22 settembre 2026.** Patch locale di Claude recuperata senza
conflitti sopra `staging/cloud` (`3e3ffe1`). La revisione ha corretto un caso
non coperto dal gate originale: anche una domanda preparata ma nascosta
faceva risultare «In corso» un'area incompleta soltanto selezionata.
`start_question` avvia ora esplicitamente il flusso, salvato nella sessione;
la selezione ordinaria torna al riepilogo. Rifiuti uniti anche nella scelta
delle domande, e aree senza domande aperte escluse prima della preferenza
per un'area già iniziata. 97 test backend mirati passati localmente
(`--noconftest`: servizi isolati, nessun Mongo reale), TypeScript e guardie
Vita 3c/3d/3e verdi, export Expo web riuscito. CI estesa alle suite Vita.
Passa anche un test Playwright con profilo sintetico e API intercettate:
selezione, continua, reload e aree complete/rifiutate.
Gli screenshot A–F e `esiti.json` forniti descrivono la patch originale;
`errore.txt` conserva anche un timeout Playwright, senza una cronologia che
permetta di attribuirlo allo stesso tentativo. Non sono una verifica del
nuovo deploy: la conferma sul profilo cloud resta pendente.

### V3.21.4 — Cloud Foundation Final · IN CORSO
**Obiettivo** — il cloud sostituisce il localhost: spegnendo il PC le funzioni core continuano a funzionare.

**Evidenze già disponibili (22 settembre)** — Google Login Railway confermato funzionante dall'utente; patch Vita recuperata; correzioni Calendar/Gmail first sync, polling e consenso browser pubblicate (`8855b6d`). Runtime automatico avviato, letture ripetute senza errori nei log; meteo verificato con posizione sintetica. Questo non dimostra ancora appuntamento/email/posizione sul profilo reale.

**Gate da chiudere**
- Verifica finale V3.21.3e sul profilo Railway: selezione, domande, rifiuti, reload, CTA e percentuali coerenti.
- Login e OAuth Calendar/Gmail con callback cloud; prima lettura e modifica successiva visibili in ORA, stato ultimo sync ed errori comprensibili.
- Consenso posizione da Impostazioni e Meteo, revoca/negazione, aggiornamento del meteo sul dispositivo reale.
- Frontend/backend/Mongo stabili, documenti su storage persistente (mai affidarsi a `/tmp`); upload e lettura dopo redeploy.
- Telefonia Railway senza PC o Cloudflare. Il precedente PASS di capability (`carrier/live/public`, `gemini_live`) va distinto dal gate finale di telefonata reale V3.22.
- Segreti runtime su Railway, controllo esposizione repository e vecchi `backend/data`; nessuna cancellazione o riscrittura di storia implicita.
- Sessioni/JWT, health e capability status verificati; nessun servizio dichiarato funzionante solo perché configurato.

**Exit** — funzioni core dimostrate con PC spento; prove e limiti registrati. Nessuna nuova architettura telefonica.

### V3.22 — Call UX Final · PIANIFICATO
**Obiettivo** — preparo chiamata → autorizzo → ORA chiama → seguo stato → leggo esito → eventuale decisione → applicazione → storico.
**Perimetro** — prodotto e gestione errori; preservare Gemini Live/Vonage salvo difetti dimostrati.
**Exit** — una persona senza conoscenze tecniche completa il percorso; telefonate reali dal cloud e recupero essenziale dimostrati, senza azioni perse o duplicate.
**Dipendenze** — V3.21.4; parte essenziale del debito V3.15.2. Chiude l'arco telefonico.

### V3.23 — iPhone Reality Gate · PIANIFICATO
**Obiettivo** — ORA su un iPhone vero tramite Expo/EAS/TestFlight, usando Railway; non una riscrittura nativa completa.
**Gate** — login, Home, Vita, conversazione, push, posizione, contatti, telefonia, permessi iOS, SecureStore, background/resume e kill/relaunch.
**Exit** — build installata e flussi verificati sul dispositivo; limiti iOS espliciti e nessuna dipendenza dal PC. Account e firma Apple necessari vanno verificati, non presunti disponibili.

---

## Parte III — Da V4 a ORA 1.0

Fasi **PIANIFICATE**. L'alpha è anticipata a V4.1; V11 e V12 sostituiscono le precedenti tappe alpha/beta, e la vecchia V13 confluisce in V12.

| Versione | Obiettivo | Exit criteria |
|---|---|---|
| **V4 — Proactive ORA V1** | Un solo caso reale: variazione calendario oppure rischio ritardo da calendario/posizione/traffico | Segnale → impatto → piano → autorità → azione o domanda → verifica → informazione; utilità dimostrata |
| **V4.1 — Closed Alpha** | 3–5 persone provano «cosa conta oggi», «arrivare al momento giusto», «occupatene tu» | Beneficio osservabile rispetto agli strumenti manuali; problemi e risultati registrati, gate minimi superati |
| **V5 — Long-Running ORA** | Commissioni di ore/giorni; completare V3.15.2 | Obiettivo sopravvive a riavvio, attesa, needs-user, provider down, retry e conflitto |
| **V6 — Learning & Personal Adaptation** | Abitudini, preferenze, routine, comunicazione e soglie | Ogni apprendimento è spiegabile, correggibile e reversibile |
| **V7 — Unified ORA Intelligence** | Ridurre i motori: Context/Sensors → Reasoning → Plan → Authority → Capability → Verification → Presentation | Contesto e decisioni coerenti; meno motori, non uno stack parallelo |
| **V8 — Mobile & System Presence** | Raffinare iPhone già operativo: push, MapKit, geofencing, Contacts/EventKit, share sheet, deep link; Siri/widget dove utili | Valore quotidiano su device e comportamento background verificato |
| **V9 — Privacy / Safety / Trust** | Audit completo, provenance, minimizzazione, retention, export/cancellazione, revoca e azioni | Garanzie dimostrate prima di ampliare gli utenti |
| **V10 — Production Reliability** | Monitoring, alert, rate limit, CI, rollback, capability health e incident recovery | Backup con restore provato e failure/recovery reali; servizio senza supervisione continua |
| **V11 — Private Beta** | Più utenti senza assistenza continua | Affidabilità e utilità confermate oltre l'alpha |
| **V12 — Public Beta / Release Candidate** | Onboarding, pricing se previsto, compliance store/privacy, crash/latency/error budget | Nessun difetto bloccante e criteri di rilascio verificati |
| **ORA 1.0** | Lancio | Ciclo completo stabile nell'uso quotidiano |

**Gate obbligatori prima di V4.1** — isolamento dati tra utenti, permessi e revoca accessi, gestione segreti, storage persistente, backup/ripristino provato, errori osservabili e recovery essenziale/idempotenza delle azioni. V9–V10 completano la maturità, non autorizzano a rinviare queste basi.

**Ordine immediato** — V3.21.3e reality gate → V3.21.4 → V3.22 → V3.23 → V4 → V4.1. Google Login già confermato: regressione da controllare, non blocker noto.

**Fuori dal percorso immediato** — GPT-Live, WhatsApp, banking e nuovi engine. Consolidare le capacità esistenti prima di ampliare il perimetro.

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
| **Reconciliation robusta** | riesce, non ritenta | Recovery essenziale prima V4.1; completamento V5 |
| **Proactivity utile** | esiste, non misurata | V4 |
| **Recovery / idempotenza** | idempotenza ✅, recovery ✗ | Prima V4.1; V5 · V10 |
| **Mobile completo** | gate device aperto | V3.23 prima prova; V8 integrazione profonda |
| **Privacy / audit** | gate minimi aperti | Minimi prima V4.1; audit completo V9 |
| **Production infra** | cloud attivo, consolidamento aperto | V3.21.4; minimi prima V4.1; maturità V10 |
| **Alpha / Beta superate** | no | V4.1 · V11 · V12 |

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
