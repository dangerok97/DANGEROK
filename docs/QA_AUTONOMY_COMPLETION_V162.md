# 12 ottobre 2026 — v162, esiti848 e riparazione dei supporti di test

CI848 completa alle17:06:36Z, attempt1, nessun rerun:6 workflow (2 successi,4 failure),16 job (10 successi,4 failure,2 saltati). Push checkout848a379; PR checkout reale e7ddc35, tree2ffa79b, parent c907ca2+848. I25 file differenti appartengono a Vision/WhatsApp; i18 percorsi critici confrontati sono identici.

Per entrambi i backend generali lo step42 termina877 PASS/1 FAIL su test_scripted_first_cycle_uses_real_worker_sources_and_a_future_check, assert full_contexts. Le invocazioni precedenti sommano1424 PASS push e1436 PASS PR, con8 skip storici ciascuno; non sono conteggi deduplicati. Il modulo handoff42, successivo nell'ordine, non è raggiunto; CLI9, Mongo6 e provenance3 non eseguiti. I backend Situation dedicati completano tre selezioni111+62+116 PASS ciascuno.

I due job frontend completano tsc e34 casi:20 presenter,9 hook,5 render; anche prebuild/export iOS passano. Situation presentation si ferma invece all'assert statico riga403 sul vecchio nome followup; il successivo step presenter di quel workflow non parte. Mobile web40 PASS,20 Chromium e20 WebKit. Phone cloud294 PASS per job, bounded phone7 PASS. Secret scan18910 oggetti push e18917 PR:0 pattern e0 percorsi sensibili.

La causa scripted è ricostruita dai sorgenti848: il solo CREATE raw del fake omette source_refs e ripete l'omissione durante la riparazione, quindi non entra nel worker. Aggiunto esclusivamente source_refs:[]. Nessuna modifica al vero manager, all'oracolo, all'assert full_contexts o alle soglie. Audit di20 script e20 moduli successivi al punto di arresto: altre fixture raw positive complete; negativi intenzionali e typed preservati.

L'assert ora14 mantiene l'obbligo del label/timestamp persistito usando verifiedFollowup. Verifica V8 dell'intero guard con15 sorgenti esatti: baseline fallisce alla118ª asserzione, candidato130 PASS. Gli adattatori fs/assert e i corpi reali dei due helper non equivalgono a una nuova esecuzione Node. Pytest e Node della revisione corretta restano NOT_RUN al congelamento.

Preservati14 log848:8.418.238 byte originali;8.418.634 byte pubblicati. Tre copie hanno12 sole redazioni di contatti pubblici npm, con hash originali conservati; le altre11 sono byte-identiche. Nessun live848 con CI negativa, nessuna prova nativa o accettazione autonoma. [CI848 e log](evidence/autonomy_v162_ci_2026-10-12_848a379_failure.json) · [Riparazione esatta](evidence/autonomy_v162_scripted_context_and_guard_repair_2026-10-12.json).

---

# 12 ottobre 2026 — v162, regressioni f1 e tre riparazioni ai test

CI f1 completa, negativa, senza rerun:6 workflow/16 job,8 failure e2 job saltati. Entrambi i backend:156 PASS/1 FAIL nello step della fixture v84 priva di location_label. Le21 invocazioni raggiunte sommano1158 PASS push e1170 PASS PR,1 FAIL e8 skip storici ciascuno; non sono casi deduplicati né il gruppo v162. Modulo42, gruppo1359, CLI9, riavvioMongo6 e guard successivi non raggiunti.

Frontend Node realmente eseguito:32 PASS/2 FAIL per job,20 presenter e5 render tutti verdi,7 hook verdi. Le prime letture di successo/errore risultavano ancora nel precedente snapshot dopo due soli microtask. Il harness attende ora un turno event loop Node; nessuna asserzione rimossa. Il guard statico fallito cercava il precedente nome followup: ora verifica verifiedFollowup e conserva il vincolo sul timestamp persistito.

La fixture aggiunge soltanto lo sconosciuto esplicito; un controllo statico dei26 moduli del gate Situation ha individuato quattro CREATE raw alla governance, con gli altri tre già completi. Non è una scansione di tutti i test del repository. Le prove del codice corretto restano NOT_RUN al congelamento; la diagnosi V8 sulle Promise non è una nuova esecuzione Node o React.

Il nuovo candidato contiene solo questi tre ritocchi ai test, documentazione ed evidenze; runtime, workflow e oracle live sono identici a f1. Conservati14 log, conteggi, checkouts separati, hash originali e redazioni limitate ai contatti pubblici npm.

[Evidenze della CI f1](evidence/autonomy_v162_ci_2026-10-12_f1cec19_failure.json) · [Correzione dei tre test](evidence/autonomy_v162_ci_fixture_repairs_2026-10-12.json).

---

# 12 ottobre 2026 — v162, regressioni del candidato dopo641

Le nuove prove backend coprono sette combinazioni di chiavi CREATE omesse, sconosciuti espliciti e modello già tipizzato, quattro operazioni non-create, focus valido/nullo e cinque tipi o lunghezze invalidi. Due prove del loop verificano la riparazione preesistente con una sola creazione/programmazione e il caso ancora invalido senza effetti di dominio. Il test positivo rilegge source_refs dal record effettivo con id e owner; non richiede un campo assente nell'ack pubblico.

Sono22 nuovi casi,42 totali nel modulo; le74 asserzioni dei20 casi precedenti restano conservate dopo le sole aggiunte di import e source_refs esplicito. Le tre fixture legacy aggiungono esclusivamente valori sconosciuti già impliciti. Le verifiche statiche e di sorgente non sostituiscono pytest: nessuna esecuzione Python o TypeScript locale è dichiarata a executor offline.

Le regressioni frontend dichiarano20 casi presenter e14 hook/render: errore della fonte in uso, errore irrilevante dell'altra fonte, prima lettura fallita, recupero, cancellazione letta, risposte superate e cambio owner. Le16 prove presenter precedenti sono un prefisso byte-identico del file aggiornato. L'autore ha eseguito in V8 i corpi JavaScript reali di20 presenter e9 callback del hook:29 PASS; sulla base641,16 PASS e13 FAIL. Restano da eseguire la transpilation Node/TypeScript e i5 casi di render. Il mock dello scheduling React non prova un'esecuzione React/browser. Un dato operativo rimasto in memoria non deve essere presentato come attuale dopo il fallimento noto della sua rilettura. Il comando del gate Frontend TypeScript in ci.yml seleziona ora esplicitamente anche presence/temporaryMemoryFreshness.test.cjs, dopo l'npm ci già esistente. Il workflow Situation senza dipendenze installate continua a eseguire il solo situationOutcome.test.ts. Nessun nuovo job o dipendenza; l'indice lega comandi, file e workflow.

Non sono introdotti nuovi polling o gate di modello, né rilassati gli oracoli live. La completezza del CREATE permette comunque null espliciti; non prova la correttezza semantica. La prosa finale e le prove native restano aperte.

[Contesto, visibilità e verifiche del candidato](evidence/autonomy_v162_context_and_visibility_repair_2026-10-12.json). Gli esiti originali641 restano preservati nel blocco storico seguente.

---

# 12 ottobre 2026 — v162, esiti verificati641

La CI della revisione641 conclude5 workflow,14 job e tutti i relativi step con successo, attempt1. Per ciascun backend:1.337 PASS v162 senza skip, inclusi i20 casi handoff; CLI9/9 senza modello/HTTP/effetti; visibilità3 PASS, Mongo con riavvio6 PASS, provenance3 PASS. Le due selezioni legacy conservano3 e5 skip. Browser40/40,20 Chromium e20 WebKit; nessuna prova nativa. Il merge PR reale è4958ee9, con base9063c41 e tree diverso da641; la vecchia base6e619cf nei metadati API non sostituisce i parent effettivi.

Il live sullo stesso641 produce due FAIL completi. Situation:4 chiamate logiche,10 HTTP modello e1 meteo Open-Meteo. L’errore `DECLARATION_PLACE_OR_START_NOT_PRESERVED` è qui dovuto al luogo; started_at è preservato. Seconda programmazione con ID reale riuscita, dopo rifiuto dell’ID inventato. Il testo finale usa18:00 come limite per il ritiro e propone05:00–07:00 senza assessment. Meteo fino alle05:00, previsione0% elevata a certezza. Worker, monitoraggio, controllo futuro, azione utile e dispositivo restano `not_run`; cancellazione sintetica PASS.

Memory:4 chiamate logiche e7 HTTP. `UNFINISHED_WORK_LOST` corrisponde qui a `ask_user → prepare`, goal waiting, input necessario, nessuna lettura eseguita o bozza. Non dimostra perdita DB. La correzione a150 non è raggiunta; tutti i sei controlli finali sono `not_run`. Input storici completi e testo esatto della domanda non sono conservati: la categoria knowledge è inferita dai flag e dal codice.

I report originali, le due review, la finestra di raccolta senza filtri e gli hash dei log restano disponibili nell’[indice641](evidence/autonomy_v162_641_results_2026-10-12.json). Gli esiti non vengono trasferiti a revisioni successive.

---

# 12 ottobre 2026 — v162, limite della traccia nella CI c8ca

Push e PR si fermano entrambi sul nuovo caso `early_render[duplicate]`: **1 FAIL / 937 PASS** per ciascuna invocazione backend. Passano gli assert precedenti su letture reali, stato iniziale non programmato e finale programmato, proprietario, Situation, contatori, orario, unico obiettivo e unico wake. L’asserzione composta degli eventi fallisce nella proiezione pubblica; il log non espande la lista e non permette di attribuire l’assenza a un evento specifico.

Il sorgente mostra che `_redact_coords` tronca tutte le liste a 12 elementi. La nuova prova intercetta `loop.public_trace`, osserva soltanto i nomi degli eventi prima della proiezione e restituisce il risultato reale invariato. Le asserzioni terminali non sono rimosse. Tutti i 20 casi restano definiti; la nuova CI è **NOT_RUN al congelamento**. Runtime, limiti della traccia e oracle live restano identici.

[Manifest c8ca](evidence/autonomy_v162_handoff_ci_2026-10-12_c8ca6d0_failure.json) · [Indice, hash e limiti](evidence/autonomy_v162_trace_observation_repair_2026-10-12.json).

---

# 12 ottobre 2026 — v162, regressione del test250ef7f

I due backend della CI250ef7f falliscono nello stesso punto: `ack_snapshot["follow_up"]` presuppone un campo assente nel contratto CREATE. Prima del fallimento passano i controlli su risposta, contatori, unica Situation e immutabilità del risultato originale. Il manifest conserva esiti e checkout distinti di push e PR.

La nuova prova asserisce l’assenza di quel campo nel risultato storico e mantiene le letture effettive del programma. Due casi ulteriori passano dal gate reale con una risposta intermedia prima di programmare, osservando lo stato iniziale non programmato e quello finale programmato. **20 casi definiti; esecuzione NOT_RUN al congelamento.** Il runtime resta quello250ef7f.

Il collector mirato è verificato separatamente con40 controlli su copie dichiarate dei log22df; non esegue modelli e non promuove i loro esiti. Il suo manifest conserva il candidato annunciato al proprio congelamento; la configurazione della prossima raccolta userà il nuovo SHA e deployment. [Indice](evidence/autonomy_v162_handoff_contract_repair_2026-10-12.json).

---

# 12 ottobre 2026 — v162, confini delle prove recuperate

**CI 22df078: 6 workflow e 16 job SUCCESS.** Il live 68aa2564 termina CRASHED alle 14:18:59 UTC con tre report completi. Situation fallisce il gate per il riferimento al luogo mancante; la revisione rileva obiettivo ridotto alla pioggia e handoff incoerente. Agent: 4/9, soli negativi, 0/5 positivi accettati, Home/replay not_run. Pubblico: PASS tecnico ma revisione umana negativa. Le 51/51 citazioni autentiche non attestano che le conclusioni siano sostenute.

Il locale 7a65f40 conserva 1.890 PASS, 1 SKIP, 0 FAIL e CLI 9/9. Dopo `409 environment_offline`, qualificazione runtime recuperata identica per hash, loop e test ricostruiti: **nuova CI NOT_RUN al congelamento**, nessun trasferimento dei risultati. I 18 casi nuovi sono stati letti e revisionati, non eseguiti in questo ambiente. La raccolta cloud recupera tre report byte per byte e una nuova ricevuta; non ricostruisce i vecchi poll o archivi locali.

Resta il rifiuto APP eb9c3870, senza aggiramento via staging/cloud; firma, installazione, visualizzazione e tap non sono attestati.

[Situation](evidence/autonomy_v162_live_2026-10-12_22df078_situation.json) · [Autonomia](evidence/autonomy_v162_live_2026-10-12_22df078_autonomy.json) · [Pubblico](evidence/autonomy_v162_live_2026-10-12_22df078_public.json) · [Binding e limiti](evidence/autonomy_v162_cloud_recovery_2026-10-12.json)

---

# 12 ottobre 2026 — v162, CI 650 verde e accettazione reale ancora aperta

## Identità e CI osservata

Head `650a6f404be52829c983cf49c0b612a96e6a4a11`, tree `fb5a9bb2fa8d3a593815481a66767a5d3cca2f89`; merge tecnico PR `96565463674bf8b58d1b3e693f01f3a2a30f4e62`, genitori `6e619cf` e 650, stesso tree. **6 workflow / 16 job / 259 step SUCCESS**, 7 job push e 9 PR. Nessun job saltato.

Ogni invocazione backend riporta **1.274 PASS v162, 192 PASS Vision catalog/seed/anatomy, 6 PASS Mongo con riavvio di processo e 3 PASS dei guard statici v39**, senza skip in questi gruppi. Le due selezioni storiche precedenti conservano rispettivamente tre e cinque test saltati. CLI scripted **9/9**, zero modello reale, HTTP al modello ed effetti esterni; SHA650 nel push, SHA del merge tecnico nella PR. Scansione completa della storia eseguita nei due eventi. Il manifest derivato corregge esplicitamente l’aggancio iniziale dei tre guard statici al conteggio 1.274: i log e i verdetti restano invariati.

Mobile **40/40**, 20 Chromium e 20 WebKit. Configurazione Expo, generazione iOS ed export JavaScript iOS passano in entrambi i job frontend. Le prove browser usano API simulate; il workflow phone-turn verifica il confine conversazionale, non una telefonata o una ricevuta su dispositivo. Questi conteggi non sono un totale di test unici e non sostituiscono l’aggregato locale 1.831 della precedente registrazione.

## Tre prove reali650

Deployment tecnico `d32cdee9-64f2-4d40-90be-4d907fe7f036`, servizio `d84dcca0-6372-40cc-a19e-ca32c3533fb0`, ambiente `8554e8b3-db0b-4e55-ae40-7ab5a25eb657`. I tre rapporti sono completi prima dello stato terminale **CRASHED**, `updatedAt=13:18:27.613Z`; la raccolta riuscita non promuove il risultato delle prove.

| Prova | Esito originale | Accettazione e limite |
|---|---|---|
| Situation Tarquinia | `followup_pending_unobserved`, `passed=false`; 7 chiamate logiche / 11 HTTP modello / 1 lettura provider | Situazione e controllo futuro salvati; worker, monitoraggio, controllo futuro, azione utile e dispositivo `not_run`. Cancellazione sintetica PASS, zero wake residue, nessun ritiro fisico dichiarato |
| Autonomia | **4/9**, 90 chiamate logiche / 97 HTTP modello | Passano soltanto `source_revoked`, `memory_revoked`, `already_resolved`, `irrelevant`; **0/5 testi positivi accettabili manualmente** |
| Letture pubbliche | Tecnica e semantica bounded PASS; 2 letture / 4 decisioni / 0 grounding rewrite | Il finale di 578 è accettabile nel singolo caso; l’originale conserva `pending_human_review`, senza promozione automatica o prova di autonomia generale |

`completed_result` conserva il rifiuto automatico `MISSING_COMPARISON_VALUE_60`; planning, Home e source-change esauriscono il budget, Memory corretta termina `COMPLETION_NEEDS_NEW_DECISION`. I codici automatici e i giudizi manuali sono registrati separatamente. Soltanto il caso completed raggiunge i controlli finali Home/replay/owner; gli altri quattro casi positivi li conservano `not_run`, senza inventare una consegna.

Nel pubblico il finale coincide byte per byte con il quarto `message_to_user`, prodotto da OpenAI `gpt-4o-mini`: 2.990 m / 782 s e le previsioni23 °C / 0% alle 16/17 sono riportati fedelmente come distanza, stima e previsione. La review non accetta il messaggio intermedio Mistral di 2.668, che tratta ETA come dato misurato, anticipa un meteo non ancora letto e aggiunge rallentamenti non documentati; quel testo non è il finale. L’identità del provider osservato non è una prova di fatturazione né una raccomandazione di cambiare configurazione.

### Revisione dei cinque testi positivi

- **Completed:** il differenziale 60 è eliminato dall’audit; restano clausole mensili di disdetta/rimborso non sostenute. Il completamento software e i controlli Home non rendono accettabile il testo.
- **Planning:** 60 è presente. Il rifiuto manuale riguarda condizioni non fondate, tra cui nonrimborso attribuito a entrambe le formule; gli esempi 20 € e 30 giorni sono esplicitamente ipotetici e non vengono descritti qui come fatti affermati.
- **Home:** 60 è presente, ma assenza di penali e condizioni mensili non derivano dalla nota. Il caso si ferma prima delle verifiche finali di consegna.
- **Memory corretta:** la lettura corrente contiene 150 e il relativo passaggio autentico viene citato, ma l’audit afferma 120 e respinge 150; il testo conserva 120/60 anziché 150/30.
- **Source-change:** la differenza −60 € è un’espressione aritmetica valida. Il rifiuto manuale riguarda l’assenza di spese extra e la flessibilità non sostenute, separate dall’overflow successivo del chooser.

Le 43 selezioni letterali osservate risultano autentiche; questo non prova l’implicazione delle affermazioni. I cinque testi salvati sono esaminati integralmente. Alcune generazioni precedenti rifiutate e alcuni input diagnostici restano troncati o omessi: non viene ricostruito un corpo storico completo che il report non conserva.

## Modifiche successive e conservazione

Le modifiche successive alla risposta terminale e alla diagnostica sono congelate nello snapshot locale `0604fd9` e non sono state provate dal collaudo reale 650. La risposta terminale può riferire il controllo già persistito dopo rilettura corrente, conservando l’esito incompleto; la diagnostica rende osservabili più confini effettivi del turno e della verifica, entro i limiti del reporter. L’esempio astratto X/A/B nell’audit sostituisce due ripetizioni del prompt: è un’ipotesi da valutare, non una correzione semantica dimostrata. Le 40 regressioni locali dell’esperimento verificano compatibilità di protocollo, trasporto e fonti; non provano la qualità della prossima risposta reale. Schema, parser, numero di chiamate e budget restano invariati.

Archivio con **53 voci: 49 originali esatti e 4 copie redatte**. Sono rimossi soltanto quattro oggetti creator e due rese testuali degli stessi dati personali; nessun valore personale nel manifest. I tre rapporti mantengono dimensioni, hash e frammenti originali, concatenati senza separatori e con un solo LF finale. Gzip `mtime=0`, decompressione ed estrazione di ogni voce verificate. Le limitazioni interne dei record diagnostici restano quelle originarie; il JSON completo non equivale al corpo HTTP completo di tutti i modelli.

L’autorizzazione generale della persona a proseguire resta valida. La revisione automatica dell’approvazione ha però respinto la specifica patch APP `eb9c3870-6835-4c5a-bcbb-24d34b6dd627` (`INVALID_ARGUMENT`; `Cancelled — the user did not approve this action. No changes were made.`). Quella modifica APP non è stata eseguita e non è stato effettuato un merge su `staging/cloud` per aggirare il blocco. Firma, installazione e ricezione di una notifica sul telefono ad app chiusa restano non attestate.

**Verifica locale successiva:** commit `0604fd9a96ba7c4ae21b78feb869b8a4e9e57d9b`, tree `23b63ffbbe1648eae0e1614389c6caddb8cad860`; **1.874 PASS / 1 SKIP / 0 FAIL**, 152 moduli e 154 selezioni in 71,38 s, esito 0 e otto file sorgente invariati durante la prova. **CLI scripted 9/9**, zero tentativi modello, HTTP al modello ed effetti esterni, `real_model_executed=false`. Il report mantiene `code_revision=null`; commit e tree sono attestati separatamente dal manifest di esecuzione. L’unico SKIP è `tests/test_ai_provider_manager.py::test_real_gemini_enrichment_optional`, perché `GEMINI_API_KEY` è stata deliberatamente lasciata vuota nel run isolato; non descrive le credenziali dei servizi. Questi sono esiti locali, distinti da CI e live 650; la nuova revisione non ha ancora una propria prova remota o reale.

La selezione separata della risposta terminale ha **54 PASS e 3 FAIL legacy di navigazione**, riprodotti anche caricando il sorgente HEAD di confronto. I tre nodi sono rimasti invariati e sono fuori dall’aggregato di 152 moduli; il totale integrato non ne dichiara la risoluzione.

[CI 650](evidence/autonomy_v162_ci_2026-10-12_650a6f4.json) · [Manifest dei tre collaudi e archivio](evidence/autonomy_v162_live_2026-10-12_650a6f4_manifest.json) · [Review dei cinque testi positivi](evidence/autonomy_v162_live_2026-10-12_650a6f4_semantic_review.json) · [Revisione separata del pubblico](evidence/autonomy_v162_live_2026-10-12_650a6f4_public_review.json) · [Seguito locale e log](evidence/autonomy_v162_followthrough_2026-10-12.json). Gli originali e i suffissi documentali storici restano invariati.

---

# 12 ottobre 2026 — v162, recupero dopo il collaudo 636 e integrazione della base 6e619

**636 resta fallito come accettazione reale; le correzioni seguenti sono verificate separatamente.** Gli originali e la review semantica sono conservati senza modificare risposte o verdetti. Revisione esatta: `636c0f72b374bff95039ad2b3e017ed2974c77db`, tree `1c7653987a805f34d75269495b3d86c5b1b5e796`.

| Prova su 636 | Risultato osservato | Limite |
|---|---|---|
| CI push | 2 workflow, 7/7 job PASS; v162 1.173 PASS, Vision 157 PASS, Mongo 6 PASS e scansione completa della storia | CI PR e Mobile non eseguite; nessun PASS trasferito da altri SHA |
| Autonomia reale | 5/9 PASS automatici; 82 chiamate logiche, 96 HTTP al modello | Accettazione semantica complessiva rifiutata |
| Tarquinia | `EXACTLY_ONE_NEW_SITUATION_REQUIRED`, 7 chiamate logiche, 14 HTTP modello, una lettura meteo reale | Nessuna nuova Situation valida; worker, monitoraggio, controllo futuro e ritiro `not_run` |
| Letture pubbliche | 2 letture reali e 4 decisioni; tecnica PASS, semantica FAIL | Falso positivo lessicale sull’intensità distinto da `MODEL_CLAIM_REWRITTEN`, con una riscrittura registrata |

La review manuale conserva questi rilievi:

- `completed_result`: totali 180/120 e differenza 60 corretti, ma condizioni di disdetta e rimborso mensili non presenti nella nota sono accettate dall’audit con citazioni irrilevanti. Il difetto non deriva soltanto da mancata copertura delle affermazioni.
- `planning_outage`: il testo finale di 1.824 caratteri non riporta 60 e chiama 120 euro risparmio totale; il rifiuto `MISSING_COMPARISON_VALUE_60` è fondato. Home e replay passano sul piano tecnico, senza rendere il testo corretto.
- `home_write_retry`: il testo salvato di 2.272 caratteri dichiara la disdetta mensile senza penalità come **ipotesi da confermare**, ma vi fonda la raccomandazione; manca inoltre il differenziale. Goal ancora attivo, verifiche Home/replay `not_run`.
- `memory_corrected`: il testo corrente usa correttamente 180/150/30, ma introduce una comparazione di flessibilità non sostenuta. Il payload storico completo del chooser da 20.338 caratteri non è conservato; la ricostruzione equivalente non prova la causa esatta e resta oltre il limite, senza patch.

I testi effettivi forniti agli audit sono osservati integri nei report trattenuti. Per la verifica finale non è conservato il corpo HTTP storico completo: la lettura del percorso di serializzazione non dimostra una cattura che non esiste. Nessun nuovo campo di ragionamento certifica da solo la qualità semantica.

**Correzioni locali mirate, conteggi non sommabili:** risposta conversazionale 20 PASS (il gruppo 114 precede l’ultimo caso); dichiarazione Situation 9 PASS, con un’asserzione legacy già fallita sulla base e lasciata invariata; riesame differito 75 PASS su 5 moduli; audit e compatibilità 157 PASS su 8 moduli; diagnostica pubblica 86 PASS su 7 moduli. Inventario della pianificazione: 13 nuove prove PASS e gruppo di quattro moduli **58 PASS**, senza dimostrare la scelta del prossimo passo da parte di un modello reale. Le review indipendenti sono letture senza nuove esecuzioni.

**Aggregato integrato:** codice locale `a11b2e36ad9ba193dd6805f306937bc908fddf65`, tree `10e536f4213b087133c6f8ee28ba04c4077bd1c8`; **1.831 PASS / 1 SKIP**, 149 moduli e 151 selezioni in 70,52 s, esito 0 e hash del codice immutati durante la prova. L’unico SKIP riguarda il test opzionale con Gemini reale, senza credenziale fornita nell’ambiente sintetico di questa esecuzione. **CLI scripted 9/9**, con zero tentativi del modello, richieste HTTP al modello ed effetti esterni, `real_model_executed=false`. Il report conserva `code_revision=null`; il collegamento al codice locale è documentato separatamente nel manifest di esecuzione. TypeScript/export web PASS; Chromium **20/20 PASS**. Le 20 prove WebKit hanno errori di avvio per librerie OS mancanti, senza esecuzione applicativa; il tentativo standard di installazione è fallito con `EPERM`. CI remota e prove reali del nuovo candidato restano pendenti. Dopo l’aggregato è stato aggiunto soltanto il selettore CI `vision_tests/test_anatomy_atlas.py`, da eseguire con Mongo reale; nessun esito locale è attribuito a questa prova.

La pubblicazione del nuovo candidato, la sua CI completa e un nuovo collaudo reale restano da verificare. L’aggiornamento delle due app Railway resta subordinato all’approvazione della patch `eb9c3870-6835-4c5a-bcbb-24d34b6dd627`, precedentemente respinta dalla revisione automatica; l’integrazione Git non aggira quel limite. Firma, installazione e ricezione su un telefono ad app chiusa non sono attestate.

[Indice delle evidenze e delle verifiche locali](evidence/autonomy_v162_recovery_2026-10-12.json) riporta hash degli originali, della review da 154.342 byte, dei manifest, dei log e dei suffissi storici. I gruppi sovrapposti non sono sommati al totale dell’aggregato.

---

# 12 ottobre 2026 — v162, prova 630 e correzioni dopo il collaudo

## Identità e CI osservata

Revisione live/CI `630020147223ada63430a11870209494dc35cc22`, tree
`0878f56d49f120c7b97ce93e49fa9076398c43c2`. La CI raccolta alle
10:58:47.030 UTC del 12 ottobre conclude **5/5 workflow e 15/15 job SUCCESS**;
nessun job saltato. Merge tecnico
`914c682779b8bee332b15fae9e399cf3e2c1ce34` sulla base `c419e0c`, tree identico.
La base avanzata a `ff6d273` durante la raccolta non è coperta da questa CI.
Fonti: [CI originale 630](evidence/autonomy_v162_ci_2026-10-12_6300201.json) e
[archivio completo](evidence/autonomy_v162_ci_2026-10-12_6300201_full.json.gz).

Ogni invocazione backend riporta 1.074 PASS v162 senza skip, CLI scripted 9/9
senza LLM/HTTP del modello e 6/6 prove Mongo con riavvio di processo, senza skip.
Altre selezioni precedenti nei job hanno otto test saltati per invocazione;
i log non ne riportano il motivo. Non sono skip dei job, di v162 o di Mongo.
Mobile: 36/36, 18 Chromium e 18 WebKit. TypeScript, configurazione Expo,
prebuild iOS senza installazione ed export JavaScript iOS hanno successo.
Questi risultati non attestano firma, installazione, rilascio app o ricezione
ad app chiusa. I conteggi PR/push e dei gruppi sovrapposti non sono un totale
di test unici.

## Nove scenari reali: 3/9, verdetto originale FAIL

Il deployment tecnico `068a3ef3-729b-4690-871a-ec36667ce513` ha emesso i tre
report, recuperati integralmente; lo stato terminale osservato è `CRASHED`.
La suite dei nove casi va dalle 11:07:54.638830 alle 11:15:28.570992 UTC:
48 tentativi logici e 57 richieste HTTP del modello, fixture
`personal_outcome_v1`. Fonte: [nove scenari originali](evidence/autonomy_v162_live_2026-10-12_6300201_original.json) e
[raccolta con binding del servizio](evidence/autonomy_v162_live_2026-10-12_6300201_collection.json).

| Scenario | Macchina | Ragione originale | LLM logiche / HTTP |
| --- | --- | --- | ---: |
| completed_result | FAIL | `UNFINISHED_WORK_LOST` | 5 / 8 |
| planning_outage | FAIL | `UNFINISHED_WORK_LOST` | 4 / 5 |
| home_write_retry | FAIL | `COMPLETION_BUDGET_EXHAUSTED` | 14 / 15 |
| source_revoked | PASS | — | 4 / 5 |
| memory_revoked | FAIL | `UNFINISHED_WORK_LOST` | 5 / 5 |
| memory_corrected | FAIL | `UNFINISHED_WORK_LOST` | 5 / 8 |
| source_change_crash | FAIL | `OWNED_SOURCE_NOT_READ_ONCE` | 9 / 9 |
| already_resolved | PASS | — | 1 / 1 |
| irrelevant | PASS | — | 1 / 1 |

Per i sei casi falliti i controlli di risultato, Home, replay e isolamento non
sono stati raggiunti; restano `not_run`. I tre PASS riguardano casi negativi,
non consegna di un risultato positivo. I codici di fallimento non consentono
da soli di ricostruire il valore esatto di una dichiarazione del piano.
La [diagnostica estratta](evidence/autonomy_v162_live_2026-10-12_6300201_planning_diagnostics.json)
conserva campi osservati e limiti; non sostituisce input/output mancanti.

### Testo Home: rifiuto semantico indipendente

La bozza di `home_write_retry` contiene 3.643 caratteri (3.677 byte UTF-8),
senza troncamento. Generazione, `content` dell'audit `verified=true` e testo
persistito sono identici; SHA-256
`f3df3f91ac1b0bdbec7babe7a549712167b02207b0ea89fd9f20def0860bce92`.
La tabella 180/120 viene contraddetta dalla frase «costo totale sia identico»;
la differenza utile di 60 è assente; la maggiore flessibilità per interruzione
anticipata del mensile non è stabilita dalla fonte. Il giudizio `conditional`
nella review non rende condizionale il testo assertivo. Una citazione autentica
sul mancato rimborso annuale non sostiene una proprietà non dichiarata del
mensile. La bozza resta **inaccettabile**, goal non completato, Home e replay
`not_run`. Fonte completa: [review del testo Home](evidence/autonomy_v162_live_2026-10-12_6300201_home_semantic_review.json). Le prove locali successive non
attestano la risoluzione di questi errori semantici.

## Tarquinia: FAIL originale e diagnosi del runner

La prova reale, dalle 11:06:22.441453 alle 11:07:52.397908 UTC, termina con
`INITIAL_REVIEW_NOT_ADMITTED`: sette chiamate logiche, dodici HTTP del modello,
una lettura meteo reale, nessuna ricerca e nessun passo Agent. I tool meteo e
programmazione hanno stato `ok`; il vecchio report conserva però soltanto il
loro stato e gli input del modello sono tutti limitati a 9.000 caratteri.
Le sette risposte del modello sono complete. La risposta finale alla persona
sintetica dichiara di non avere evidenza sufficiente per una stima quantitativa.
Le proposte intermedie non vanno confuse con una risposta consegnata. Fonte:
[Tarquinia originale](evidence/situation_v162_live_2026-10-12_6300201_original.json).

La [ricostruzione isolata della programmazione](evidence/situation_v162_2026-10-12_schedule_transition_diagnostic.json), senza modelli o HTTP, esercita create/programmazione/rilettura
reali con owner sintetico. Dimostra il passaggio dello stesso goal da
`situation_initial_review` a `situation_followup`, l'annullamento della wake
iniziale e un solo controllo pendente alle 16:00 UTC, 18:00 a Roma. Owner,
Situation e revisione restano corretti; l'obiettivo iniziale asciugatura oppure
rischio resta conservato. Il controllo cade oltre i 240 secondi osservabili.
Il vecchio runner rifiuta il tipo follow-up e si ferma prima del worker. Il
probe è una ricostruzione isolata, non il database storico del live.

La correzione registra lo snapshot prima dell'asserzione e riconosce i due
tipi validi soltanto con fonte, owner, revisione e wake correnti. La route
`conversation_scheduled` oltre il termine produce
`followup_pending_unobserved`, **`passed=false` e risultato lavanderia completo
falso**. Worker, monitoraggio, controllo futuro, azione utile e dispositivo
rimangono `not_run`; nessun tempo viene accelerato. Quando il termine è
raggiungibile, la stessa wake viene seguita con l'orologio reale. La
cancellazione sintetica verifica la chiusura e l'assenza di wake residue;
nessuna stesura reale precedente viene riaperta. La diagnostica dei tool ora
conserva il payload effettivo redatto entro 6.000 caratteri e dichiara eventuale
troncamento. Il FAIL live 630 resta immutato.

## Letture pubbliche: falso negativo numerico, accettazione ancora distinta

Il [report pubblico originale](evidence/public_read_v162_live_2026-10-12_6300201_original.json) esegue due letture reali, percorso e meteo, con quattro
chiamate al modello. Il confine tecnico passa; il verdetto originale resta
FAIL `semantic:TEMPERATURE_MISMATCH`. Il parser trattava il separatore del
range `23-24°C` come segno negativo e ricavava `-24`. La nuova lettura verifica
entrambi gli estremi degli intervalli, mantenendo tolleranza 1,1 e giudizio
umano. Il [replay rosso](evidence/public_read_v162_2026-10-12_temperature_replay_red.json)
e il [replay corretto](evidence/public_read_v162_2026-10-12_temperature_replay_green.json)
conservano la distinzione: nel secondo non restano discrepanze numeriche.

Questo non accetta la frase «senza possibilità di pioggia», che attribuisce
certezza fisica a una previsione. Il testo reale e il suo verdetto non vengono
riscritti né promossi. Il report pubblico non espone una propria revisione;
il binding a 630 proviene dal lancio e dai metadati del medesimo servizio,
conservati nella raccolta.

## Correzioni locali e limiti delle prove

| Confine | Prova mirata nuova | Ultimo gruppo locale | Limite |
| --- | --- | --- | --- |
| Runner Situation e tool osservati | RED 5 FAIL; focused GREEN 14/14 | Modulo 41 PASS, 31,82 s | Ricostruzione sintetica e primo ciclo scripted; non live o ricezione fisica. |
| Range di temperatura | RED 7 FAIL/16 PASS; 23 casi nuovi | 50 PASS, 1,41 s | Corregge il confronto numerico, non la certezza espressa dal modello. |
| Origine `current_facts` | RED 14 FAIL/2 PASS; GREEN 16/16 | 16 PASS, 0,26 s | Gruppo correlato 31 PASS/1 FAIL; viaggio legacy riprodotto con soli due moduli 630 in memoria. |
| Verità del controllo programmato | RED 1 FAIL/4 PASS; 5 nuovi | 22 PASS, 0,71 s | Rilettura owner-bound; nessuna nuova stima o promessa di push. |
| Esempi validi dei passi | RED 3 FAIL/5 PASS; 8 nuovi | 63 PASS, 1,86 s | Esempi di protocollo, senza riscrittura o autorizzazione dell'azione. |
| Diagnostica delle dichiarazioni | 16 nuovi; nuova osservabilità | 75 PASS, 1,90 s | Presenza/tipo bounded; nessun valore storico inventato, parser o gate cambiato. |

Il test viaggio legacy resta invariato e documentato come preesistente. La
[verifica della provenienza](evidence/autonomy_v162_2026-10-12_current_fact_provenance_verification.json)
e la [verifica del runner](evidence/situation_v162_2026-10-12_schedule_runner_verification.json)
conservano comandi, limiti e hash. La [review di compatibilità del piano](evidence/autonomy_v162_2026-10-12_plan_schema_compatibility_review.json) spiega perché questo delta
non aggiunge uno schema nativo del planner: `strict` con parametri tool aperti
non è un contratto minimo compatibile. Le prove non simulano una garanzia che
il provider non riceve.

I conteggi dei gruppi si sovrappongono e non vanno sommati. Skim indipendenti
non hanno rilevato blocker nei confini letti; non sono prove aggiuntive sul
modello reale. L'indice registra file e hash locali: `HEAD` del checkout con
modifiche non è la revisione pubblicata che le contiene.

Aggregato e snapshot locale registrati:
`1653 PASS, 1 SKIP; 135 moduli, 137 selezioni, 69.19 s`, `9/9 SCRIPTED; zero modelli reali, HTTP del modello ed effetti esterni`,
`9fdc2af983b8323f956583b6ec7f90c58ab7dbee` / `e9d09b89c5e12f7034aaaf08c43b024818e5a239`,
`non eseguite su questa versione al momento della registrazione`.
Riferimenti, originali e log locali: [indice delle evidenze e delle correzioni](evidence/autonomy_v162_followup_2026-10-12.json).

La diagnostica del chooser osserva il riduttore originale solo nel percorso dello stesso
database, owner e goal sintetico, ricontrollando il marker prima della scelta. Registra
le cause effettivamente emesse dal codice, dimensioni e hash dell'input e una copia
redatta entro 9.000 caratteri; conserva al massimo dodici osservazioni. Le quindici
prove dedicate passano. È osservabilità per il prossimo live, non una spiegazione
retroattiva certa del blocco Home 630.

## Verifica locale della versione integrata

Codice locale verificato: `9fdc2af983b8323f956583b6ec7f90c58ab7dbee`, tree `e9d09b89c5e12f7034aaaf08c43b024818e5a239`.
Suite integrata: **1653 PASS, 1 SKIP; 135 moduli, 137 selezioni, 69.19 s**. CLI separata: **9/9 SCRIPTED**, senza
modelli reali, HTTP del modello o effetti esterni. Le due incompatibilità della
diagnostica e quella dell'esempio calendario sono corrette; i log dei tentativi
falliti e riusciti restano nell'archivio. I gruppi mirati sovrapposti non si sommano
al totale. Questa registrazione precede la pubblicazione: gli SHA sopra identificano
lo snapshot locale, non una nuova CI o una nuova prova reale già completata.

La base revisionata `ff6d273` è integrata nei suoi otto file. I due moduli Vision
hanno 147 PASS locali e dieci errori di setup per Mongo non disponibile; la prova
su Mongo reale è aggiunta alla CI usando il servizio esistente. Le due suite Node
passano 192 casi dopo avere generato il manifest dal catalogo reale di 126 famiglie.
Il primo errore per manifest assente è conservato. Questi risultati non sono
una prova di notifica sul dispositivo.

---

# 12 ottobre 2026 — v162, ripresa del ciclo e giudizi sulle fonti

Il precedente head `fe2d37f` supera cinque workflow CI e tutti i 15 job,
ma il suo gate reale resta **6/9 macchina e non accettato dalla review**:
85 chiamate logiche e 96 HTTP. Un confronto accettato introduce condizioni
non sostenute dalle fonti; un altro omette la differenza utile. Citazioni
autentiche e presenza di un artefatto non dimostrano la fedeltà del risultato.
Il report originale e il giudizio indipendente restano conservati integralmente.

## Lettura dei risultati precedenti

| Scenario fe2 | Macchina | Review e limiti |
| --- | --- | --- |
| completed_result | PASS | 180/120/60 completi, vincolo annuale e provenienza corretti. |
| planning_outage | FAIL | Attribuzione effettiva presente, ma manca davvero la differenza 60. Home/replay eseguiti separatamente non promuovono il risultato. |
| home_write_retry | FAIL | Testo completo; il verifier aggiunge una conferma esterna non richiesta, poi propone wait=0 con revised_steps. La wake era presente: non è un caso provato di wake persa. |
| source_revoked | PASS | Revoca e replay rispettati. |
| memory_revoked | PASS | Arresto dopo revoca. |
| memory_corrected | FAIL | Rilettura corrente a 150, ma ripetuti audit con citazioni non contigue; nessun risultato salvato. |
| source_change_crash | PASS | Review FAIL: cancellazione mensile senza penali e assenza generale di costi non sostenute. Le citazioni autentiche non bastano. |
| already_resolved | PASS | Nessuna riapertura. |
| irrelevant | PASS | Nessun goal estraneo. |

I tre diagnostici `b816d05` falliscono. Planning e Home esauriscono il limite
esistente di quattro tentativi di piano dopo errori effect_type/wrong_type:
il valore errato non è esportato, quindi non si conclude che fosse null.
L'assenza della wake al limite è una sospensione prevista; il nome generico
UNFINISHED_WORK_LOST del runner non dimostra un guasto dello scheduler.
La correzione Memory resta in attesa con wake. Anche i tre diagnostici `b4ca675`
falliscono con COMPLETION_BUDGET_EXHAUSTED, così come i tre diagnostici `79d7fc3`.
Sul successivo `bf8306b` falliscono tutti e tre: planning_outage abbandona
con COMPLETION_NEEDS_NEW_DECISION, Home e Memory esauriscono il budget.
Questi report restano attribuiti ai rispettivi commit precedenti, senza
dedurre il risultato della revisione corrente. Nessun verdetto viene sostituito.

## Confini del nuovo collaudo

Le citazioni native vengono materializzate soltanto dagli input esatti di quel
singolo audit. Nei diagnostici restano separati gli identificativi ricevuti dal
modello e i passaggi risolti dal codice; i secondi non sono citazioni emesse dal
modello né attestazioni semantiche. Il log di avanzamento conserva null per uno
stato non osservato, invece di presentarlo come false.

Il runner Tarquinia mantiene 240 secondi, 40 chiamate logiche, 80 HTTP modello e
12 letture provider. Gemini Search condivide entrambi i relativi contatori.
HTTP consentito solo ai provider già collegati e al punto pubblico della fixture;
effetti e invii reali sono intercettati senza produrre ricevute finte. I test
offline usano trasporto e risposte esplicitamente sintetici. Le fasi future
non eseguite restano not_run; la cancellazione finale chiude solo la fixture.

Il riesame rifiuta attese senza tempo valido o mescolate a revisioni del
piano. Conserva il checkpoint tecnico già salvato e i contatori, senza trasformare
un errore di formato in una nuova attesa del mondo. Il planner può leggere una
sola diagnosi storica del formato, filtrata per owner, goal e scadenza: la risposta
corrente viene comunque validata senza riscrittura del piano.

Nell'audit, il modello seleziona passaggi identificati dal codice, ricavati
senza perdita dalla fonte corrente. Il codice risolve solo questi identificativi
in citazioni letterali, che attraversano il controllo precedente. Il formato
legacy continua a richiedere citazioni autentiche; forme ambigue o riferimenti
non forniti falliscono. Le istruzioni chiedono di controllare ogni clausola
sostanziale, incluse condizioni e ambito, prima di dichiararla sostenuta.
Il giudizio semantico resta del modello e deve essere verificato nella prova live.

Il chooser condivide metadati identici delle Evidence in tabelle ricostruibili;
quando necessario usa gruppi contigui, senza cambiare ordine, testo, riferimenti,
tempi o limiti. Le due catture reali del ciclo sintetico Tarquinia passano da
12.381 a 6.196 e da 12.732 a 7.122 caratteri, entro lo stesso limite di 9.000.
Il materiale che rimane troppo grande continua a essere rifiutato.

Il dispatcher verifica i fatti della capability: una capacità di scrittura
dichiarata inspect, prepare o altro tipo diverso da execute viene respinta prima
del gestore effetti. Il riesame esistente riceve l'errore; non vengono inventati
un tipo di azione, parametri o autorizzazioni. Il percorso execute conserva
gli stessi controlli di autorità, consenso e idempotenza.

Gemini Search associa i segmenti generati soltanto agli indici originali dei
chunk dichiarati dal provider, separati per candidato. Non assegna più alla
prima fonte un testo riferito a un'altra, né perde i supporti raggiunto il
limite dei risultati. Il nuovo campo `snippet_origin` attraversa osservazione,
Research, persistenza, valutazione, sintesi e diagnostica. Un segmento generato
non viene presentato come citazione letterale della pagina o prova primaria
automaticamente verificata. I record precedenti mantengono origine unknown;
un giudizio del modello sul tipo di fonte non può modificare questo dato.
La correzione non aggiunge ricerche, download di pagine o chiamate modello.
Il contratto degli indici e del segmento è verificato nella
[documentazione ufficiale GroundingSupport](https://ai.google.dev/api/generate-content#GroundingSupport).

La cronologia concorrente fino a `bf8306b` è preservata. Si ritirano
l'inserimento automatico di `information.read`, il riordino dei passi per nome
di capability e la normalizzazione dei null basata sulle sole dichiarazioni del
modello. La review isolata rileva 15 PASS e 8 FAIL sui quattro moduli di `2f4a64f`:
gli otto test del prerequisito non passavano nemmeno il parametro budget; corretto
solo questo, emergeva anche il metodo assente nel fake. Il bypass delle scritture
esisteva già con campi omessi; la normalizzazione null ne ampliava l'ingresso.
Restano i chiarimenti del prompt su letture, versioni e confronto qualificato.
Il test del confronto aveva un mismatch di maiuscole, corretto senza cambiare
fixture o verdetto. Questi test attestano trasporto e formato, non qualità live.
L'ultimo chiarimento del prompt propone un risultato conciso per fonti brevi,
senza imporre un nuovo limite runtime o autorizzare omissioni sostanziali.

Il candidato è isolato nel ramo `ora/v162-autonomy-validation-20261012`.
La base staging `c419e0c` incorpora le modifiche Vision concorrenti, senza
toccare il ciclo Agent o i suoi budget; i 13 controlli Vision dedicati passano
con il trasporto sintetico. Il ramo concorrente e la PR 212 non vengono
riscritti. Le loro pubblicazioni successive non attestano questo candidato.

Verifica locale del candidato integrato: **1554 PASS, 1 SKIP, 129 moduli, 67.26 s**. CLI scripted **9/9**, zero chiamate LLM/HTTP del modello ed effetti esterni.
Tarquinia e l'obiettivo «avvisami quando devo ritirare i panni» restano
confermati. La vecchia stesura è chiusa. Il nuovo runner usa una nuova persona e
stesura sintetiche; attraversa conversazione, Situation, prima wake reale,
meteo, ricerca e programmazione successiva. Non accelera il tempo e non misura
fisicamente l'asciugatura. `followup_pending` attesta soltanto il primo ciclo:
controllo futuro, momento utile e ricezione sul dispositivo rimangono separati.

CI e prove live di questa revisione devono ancora essere osservate dopo la
pubblicazione. Il servizio tecnico isolato non equivale all'app rilasciata.
Il controllo automatico ha rifiutato il deploy app; il rifiuto non viene aggirato
con un merge. Build nativa firmata e notifica ad app chiusa non sono attestate.
Non si dichiara l'app pienamente autonoma sulla base dei test locali.

Prove originali e misure sono elencate in
[indice delle evidenze](evidence/autonomy_v162_repairs_2026-10-12.json).
Il [report live fe2](evidence/autonomy_v162_live_2026-10-12_fe2d37f.json),
la [review](evidence/autonomy_v162_manual_review_2026-10-12_fe2d37f.json)
e la [CI fe2](evidence/autonomy_v162_ci_2026-10-12_fe2d37f.json)
mantengono i verdetti e la revisione originali.

---

# 12 ottobre 2026 — v162, integrazione del ramo concorrente verificata

La cronologia conserva il ramo concorrente fino a `06d2d9e`. Restano i suoi
log diagnostici compatti e il relativo test, integrati con i controlli separati
di risultato, Home, replay, owner e isolamento del candidato locale `e624015`.

La trasformazione automatica introdotta da `7c28019` viene ritirata dopo due
review indipendenti e controprove sul suo blob esatto. Associava tutti gli importi
a tutti i periodi della frase: due durate diverse diventavano falsamente comuni.
Un canone mensile precedente all'importo veniva trattato come totale; separatori
delle migliaia, componenti del costo e attribuzioni fra fonti producevano altri
errori. Quattro controprove sono state riprodotte anche dal root, senza modello,
HTTP, esecuzione dell'app o dati dell'utente. L'audit successivo era presente:
non si afferma che ogni aggiunta errata sia stata salvata. Il risultato utile
resta responsabilità dei contratti di preparazione, audit e verifica sulle fonti.

Verifica dell'integrazione: **1.416 PASS, 1 SKIP, 115 moduli, 37,60 s**;
scripted **9/9**, zero chiamate modello, HTTP modello ed effetti esterni.
La produzione coincide con il candidato già verificato: il solo nuovo codice
mantenuto è il diagnostico nel runner, con il suo test. Configurazione nativa e
TypeScript sono invariati rispetto alle verifiche precedenti. Il test del log
attesta formato e limite, non una troncatura reale o un redattore di dati arbitrari.
CI e prove reali devono ancora attestare l'head integrato dopo la pubblicazione.

Evidenze: `docs/evidence/autonomy_v162_concurrent_math_review_2026-10-12_7c28019.json`
e `docs/evidence/autonomy_v162_local_integration_2026-10-12.json`.
Tarquinia e l'obiettivo del ritiro restano confermati; la vecchia stesura è chiusa.
Il limite già documentato sul deploy dell'app e sulla verifica nativa resta aperto.

---

# 12 ottobre 2026 — v162, completezza del risultato e collegamento nativo

La prova reale del padre `5b4efd5` termina **5/9 macchina**, con **84 chiamate
logiche e 90 HTTP**. La revisione indipendente considera completi e fedeli quattro
dei cinque testi salvati. Tre di essi sono respinti da un matcher che non riconosce
attribuzioni italiane effettive; i loro controlli successivi Home/replay non sono
stati eseguiti e non vengono promossi. Nel quinto testo manca la differenza utile
già nell'ultima generation: l'audit e il verifier accettano il confronto incompleto.
La correzione Memory a 150 euro, differenza 30, supera anche Home e replay.

La prova pubblica dello stesso padre supera il controllo automatico con due HTTP
reali e quattro chiamate Gemini. La review la respinge per certezza attribuita alla
stima e assenza di rallentamenti non sostenuta dai dati. La CI del padre è **15/15
job** su cinque workflow: **927 PASS v162**, **6 PASS Mongo reale**, **36 PASS browser**.
Queste evidenze riguardano il padre e il suo merge tecnico originario, non questo candidato.

## Riscontri del padre, verdetti originali preservati

| Scenario | Macchina | Riscontro indipendente |
| --- | --- | --- |
| completed_result | FAIL attribuzione | Confronto 180/120/60 completo, «informazioni riferite dalla persona e registrate in ORA»; Home/replay successivi non attestati. |
| planning_outage | FAIL attribuzione | Confronto completo, informazioni dell'utente e memoria attribuite; Home/replay successivi non attestati. |
| home_write_retry | FAIL manca 60 | Ultima generation 572 caratteri già senza differenza; audit 581 e verifier achieved. Vincolo annuale corretto. |
| source_revoked | PASS | Revoca e replay senza riprendere il lavoro revocato. |
| memory_revoked | PASS | Arresto dopo revoca della Memory. |
| memory_corrected | PASS | 150 corrente e differenza 30; rilettura, Home e replay verificati. |
| source_change_crash | FAIL attribuzione | Confronto completo e «dati riportati da te»; una sola lettura, quattro preparazioni, Home/replay successivi non attestati. |
| already_resolved | PASS | Nessun goal riaperto. |
| irrelevant | PASS | Nessun goal creato. |

Le 84 risposte logiche riuscite provengono da Gemini2 (71) e Mistral (13), senza
modificare l'ordine dei provider. Dei 37 passaggi citati conservati nel report,
quattro non letterali appartengono ad audit intermedi respinti. Tutte le 25
citazioni degli audit dei risultati salvati sono autentiche. La completezza e
il supporto semantico sono giudizi separati. Otto decisioni omesse nel ramo
source_change impediscono di ricostruire il primo audit respinto.

Il pubblico restituisce 672 secondi e 2.765 metri: circa 11 minuti e 2,8 km sono
corretti. I dati delle 11:00 e il massimo previsto di 24 °C hanno riscontro. Il
titolo «Certezze da dati live» e l'assenza di rallentamenti eccedono le prove.
Una lieve imprecisione associa 1–2% di pioggia anche a pomeriggio/sera, i cui
valori riportati sono invece 0%. Il PASS automatico originale non viene alterato.

## Correzioni del candidato e verifiche

L'audit della preparazione controlla ora anche i risultati sostanziali mancanti
rispetto al bisogno attestato. Deve integrare le conclusioni sostenute dalle fonti
correnti e verificarne premesse e citazioni. Il verifier confronta il contenuto con
l'esito personale: un criterio generato che dice soltanto «documento disponibile»
non sostituisce il confronto richiesto. Requisiti derivati e richiesta non sono
promossi a prove; non si inventano premesse o condizioni.

Il promemoria accanto alle osservazioni degli strumenti conserva natura, precisione,
tempo e limiti dei dati. Una lettura riuscita non sostiene qualsiasi conclusione,
una stima non è certezza fisica e un aggregato non dimostra assenza di criticità.
La sezione di sistema precedente era già inoltrata: non è stata trovata una perdita
del prompt. Questa è una precisazione delle istruzioni, da collaudare sul modello.

Il runner registra separatamente i controlli di risultato, Home, replay, owner e
isolamento anche quando il testo non supera il matcher. Il controllo semantico
originale e il suo FAIL restano obbligatori; un controllo non eseguito resta tale.
Non è una modifica al percorso di consegna dell'app o alle fonti sintetiche.

La configurazione Expo usa `EXPO_PUBLIC_EAS_PROJECT_ID` quando non è già presente
`extra.eas.projectId`, preservando gli altri campi. Sei verifiche sul resolver
effettivo passano; nessun ID, account o credenziale è stato inventato. Occorrono
l'UUID del progetto reale e un backend raggiungibile dal telefono per la build.

Verifica locale del candidato: **1.415 PASS, 1 SKIP, 115 moduli, 38,78 s**; scripted **9/9**, zero chiamate modello, HTTP modello ed effetti esterni.

Il test del nuovo report diagnostico è incluso nella CI v162. I controlli mirati
sono parte o sovrapposizioni della verifica completa e non vengono sommati.
Le sei prove EAS usano @expo/config 12.0.14, plugin attivi, copie temporanee,
ambiente sintetico e rete bloccata. La baseline aveva due FAIL sui casi env;
la patch e poi i file effettivamente modificati superano tutti e sei i casi.

La ricostruzione del prompt post-tool conserva tutte le altre chiavi e le due
osservazioni originali. Il sistema di 94.837 caratteri non cambia. La prova
osserva il callback reale _call_ai, non è una cattura HTTP storica del modello.
Le nuove istruzioni richiedono ancora la verifica reale del nuovo commit.

La nuova base `c59db28` (Vision PR 215) è integrata: i dodici file interessati
restano identici a quel commit. Non cambiano provider predefiniti, budget di
esecuzione, scheduler, dipendenze o schema del database. I limiti locali della
bozza e l'autenticazione letterale delle citazioni restano invariati; autenticità
non significa automaticamente supporto della conclusione.

Tarquinia resta la località confermata e la vecchia stesura resta chiusa. Il percorso
del bucato è coperto da motore reale con risposte sintetiche; non è ancora attestata
una prova unica con meteo/ricerca reali, attesa fisica e notifica nativa osservata.
La patch app Railway `eb9c3870` è bloccata dal rifiuto automatico precedente e non
viene aggirata tramite merge. La lettura primaria delle 09:22 UTC attesta backend
e web su `c59db28` (Vision), mentre la patch resta STAGED con cinque modifiche.
Il candidato di autonomia non è applicato all'app; il servizio tecnico è distinto.
Export e browser non provano firma, installazione o comparsa della notifica ad app chiusa.

## Artefatti e integrità

- `docs/evidence/autonomy_v162_live_2026-10-12_5b4efd5.json` — SHA-256 `c8fed7a830e4eadbe0e824d9123423b22825e703f37121219e17a4e35295d3be`.
- `docs/evidence/autonomy_v162_manual_review_2026-10-12_5b4efd5.json` — SHA-256 `9767af54efb9573b12bb022edd1e5597a2b2bcbc7f4a9e248e3abaaec4793cb6`.
- `docs/evidence/public_read_v162_live_2026-10-12_5b4efd5.json` — SHA-256 `ce4c1443faf594ae2a5a2362bd63b24d325868eed6bc1e39db68604722e02be8`.
- `docs/evidence/public_read_v162_manual_review_2026-10-12_5b4efd5.json` — SHA-256 `32a802235316ff76f8cb4356313dde5a5501a3a3e61eff9084d542de37142e04`.
- `docs/evidence/ci_v162_2026-10-12_5b4efd5.json` — SHA-256 `de8dac0ec4d8cb08b07efc8ba7d82b7cbbc83f8883419b7926436082de3131bf`.
- `docs/evidence/app_deployment_v162_2026-10-12_0922.json` — SHA-256 `816fb57c92d002875b3bad88bc4c34987d8695a81b624ee7266f39119569785d`.

---

# 12 ottobre 2026 — v162, calcoli conservati e qualificazione delle fonti

La prova reale del padre `96e8513` termina **6/9 macchina**, con **74 chiamate
logiche e 84 HTTP**. Dei quattro testi salvati come completati, due confronti
sono utili e sostenuti e due perdono una differenza necessaria durante l'audit.
La correzione Memory non produce un nuovo risultato: una clausola senza supporto
viene respinta, poi due bozze superano il limite locale. La CI dello stesso padre
è **15/15 job**, su cinque workflow, con **927 PASS v162**, **6 PASS Mongo reale**
e **36 PASS nei browser mobili**. Questi esiti non attestano il nuovo candidato.

## Riscontri reali preservati

| Scenario | Verdetto originale | Riscontro indipendente |
| --- | --- | --- |
| completed_result | FAIL | Il risparmio di 60 è nella generation ma sparisce nell'audit; goal completed. L'etichetta user_stated non soddisfa il matcher italiano di attribuzione. |
| planning_outage | PASS | Confronto utile con 180/120/60 e solo annuale non rimborsabile; Home e replay verificati. |
| home_write_retry | FAIL | Tre rifiuti strutturali del piano, poi lettura e preparazione. L'audit elimina 60; il controllo semantico interrompe prima della verifica completa del recupero Home. |
| source_revoked | PASS | Arresto e replay dopo revoca della fonte. |
| memory_revoked | PASS | Arresto dopo revoca Memory. |
| memory_corrected | FAIL | 150 corrente riletto; audit respinto per la clausola di flessibilità con citazioni vuote; bozze successive di 4.379/4.135 caratteri respinte. Nessun risultato salvato. |
| source_change_crash | PASS | Scan recuperato, lettura, confronto 180/120/60, Home e replay verificati. |
| already_resolved | PASS | Nessun goal riaperto. |
| irrelevant | PASS | Nessun goal creato. |

Le 24 citazioni presenti negli audit sono autentiche rispetto alla nota pertinente.
Nel ramo corretto, la riga sul calcolo di 30 cita correttamente 180 e 150;
la riga senza citazioni riguarda invece una flessibilità mensile non documentata.
Il controllo ha quindi respinto correttamente una conclusione non sostenuta.
Le bozze troppo lunghe sono rifiutate prima dell'audit; le code oltre i 4.000
caratteri non sono esportate dal runner e non sono ricostruite nella review.

La prova pubblica del medesimo head esegue due HTTP reali e sei chiamate al
modello. Mapbox restituisce 687 secondi e 2.765 metri; Open-Meteo 19 °C correnti
e fino a 23–24 °C nel pomeriggio. I numeri nella risposta hanno riscontro.
Il matcher legge il range `23-24°C` come `-24` e produce TEMPERATURE_MISMATCH:
quel FAIL rimane nell'originale. La review respinge separatamente la
«certezza da osservazione live» del traffico e la conclusione sulle condizioni
stradali favorevoli. I metadati di stima e tempo arrivavano già al modello.

## Correzione e confini

Il candidato chiarisce che un calcolo derivato cita gli operandi e le
condizioni della fonte: il risultato non deve essere già scritto nella fonte.
L'audit deve conservare i calcoli sostenuti e rendere conto delle eliminazioni
materiali. La diagnosi `preparation_protocol` descrive il precedente difetto di
formato, distinto dal supporto fattuale e dal contenuto della nuova bozza.
La richiesta di concisione evita ripetizioni senza troncare il testo nel codice.

La provenienza viene espressa in italiano comprensibile e le istruzioni della
conversazione conservano tipo, precisione, tempo e limiti del dato anche se il
provider è autorevole. Una lettura effettiva attesta la risposta ricevuta;
non trasforma una stima in osservazione fisica o il clock ORA nel tempo del provider.

Verifica locale del candidato: **1.407 PASS, 1 SKIP, 114 moduli, 36,59 s**; scripted **9/9**, zero LLM/HTTP/effetti.

I gruppi mirati da 126 e 60 test sono inclusi o sovrapposti alla verifica finale;
non si sommano. Lo skip finale riguarda un arricchimento opzionale senza chiave locale. Un primo comando mirato non ha avviato prove perché conteneva
un nome di modulo inesistente; corretto l'elenco, il gruppo è passato.
Il test clock falliva anche con i due moduli originali di 1505e5f: il fake usava
ora invece di message_to_user, causando il retry per empty_message. Allineato
quel solo campo, mantenendo due chiamate, timezone e clock aggiornato come assert.
Nessun nuovo test replica il testo delle istruzioni: la loro efficacia semantica
rimane affidata al successivo collaudo reale, con i criteri originari.

Fonti primarie consultate sul limite nativo, senza cambiare canale o provider:

- https://ai.google.dev/api/generate-content?hl=en — GenerationConfig, responseJsonSchema.
- https://ai.google.dev/gemini-api/docs/structured-output#json-schema-support — sottoinsieme documentato e validazione applicativa.

Nessun nuovo modello/default, campo operativo, chiamata, scheduler,
dipendenza, budget o modifica degli oracoli. Controlli di citazione, revisione,
owner, revoca e consenso invariati. Le modifiche alle istruzioni devono ancora
essere accettate sulla nuova revisione con modelli reali.

Tarquinia resta la località confermata e la precedente stesura resta chiusa.
Il verticale del bucato usa motore reale e risposte sintetiche; una prova unica
con frase, meteo/ricerca reali, attesa fisica e notifica nativa non è ancora
attestata. La patch app Railway `eb9c3870` resta bloccata dal rifiuto automatico;
non viene aggirata tramite il merge, che attiverebbe già il deployment dell'app.
L'ultima lettura primaria app delle 08:03 UTC attesta backend `389f38a` e web
`b159d8c`. Export e browser non attestano firma, installazione o ricezione nativa.

## Artefatti e integrità

- [File originale o review: autonomy_v162_live_2026-10-12_96e8513.json](evidence/autonomy_v162_live_2026-10-12_96e8513.json) — SHA-256 `23c1588cae43ddf4e65c1af933930c47940651e63220b23a62e3dc9940b3169e`.
- [File originale o review: autonomy_v162_manual_review_2026-10-12_96e8513.json](evidence/autonomy_v162_manual_review_2026-10-12_96e8513.json) — SHA-256 `916fb62fd2a0df7ddfa5cff5917b29bc231c81932785c67eadef7838cd056fe6`.
- [File originale o review: public_read_v162_live_2026-10-12_96e8513.json](evidence/public_read_v162_live_2026-10-12_96e8513.json) — SHA-256 `c8adb3312eff810dccd4c24f9981175937375da9f15958cc2f9e8327bf0ae55f`.
- [File originale o review: public_read_v162_manual_review_2026-10-12_96e8513.json](evidence/public_read_v162_manual_review_2026-10-12_96e8513.json) — SHA-256 `ad5328e66e862562326430bce68dc0ac2ddd61f65b8e23ce890e807ba5df7d59`.
- [File originale o review: ci_v162_2026-10-12_96e8513.json](evidence/ci_v162_2026-10-12_96e8513.json) — SHA-256 `5d5cd0cab7704cf4a0bf99f6b26d68e452a7802a75ff0be9aae4fef022a81c1b`.

Il file locale della nuova verifica è `evidence/autonomy_v162_local_derived_2026-10-12.json`.

---

# 12 ottobre 2026 — v162, citazioni e tempi verificabili; consegna recuperabile

## Candidato locale

**1.367 PASS, 1 SKIP, 109 moduli, 36,75 s**. La selezione comprende il gate v162 aggiornato, tre selettori di
visibilità v39, i moduli provider/recupero già inclusi e 50 moduli del nucleo di
autonomia della CI. Il solo skip è l'arricchimento Gemini opzionale senza chiave
locale. Nessun gate CI o test del repository è stato rimosso.

CLI scripted **9/9**, zero chiamate logiche/HTTP del modello e zero effetti
esterni. L'evidenza locale conserva il comando completo, i file verificati e i
rispettivi hash: `evidence/autonomy_v162_local_source_quotes_2026-10-12.json`.
CI e live di questo candidato sono ancora da eseguire sul commit pubblicato.

Nel primo aggregato, dopo 1.169 PASS e uno skip, il test di isolamento delle
lane v4 si è fermato: usava deliberatamente `object()` come database ma
sostituiva soltanto `admission.drain`, che ora è preceduto dal peek delle code.
La fixture sostituisce ora il vero ingresso `drain_with_receipts`; restano
intatti gli assert su assenza di sovrapposizione, limite dei job e cancellazione
durante lo shutdown. Nessuna modifica runtime per far passare quel test.

### Regressioni aggiunte

- Citazioni: **35 casi**, con RED 26 FAIL/9 PASS prima della correzione e un
  ulteriore RED isolato per un ID di altro owner. Autenticità nella sola riga del
  payload audit; quote inventate, metadati, fonti espulse, tipi e limiti non
  validi non possono certificare la bozza. Revoca/correzione e cancellazione
  restano attive. Una prova conserva il limite autentico ma non implicante.
- Pianificazione: **23 casi**, compresa ripresa dopo il piano invalido, unico
  owned read, fault Home realmente raggiunto e arresto al limite esistente.
  Riprodotta e corretta l'attribuzione a un nuovo attempt1 del journal di un
  ciclo precedente sullo stesso goal. Diagnosi omessa senza binding esatto.
- Routing pubblico: **9 casi nuovi**, RED 6 FAIL/3 PASS, poi **26/26** insieme al
  modulo pubblico esistente. Due percorsi attraversano adapter HTTP sintetico,
  capability reale, payload del modello e sessione riletta; numeri invariati,
  ora UTC della lettura e nessun istante di traffico inventato.
- Consumer autonomo: regressioni `test_agent_route_provenance_v162.py` verificano
  stima, clock attestato, età coerente e payload legacy senza orario ricostruito.
- Consegna Situation: **51 casi** in
  `test_situation_delivery_recovery_v162.py` riproducono giudizio iniziale
  indisponibile, rilettura temporanea del luogo, risposta tardiva dopo takeover,
  crash dopo il piano dell'ultimo tentativo, vecchi terminali, Need expired e
  precedenza del secondo owner nelle code miste. Ripristino del wake senza un
  quarto modello; scadenza/revoca e silenzio restano confini effettivi. L'autore
  ha verificato 92 PASS su cinque moduli, escludendo tre nodi Mongo reale v134;
  la review indipendente è di sola lettura. Il freeze successivo aggiunge
  **14 casi** per registrazione senza giudizio, dispatch con tre code, claim
  esatta, precedenza del secondo owner e handoff al secondo slot con clock
  aggiornato: **106 PASS su cinque moduli**, tre nodi Mongo reale esclusi.
  I 37 casi focalizzati su Delivery isolano esplicitamente il passaggio
  precedente, con Need già materializzata; le prove completion attraversano
  separatamente l'intera catena. L'aggregato sopra è quello del candidato
  finale, distinto dalle verifiche intermedie.
- Completamento e comunicazione: **22 casi** in
  `test_completion_visibility_recovery_v162.py`, con fonte temporaneamente
  illeggibile prima del giudizio, dopo il candidato e dopo la Home; riavvio
  senza riesecuzione del lavoro, None distinto dal silenzio, registrazione
  idempotente del Need e mancata chiusura quando il CAS della preparazione
  perde. Tre ulteriori RED durante l'await del modello (riapertura, nuova data
  di completamento, risultato diverso) sono chiusi dal controllo dell'identità
  corrente prima dell'ammissione: il candidato superato diventa stale.

Il replay della consegna già `delivered` nel database non va confuso con il crash
tra accettazione del provider e salvataggio della ricevuta locale. Il primo è il
confine coperto dal recupero del giudizio; il secondo non è chiuso da un plan_id
passato nei dati Expo e non viene dichiarato exactly-once. Nessun invio reale è
usato per queste regressioni.

Non cambiano modello/default, due chiamate di preparazione, contesto a 9.000,
bozza a 4.000, budget dei casi o oracoli di completamento. I fake positivi
conservano le affermazioni della propria fonte e tutti gli assert precedenti.
L'autenticità del passaggio non sostituisce la review semantica del testo.

## Prova reale definitiva 01ef500

Deployment tecnico `58224ab3-e932-4160-bd0b-12aa08cc96cb`, prova dalle
**07:10:44.195873** alle **07:13:08.469117 UTC** del 12 ottobre. **7/9 macchina**,
**48 chiamate logiche, 53 HTTP**. Risposte effettive: 33 Gemini
`gemini-flash-lite-latest`, 15 Mistral `ministral-8b-2512`; catena configurata,
senza override o inferenze su un presunto reset delle quote.

| Caso | Macchina | Revisione e limite |
| --- | --- | --- |
| completed_result | PASS | Testo accettato: prezzi 180/120/60 e non rimborso riferito solo all'annuale. |
| planning_outage | PASS | Testo respinto: estende il non rimborso anche al mensile. |
| home_write_retry | FAIL | OWNED_SOURCE_NOT_READ_ONCE; piano iniziale rifiutato, retry salvato; fault Home non ancora raggiunto. |
| source_revoked | PASS | Interruzione dopo revoca, nessuna ripartenza. |
| memory_revoked | PASS | Abbandono, nessuna nuova preparazione. |
| memory_corrected | PASS | Testo accettato dopo rilettura 150/30. |
| source_change_crash | FAIL | Scansione recuperata; piano rifiutato, retry salvato, nessuna lettura. |
| already_resolved | PASS | Nessun goal per il bisogno risolto. |
| irrelevant | PASS | Nessun goal per la fonte irrilevante. |

Due dei tre testi finali nella Home sintetica sono accettati; la review complessiva è
**non accettata**. In planning_outage la generazione Mistral (chiamata 6) introduce
la clausola mensile; l'audit (chiamata 7) la attribuisce alla fonte e la approva.
La successiva verifica non la elimina. Il controllo delle citazioni è motivato
da questa falsa attribuzione, senza promettere di dimostrare ogni implicazione.

Nessuna rivalutazione è stata chiamata nel trial: il recupero degli alias del
piano rivisto non è stato esercitato qui. I due piani iniziali rifiutati non
conservano il dettaglio completo del campo errato, che non viene indovinato.
La riproduzione isolata mostra che un wake successivo può recuperare il piano
e leggere la fonte una sola volta: il runner precedente si fermava prima.

Originale: `evidence/autonomy_v162_live_2026-10-12_01ef500.json`, SHA-256
`574d9e0efbfa318025ceec48fcf9256add96a2ec50c340f298528dacbb37b4f8`.
Review separata: `evidence/autonomy_v162_manual_review_2026-10-12_01ef500.json`.
Verdetti originali conservati. Il processo termina con 1 quando il gate fallisce;
Railway CRASHED non dimostra da solo un errore infrastrutturale.

## Roma Termini → Colosseo su 01ef500

Deployment tecnico separato `a8956e43-4188-48be-81e1-1f2eeb893192`: il primo gate
fallito interrompeva il comando concatenato. **Due HTTP provider**, Mapbox e
Open-Meteo, **quattro chiamate Gemini**, nessuna riscrittura. Machine PASS;
review manuale **non accettata**. Distanza 2.765 m e durata 759 s sono coerenti con
la risposta, ma il testo qualifica il viaggio come “certezza osservata” e lega
il traffico all'istante esatto della verifica. Il provider non ha consegnato
quell'istante di osservazione. Il clock HTTP del runner non era metadata dato
al modello. Il meteo datato è coerente con la risposta effettiva.

La documentazione primaria Mapbox definisce `duration` come tempo stimato e il
profilo `driving-traffic` combina traffico corrente e storico:
https://docs.mapbox.com/api/navigation/directions/ (consultata 12 ottobre 2026).
I metadati aggiunti nel candidato non trasformano una stima in una misurazione.

Originale: `evidence/public_read_v162_live_2026-10-12_01ef500.json`, SHA-256
`1fbe249e89738f0d0b0956949b47d3fa782fb35288d3505dc3b4d878d7ca46c8`.
Review: `evidence/public_read_v162_manual_review_2026-10-12_01ef500.json`.
Il comando tecnico standard è stato ripristinato dopo la prova separata.

## CI, integrazione Vision e app effettiva

`01ef500`: due workflow push, **7/7**. La base effettiva era avanzata con Vision
PR #213 e i workflow PR non partivano durante il conflitto; nessun controllo
mancante è stato contato come riuscito. Il merge `6e6e5b7` preserva tutti i 19
file Vision non documentali e concatena le quattro note canoniche senza perdite.
Tree `f231fee6d4b5277a80921700b29f85e5baa4231f`, identico al locale e al merge
tecnico `a9a60e371308c59e7f1fb0716a64c6e763f8b511`.

CI `6e6e5b7`: **quattro workflow, 13/13 job**. Nel backend PR: nucleo 286,
v162 776, scripted 9/9, MongoDB reale 6 con `PHASE2_REAL_MONGO=1`. Mobile browser
**36/36**, Chromium e WebKit. Non è una prova nativa né la CI delle nuove
correzioni. Evidenze: `ci_v162_2026-10-12_01ef500.json` e
`ci_v162_2026-10-12_6e6e5b7.json` nella cartella `evidence`.

La base è avanzata ancora con Vision PR #214 (`389f38a`): soltanto
`backend/vision_xray.py` e `backend/vision_tests/test_catalog.py`, integrati
esattamente nel candidato, senza conflitti. La CI Vision conserva il collaudo
con Mongo reale; quei test non sono contati nel risultato locale di autonomia.

App osservata alle 08:03 UTC: backend **389f38a**, web **b159d8c**; il nuovo evento
web è SKIPPED e non sostituisce il deployment SUCCESS precedente. Patch
`eb9c3870` ancora STAGED con cinque modifiche. Prova primaria in
`evidence/app_deployment_v162_2026-10-12_0803.json`; conservata anche la lettura
storica delle 07:38. Nessuna azione sui servizi app è stata eseguita da queste
letture. Il precedente rifiuto automatico della patch non viene aggirato tramite
un altro deploy, incluso un merge con trigger.

Restano necessari risultati reali accettabili sul nuovo commit, revisione dei
testi e consegna nativa visibile. Firma/configurazione EAS, installazione e
registrazione dispositivo non sono attestate da export o test browser. Nessun
push reale, pagamento, telefonata, prenotazione o evento calendario reale.
Il vecchio bucato Tarquinia resta chiuso.

---

# 12 ottobre 2026 — v162, schema nativo e piano di recupero: gate ancora aperto

## Candidato che contiene questa nota

La verifica locale finale è **1.088 PASS, 1 SKIP, 95 moduli, 97 selettori, 33,49 s**.
Il CLI scripted esegue tutti i nove casi con **9/9 PASS, zero chiamate logiche o
HTTP del modello e zero effetti esterni**. Il file
`evidence/autonomy_v162_local_native_protocol_2026-10-12.json` conserva comando,
hash del codice verificato, conteggi e limiti del controllo. CI e live del nuovo
commit sono pendenti: i conteggi locali non li sostituiscono.

La selezione comprende il gate v162 aggiornato, tre controlli di visibilità v39,
i moduli di recupero/provider e 50 moduli del nucleo di autonomia della CI.
Lo skip è l'arricchimento Gemini opzionale senza chiave locale. Un tentativo
aggiuntivo sull'intero `test_research_v34.py` ha raggiunto un caso che richiede
MongoDB reale, assente localmente. Quel modulo extra non fa parte del conteggio
finale; non sono stati disabilitati test del repository o gate CI. Il gate
previsto con database reale resta da eseguire nella CI del nuovo head.

## Difetti riprodotti e copertura

| Area | Difetto e correzione | Nuovi casi |
| --- | --- | ---: |
| Rivalutazione | La vista usa `type`, il lettore richiedeva `step_type`; gli alias includono anche parametri/cursori/effetti. Normalizzazione rigorosa e validazione atomica dell'intera modifica. | 27 |
| Trasporto | Contratto opzionale inoltrato fino alle richieste SDK/HTTP native, conservato al failover e non aggiunto alle chiamate legacy. Nessun downgrade silenzioso. | 30 |
| Preparazione | Schemi distinti per generazione e audit, ID limitati al payload dopo ogni riduzione; risposte negative consentite e guardie locali mantenute. | 9 |
| Diagnostica | Le decisioni recenti potevano espellere generazione e audit dalla finestra. Conservazione entro lo stesso limite, con identificativi di esecuzione. | 2 |

Le tre fixture positive di `test_agent_preparation_v4.py` ora restituiscono l'ID
del candidato reale invece di una stringa vuota. Le asserzioni su consenso,
ripartenza e fonte cambiata non sono state modificate. Le altre fixture toccate
accettano soltanto l'argomento opzionale `response_schema`.

Gli schemi controllano la forma della risposta, non l'implicazione logica tra
fonte e conclusione. Il limite di 4.000 caratteri resta applicato localmente.
Una dichiarazione del modello `verified=true` non basta a superare la review
manuale; nessun recupero inventa la fonte mancante o esegue un passo diverso.

## Prova reale definitiva del padre 3b7c4d7

Deployment tecnico `de19da6a-4ad6-4594-b342-7a15726d1fc7`, dal
12 ottobre 2026 **06:30:56.964433 UTC** alle **06:38:33.868307 UTC**.
Report completo recuperato dopo il ritardo dei log: **4/9**, **86 chiamate logiche,
94 HTTP**. Risposte: 84 Mistral `ministral-8b-2512`, una Groq
`qwen/qwen3.8-27b`, una OpenAI `gpt-4o-mini`, entro la catena già configurata.
Nessun passaggio a un nuovo modello predefinito o attivazione di fatturazione.

| Caso | Esito macchina | Osservazione rilevante |
| --- | --- | --- |
| completed_result | FAIL — OWNED_SOURCE_NOT_READ_ONCE | Piano iniziale e proposta modificata preparano/verificano senza leggere la fonte. |
| planning_outage | FAIL — COMPLETION_BUDGET_EXHAUSTED | Recupera il guasto di pianificazione e salva una bozza, ma resta in verifiche parziali; la bozza include clausole non fondate. |
| home_write_retry | FAIL — COMPLETION_BUDGET_EXHAUSTED | Generazione di 4.394 caratteri, rifiutata prima dell'audit; il guasto Home non viene raggiunto. |
| source_revoked | PASS | Revoca dopo la lettura: lavoro interrotto, senza nuova attivazione. |
| memory_revoked | PASS | Revoca Memory dopo la lettura: goal abbandonato, senza nuova preparazione. |
| memory_corrected | FAIL — COMPLETION_BUDGET_EXHAUSTED | Rilegge la correzione 150/30; l'audit restituisce un oggetto come contenuto, correttamente rifiutato. |
| source_change_crash | FAIL — COMPLETION_BUDGET_EXHAUSTED | Recupera scansione e goal; l'audit restituisce ancora contenuto oggetto, rifiutato. |
| already_resolved | PASS | Nessun goal per un bisogno già risolto. |
| irrelevant | PASS | Nessun goal per un elemento irrilevante. |

I quattro PASS sono tutti controlli negativi. **Zero completamenti positivi
accettati manualmente.** In nove decisioni `modify`, tutti i 13 passi rivisti
visibili nella diagnosi usano `type` e nessuno dichiara `step_type`; il replay
diagnostico non ne accetta alcuno. Le righe diagnostiche sono parziali e non
sostituiscono i payload integrali: i nuovi test verificano anche oggetti completi
e parametri realmente esposti.

La bozza di `planning_outage` inventa flessibilità, condizioni di disdetta e
possibili rimborsi del mensile. Cinque osservazioni iniziali, comprese generazione
e audit, non erano più conservate; non è possibile attribuire l'origine delle
singole frasi a uno dei due passaggi. Nel caso `source_change_crash` l'audit
attribuisce invece alla Memory una citazione su assenza di vincoli e rimborso
proporzionale che la fonte non contiene. I prezzi corretti non rendono valido
questo contenuto aggiuntivo.

File immutati nei verdetti:
- `evidence/autonomy_v162_live_2026-10-12_3b7c4d7.json`
- `evidence/autonomy_v162_manual_review_2026-10-12_3b7c4d7.json`
- `evidence/ci_v162_2026-10-12_3b7c4d7.json`

SHA-256 del report originale:
`3193ae4777d1285e86a8f7557ee3f2abca8fc2551d4f7fd0b5cfa6b4bf268513`.
Il processo del runner restituisce 1 quando almeno un caso fallisce; lo stato
Railway CRASHED è compatibile con questo gate non superato. Non è una diagnosi
di OOM o di indisponibilità del servizio. Il test pubblico Roma Termini → Colosseo
non è partito, perché concatenato con `&&` dopo il gate fallito.

## CI del padre e criteri per proseguire

Cinque workflow, 15 job: **11 SUCCESS, 2 FAILURE, 2 SKIPPED**. Le due failure
backend sono le fixture con ID vuoto corrette nel candidato. I successivi gate
v141/v142/v162 e MongoDB reale non erano stati raggiunti. Mobile **36/36**:
18 Chromium e 18 WebKit. Non attribuire questi risultati a un commit successivo.

Prima del merge servono CI verde del commit esatto, prova reale bounded con
risultati corretti e review manuale di tutte le fonti/bozze disponibili, incluso
il controllo pubblico indipendente. Restano fuori da questa prova sintetica
account utente reali, invii effettivi, calendario reale e consegna su dispositivo.
L'app non è stata rilasciata: il controllo automatico ha rifiutato l'approvazione
della patch Railway. Nessuna nuova prova riapre il vecchio bucato di Tarquinia.

---

# 12 ottobre 2026 — v162, decisioni valide e contesto conservato

Verifica locale congelata: **811 PASS, 1 SKIP, 47 moduli, 28.88 s**. CLI scripted **9/9**, zero chiamate LLM/HTTP del modello ed effetti esterni. Lo skip resta il solo `test_real_gemini_enrichment`, opzionale senza chiave locale. Frontend: **14/14 Node** (calendario e review), **18/18 Chromium** su export di produzione, guard Home3, TypeScript, lint mirato ed export riusciti. WebKit e il gate dei 36 scenari sono da verificare nella CI del nuovo candidato.

Le scelte execute/skip riferite a passi mancanti o non più eseguibili non possono
eseguire o saltare un altro passo per fallback. La decisione invalida ritorna alla
rivalutazione ordinaria con una diagnosi bounded, entro gli stessi budget.
Il modello mantiene la scelta di continuare, modificare, chiedere o attendere.

Le risposte di preparazione con tipi/citazioni non validi continuano a essere
rifiutate. Il recupero conserva una diagnosi strutturale specifica al contesto,
senza convertire oggetti in testo, inventare una bozza o trattare feedback come
fonte. La valutazione precedente dell'esito di un'opportunità resta disponibile
all'ammissione come contesto del modello non autorevole: è separata dalle fonti
correnti e non impone la creazione del goal né annulla un no_goal valido.
Il binding riguarda la revisione della proposta, owner e riferimenti citati;
non introduce un nuovo digest delle Memory. AgentService.consider continua
a rileggere le fonti correnti e a mostrarle separatamente al modello.

La scelta successiva tenta ora la condivisione esatta di testo e tabelle
ricostruibili anche quando non esiste ancora una preparazione corrente.
In quel percorso non sono consentite omissioni di storia generata o descrizioni
dei passi conclusi; fonti, cursori, limiti, criteri e orologio restano integrali.
Un contesto materiale ancora troppo grande resta indisponibile. Il confronto
di copie distingue anche booleani e numeri, che Python considera altrimenti uguali.

Il rapporto 14B mostra tre scelte senza risposta e senza una nuova chiamata al
modello dopo la lettura riuscita nel caso source_change_crash. Non conserva
il payload integrale. La riproduzione locale è quindi dichiaratamente sintetica,
costruita da repository e reader reali: dimostra che il solo dedup dei candidati
può eccedere 9.000 caratteri mentre la condivisione esatta consente di consegnare
le medesime informazioni allo SDK. Non viene presentata come cattura HTTP storica.

Il calendario Home normalizza la risposta dei giorni prima di usarla come array.
Un payload oggetto non crea eventi né provoca il crash del dettaglio. La prova
browser attende ora il callback Home effettivo prima della navigazione; la fixture
malformata e l'asserzione sugli errori restano intatte. I vecchi 4/4 locali avevano
lasciato sfuggire questo problema di tempi. Le fixture v141 persistono il goal
prima del controllo della concorrenza o dell'assenza di prove, mantenendo gli assert.
Il vecchio test unitario v4 che prescriveva il fallback su un altro passo viene
aggiornato a verificare il rifiuto della scelta invalida e gli stati immutati.
Il vecchio test di contesto con stesso id e definizioni diverse non richiede
più indisponibilità quando le informazioni entrano senza perdite: richiede
il ripristino integrale e tipizzato di entrambe le definizioni e la decisione
invariata. L'overflow materiale distinto continua a impedire la chiamata.

## Esiti conservati e limiti della prova

Il candidato `2e848b6` ha **5/9 PASS automatici**, 69 chiamate logiche e 88 HTTP;
**non è accettato alla lettura manuale**. Il testo di completed_result contiene
calcoli 180/120/60 corretti, ma inventa condizioni mensili di disdetta, rimborso
e assenza di vincoli. La generazione introduce parte dell'errore e l'audit lo
conferma/aggrava. Il PASS bounded non copre queste clausole. I tre casi
planning_outage/home_write_retry/memory_corrected esauriscono il budget;
source_change_crash recupera Discovery ma riceve un no_goal non sostenuto.
Le 69 risposte riuscite sono 59 Mistral e 10 Groq, nessuna Gemini: disponibilità
della risposta e completamento utile sono misure distinte.

La CI `2e848b6` è **10 PASS / 3 FAIL / 2 SKIP**, cinque workflow. I Backend si
fermano sulla fixture v141 prima dei gate v162/Mongo successivi. Mobile è
34/36 (17/18 per motore); i due fallimenti malformati nascono dal calendario
Home. Questi sono esiti della revisione precedente, non CI verde del candidato.

Le letture pubbliche separate sullo stesso `2e848b6` eseguono due HTTP reali
(Mapbox/Open-Meteo), cinque chiamate LLM e 68.520 ms di loop. Tecnico PASS,
semantico FAIL per MODEL_CLAIM_REWRITTEN. Il rapporto non conserva il messaggio
originale prima della riscrittura: la sola risposta finale non permette di
ricostruire quella frase. Il primo avvio separato aveva omesso la dipendenza
mongomock-motor dal comando e si è fermato con ModuleNotFoundError; il comando
corretto installa la medesima versione 0.0.36 già usata nella prova completa.

**Rettifica dell'interpretazione del vecchio rapporto pubblico d5:** il pattern
`intensi` intercetta l'inizio di «intensità» nella corretta negazione «non è una
misura dell'intensità». UNVERIFIED_FORECAST_INTENSITY è un falso positivo su
quel testo. MODEL_CLAIM_REWRITTEN include anche il rendering di messaggi
strutturati e il rapporto non conserva l'originale: non dimostra da solo una
specifica affermazione meteo falsa del modello. Il vecchio report resta FAIL;
fixture, oracle e risultati originali non vengono riscritti.

Il confronto diagnostico con LLM_PROVIDER=mistral e
MISTRAL_MODEL=ministral-14b-2512 usa sempre il codice `2e848b6`, gli stessi
nove scenari, budget e confini: **5/9 PASS automatici,
53 chiamate logiche / 65 HTTP**. È una configurazione del
solo servizio di collaudo: la catena ha usato anche fallback Groq e OpenAI,
quindi non tutte le risposte sono del modello 14B. Non dimostra da sola
il comportamento dei servizi app né sostituisce la lettura delle risposte
o il collaudo del codice successivo. Le preferenze free-first restano valide:
nessun default dell'app, account, fatturazione o servizio a pagamento viene
attivato o cambiato da questa prova.

Anche i due risultati positivi di questa diagnostica non sono accettati
alla revisione manuale. completed_result conserva flessibilità e costi
proporzionali non documentati, oltre a soglie temporali incoerenti: generazione
14B, audit GPT-4o-mini. memory_corrected usa correttamente la nuova cifra
150 e la differenza 30, ma confronta il rischio sulla base di vincoli mensili
assenti dalla fonte: generazione Groq/Qwen, audit GPT-4o-mini.
La correzione della fonte e il salvataggio funzionano; la fedeltà semantica
non è dimostrata e non viene certificata dai controlli di formato o citazioni.

Nei tre casi planning_outage/home_write_retry/memory_revoked della diagnostica
14B, il fallback propone una preparazione senza lettura. Nei casi Home e
revoca il gate si ferma prima di quelle iniezioni; il guasto di pianificazione
è già stato iniettato nel suo caso. I goal conservano una scadenza di recupero. Il vecchio report non esporta revised_steps e non consente
di dedurre perché modify non abbia aggiunto passi. La diagnostica del prossimo
collaudo registra separatamente formato e passi di rivalutazione, entro gli
stessi limiti e guard del solo owner sintetico, senza cambiare il verdetto.

Report e annotazione separata:

- [Collaudo originale 2e](evidence/autonomy_v162_live_2026-10-12_2e848b6.json)
- [Revisione manuale 2e](evidence/autonomy_v162_manual_review_2026-10-12_2e848b6.json)
- [Letture pubbliche 2e](evidence/public_read_v162_live_2026-10-12_2e848b6.json)
- [Diagnostica Ministral 14B](evidence/autonomy_v162_ministral14b_live_2026-10-12_2e848b6.json)
- [Revisione manuale della diagnostica 14B](evidence/autonomy_v162_ministral14b_manual_review_2026-10-12_2e848b6.json)

## Confine del rilascio

Merge soltanto con CI verde e risultati reali accettabili sul candidato.
Nessun dominio/keyword router, nuovo scheduler, reset dei budget o azione esterna
reale nel collaudo. Il bucato precedente di Tarquinia resta chiuso. Un nuovo
bucato deve condurre all'avviso utile di ritiro, distinguendo stima di asciugatura
e ritiro anticipato per rischio.

I servizi app non sono stati aggiornati: la patch Railway è preparata ma
l'applicazione è stata rifiutata dal controllo automatico. Il servizio isolato
di valutazione non applica quella patch. Backend resta al commit 9e1a2f0,
web a 9dc0d65. Configurazione/prebuild/export iOS in CI non sono firma,
installazione o ricezione su dispositivo. Mancano accesso al progetto EAS e
credenziali native; registrazione, app chiusa, avviso visibile e apertura del
risultato sul dispositivo restano da verificare. Nessun push reale inviato.

---

# QA v162 — review persistita e consegna della preparazione corrente

## Verifica congelata del candidato successivo a d5

**757 PASS, 1 SKIP, 43 moduli, 28.27 s**; CLI scripted **9/9**, zero chiamate LLM/HTTP del modello ed effetti esterni.

Nuovi moduli: snapshot/review/CAS, consegna, diagnostica delle catene LLM
e classificazione Gemini/RetryInfo. Il gruppo include anche v55, i tre
controlli statici di visibilità corretti e le regressioni del Provider Manager.
Lo skip è solo `test_real_gemini_enrichment`, opzionale e privo di chiave locale;
le prove live sul servizio isolato hanno un esito separato.
I risultati mirati sono inclusi nel totale. La UI ha 7 nuove prove Node più
UpdateActions (8/8), 4 prove Chromium sui due giudizi, approvazione e dati
malformati, tsc ed export riusciti. I due screenshot sono stati ispezionati:
avviso e mancanza leggibili sopra il testo. WebKit resta alla CI del candidato.

## Gate reale d5 originale

Il gate reale d5b5e1e è **4/9 PASS**, con **80 chiamate logiche e 106 HTTP**.
La precedente CI d5 è **10 PASS / 2 FAIL / 2 SKIPPED**: i due Backend si sono
fermati sulla firma obsoleta del fake v55 (1 failed / 282 passed), prima dei gate
v162 e Mongo. Questa compatibilità è corretta nel candidato successivo; non
si attribuisce a d5 una CI verde. Il [report originale](evidence/autonomy_v162_live_2026-10-12_d5b5e1e.json)
rimane integralmente disponibile. L'autonomia dell'app non è ancora dimostrata.


| Caso | Esito | Chiamate logiche / HTTP | Evidenza |
|---|---|---:|---|
| completed_result | FAIL | 11 / 20 | Goal chiuso, ma manca la differenza numerica utile. |
| planning_outage | FAIL | 23 / 33 | Bozza salvata; il verifier rimanda a una verifica formale e il riesame ripete complete. |
| home_write_retry | FAIL | 5 / 6 | prepare con information.read non esegue la lettura; il guasto Home non viene raggiunto. |
| source_revoked | PASS | 5 / 5 | Revoca rispettata. |
| memory_revoked | PASS | 5 / 7 | Revoca rispettata. |
| memory_corrected | FAIL | 27 / 29 | Fonte corretta a 150; secondo document.create execute e ciclo di verifica. Testo con flessibilità non sostenuta. |
| source_change_crash | FAIL | 2 / 4 | L'audit crede alla proposta «già preparato»; nessun goal recuperato. |
| already_resolved | PASS | 1 / 1 | Non riapre il lavoro chiuso. |
| irrelevant | PASS | 1 / 1 | Non crea lavoro non pertinente. |

La verifica manuale non accetta le clausole non sostenute anche quando i
numeri passano. Il nuovo codice non riscrive i testi del report.

## Letture pubbliche separate, codice d5

[Report originale](evidence/public_read_v162_live_2026-10-12_d5b5e1e.json).
Deployment `f59f67dc-a65f-492e-b0aa-e2ad4271e1de`, pin d5 verificato.
Roma Termini → Colosseo, account/stato sintetici. **2 letture provider reali**
(Mapbox e Open-Meteo), **4 chiamate LLM**, 40.482 ms di loop.
Gate tecnico PASS; gate semantico FAIL: UNVERIFIED_FORECAST_INTENSITY e
MODEL_CLAIM_REWRITTEN. La risposta finale riscritta dalla protezione distingue
probabilità e intensità; questo non cancella l'errore del modello. Nessuna
operazione bloccata o effetto esterno. Nessuna verifica di luoghi privati.

Un primo redeploy tecnico `17ce8308-0579-4d03-845a-2bad831dd8bf` aveva
riutilizzato il comando completo precedente, non il comando pubblico aggiornato.
È stato sostituito collegando di nuovo il pin: il solo progresso registrato
è completed_result FAIL, 18 chiamate / 26 HTTP. Esecuzione incompleta,
non utilizzabile come gate e non aggiunta ai risultati completi.

## Smoke isolato del profilo Gemini 3.8, codice d5

[Report originale](evidence/autonomy_v162_gemini38_smoke_2026-10-12_d5b5e1e.json).
Deployment `eae276c4-8ce7-485c-8734-d0e3dc9a07f0`. Override temporanei
GEMINI_MODEL/GEMINI2_MODEL=gemini-3.8-flash e
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite; nessuna modifica ai servizi app.
Solo completed_result: **FAIL**, 11 chiamate / 19 HTTP.
8 risposte Mistral, una OpenAI, una Groq e soltanto l'ultima Gemini 3.8
(visibilità). Non è un confronto affidabile della qualità tra modelli:
la bozza e la verifica non sono state svolte dal profilo atteso. Il testo
omette attribuzione e limiti, estende indebitamente il vincolo di rimborso
ed è stato erroneamente chiuso. I dati vengono conservati senza correzione.

## Correzioni e confini

Una verifica parziale o incerta di un risultato interno viene conservata sul
preciso artefatto che il verificatore ha letto. Una nuova preparazione riceve
una nuova identità anche se il testo è identico. Testo, citazioni e contesto
vincolano il giudizio; una risposta tardiva non può sovrascrivere una nuova
bozza. Una successiva verifica positiva dello stesso artefatto ritira la
critica insieme alla chiusura autorizzata, prima del cleanup.

Home, comunicazioni in coda e apertura di un vecchio avviso rispettano la
preparazione corrente e il suo giudizio. Le domande su informazioni o autorità
rimangono possibili quando il goal corrente ne ha davvero bisogno. Un errore
di lettura conserva la possibilità di riprovare. Il dettaglio mostra
«Bozza da rivedere» oppure «Verifica ancora incerta», con ciò che manca sopra
il testo, senza nascondere le bozze da approvare.

Le istruzioni distinguono ora esplicitamente lettura, preparazione salvata
e azione esterna: nominare una capacità di lettura su un passo prepare non
esegue la lettura. La verifica finale deve valutare il contenuto adesso; un
passo di verifica ancora pendente non è da solo una mancanza sostanziale.
Il confronto deve esplicitare le differenze utili e i calcoli sostenuti dalle
premesse. Discovery non può usare una propria proposta al passato come
prova che un lavoro sia stato svolto. Queste correzioni sono generali;
fixture, oracolo, budget e decisioni negative del modello restano invariati.

Il report osserva al massimo 40 esiti di chiamate logiche e 8 fallback per esito. Esporta soltanto sequence, outcome, provider e failure_kind da allowlist, elapsed_ms e la catena limitata. Sul successo usa usage.failover_errors della risposta corrente; sul fallimento, attempts dell'eccezione corrente. Non legge _last_attempts. Lo scope è manager_reported_final_chain: non pretende di ricostruire gli skip per cooldown, le precedenti catene di pacing o ogni retry interno del SDK. elapsed_ms comprende l'intera chiamata logica, inclusi fallback e pacing. Payload, prompt, URL, credenziali e messaggi d'errore restano esclusi; contatori, budget, gate ed eccezioni non cambiano.

La classificazione Gemini dei 429 usa QuotaFailure tipizzata: solo un periodo giornaliero esplicito in quotaId/quotaMetric attiva quota, con precedenza nelle violazioni miste. Gli altri 429 restano rate_limit. RetryInfo richiede il tipo RPC esatto e una durata JSON finita e non negativa; il massimo degli hint validi HTTP/RPC resta entro il cap di 300 secondi, senza cambiare la politica del Manager. Il nuovo modulo ha riprodotto 27 FAIL / 31 PASS prima della correzione e 58/58 PASS dopo, inclusi SDK reale con HTTP sintetico e recupero del Manager con orologio finto. Questi casi sono inclusi nell'aggregato, non si sommano.

Il default alternativo passa da gemini-2.0-flash a gemini-3.6-flash, sostituto indicato nella [tabella ufficiale Gemini](https://ai.google.dev/gemini-api/docs/deprecations). Principale, override, priorità, timeout e budget rimangono invariati. La correzione di un endpoint ritirato non prova disponibilità o qualità sul progetto reale, e non viene attribuita retroattivamente ai fallback d5. Configurazione e fonti del protocollo sono nel [riferimento del Provider Manager](AI_PROVIDER_MANAGER.md).
La compatibilità v55 aggiorna soltanto la firma del fake e verifica None/[]
sul percorso senza bozza. Il guard statico conserva un pass quando rimuove
docstring da un corpo vuoto e riconosce vere scritture dell'outcome; non confonde
ActionStep.step_type con visibilità. Campioni leciti e illeciti provano il matcher.

La patch di rilascio dei servizi app rimane preparata ma non applicata:
il controllo automatico Railway ha rifiutato l'azione e non viene aggirato.
Il servizio di valutazione isolato non equivale all'app rilasciata.
Build nativa firmata e ricezione su un dispositivo rimangono prove distinte.
Il precedente bucato di Tarquinia resta chiuso; per un nuovo bucato il risultato
atteso è il momento utile per ritirarlo, con stima e rischio anticipato distinti.


---


# QA v162 — recupero fino alla correzione e consegna corrente

## Candidato successivo a e3a: verifica locale

**569 PASS su 34 moduli in 7,68 secondi**, più CLI scripted **9/9**, con zero chiamate LLM reali, HTTP del modello ed effetti esterni.

Le nuove prove coprono il risveglio, le critiche persistite, la verifica
finale incompleta, il contesto dopo la preparazione e la revoca della fonte
durante il passaggio in Home. La CLI conserva nove scenari e la fixture
`personal_outcome_v1`. I risultati delle prove mirate sono inclusi nel totale;
il trasporto SDK con HTTP finto non è una prova di qualità del modello reale.

### Correzioni e prova del difetto precedente

**Risveglio.** Due riproduzioni iniziali fallivano precisamente perché
`next_run_at` diventava `None` dopo un giudizio assente o un JSON non valido.
Il nuovo modulo verifica il checkpoint persistito, `recover_due`, un nuovo
worker e il completamento senza rilettura superflua. Attesa deliberata,
richiesta di informazioni/autorità, cap background e revoca prevalgono.

**Critica disponibile al recupero.** La diagnosi conserva solo `reason` e campi tipizzati di `claim_review`, fino a 1.400 caratteri nel journal esistente e 600 nell'osservazione immediata. Owner, goal, scadenza e hash di requisiti, Evidence e snapshot Memory delimitano il riuso dopo reload. Fonti corrette, requisiti cambiati o una preparazione riuscita ritirano la critica precedente. `reconsider` e la nuova preparazione la ricevono separatamente come contesto fallibile; la diagnosi facoltativa viene omessa prima di sacrificare materiale corrente quando supera il budget. Un journal indisponibile non blocca il risultato né elimina la critica immediata. Le 16 prove attraversano i percorsi ordinario e fallback, isolamenti, TTL, versioni, forme malformate e overflow; nessuna bozza respinta viene salvata come risultato o Evidence. La provenienza di ogni tentativo `unavailable` dichiara ora che quel tentativo non ha salvato una nuova bozza; l'errore `preparation_sources_required` precisa l'assenza di Evidence utilizzabili per il goal. Restano invariati provider, classe e retryable. Cinque prove esistenti erano rosse sulla vecchia nota di successo e ora verificano il resoconto coerente che raggiunge la rivalutazione.
Le riproduzioni iniziali dei percorsi ordinario e fallback fallivano perché
la rivalutazione riceveva solo `preparation_not_supported` e un messaggio
generico. Non vengono salvati come risultato né come fonte i testi respinti.

**Verifica finale.** Nel solo risultato interno già preparato, senza intenti o ricevute esterne, i verdetti `partially_achieved` e `uncertain` raggiungono `_reconsider` con motivo, mancanza e critica persistita. Il budget resta quello esistente: al limite la prosecuzione è salvata senza chiamate extra. `wait`, `ask`, `continue` e piano modificato conservano i loro esiti; una nuova preparazione deve passare nuovamente audit e verifica. I rami di completamento, fallimento e attesa esterna rimangono invariati. Le 15 prove verificano recupero dopo reload, limiti e revoche. Le sei compatibilità dei test precedenti isolano soltanto la rivalutazione successiva fuori dal loro contratto, lasciando integro il primo recupero reale. Il percorso principale controllato rende la visibilità silenziosa: non attesta un nuovo veto globale di Delivery sulle bozze attive.
Il verdetto negativo non viene cambiato per ottenere un completamento:
un'eventuale nuova bozza attraversa nuovamente preparazione, audit e verifica.

**Contesto.** `_next` passa testo salvato e citazioni correnti al chooser e dà priorità alle Evidence citate. Entro gli stessi 9.000 caratteri, i serializer dedicati eliminano soltanto frammenti generati non citati e `intent`/`expected_result` dei passi conclusi; tutte le note operative rimangono. Testo di anteprima e `why_now` vengono condivisi soltanto quando identici, con riferimenti espliciti e metadati separati. Tabelle limitate a passi e capability conservano campi comuni, colonne, righe e indici dei campi assenti, distinguendo assenza, null, booleani e numeri. I candidati fanno riferimento al piano soltanto con una definizione unica e identica. Fonti, risultato, criteri, limiti, effetti e cursori restano ricostruibili; materiale essenziale ancora eccedente o citazione mancante produce indisponibilità prima del modello. Le 14 prove includono i testi originali e3a: chooser 11.409→8.968 e 18.115→8.952 caratteri, verifier 9.992→8.225 e 16.698→8.554, su ricostruzioni dichiarate. Il contratto comune descrive `current_source_situation` come snapshot che può includere interpretazioni dell'AI: i suoi riepiloghi non attestano una lettura eseguita o un risultato già salvato. Questa qualificazione non aggiunge campi ai payload.
La ricostruzione controllata del percorso reader/store/executor, usando i
testi originali e3a, mostrava un chooser di 10533 caratteri per il testo Home
di 790 e di 14986 per quello di 2813, entrambi rifiutati prima del modello.
Il secondo payload di verifica misurava 16698 caratteri ed era a sua volta
rifiutato. Non sono catture delle richieste HTTP storiche: obiettivo e
descrizioni del piano sono una ricostruzione esplicita. Gli input essenziali
rimangono interi; l'eccedenza realmente non comprimibile resta indisponibile.

**Home.** Tre riproduzioni iniziali confermavano consegna o visibilità dopo
revoca/soppressione. Il controllo corrente è condiviso con Delivery e viene
ripetuto dopo gli await pertinenti. La lettura Home controlla anche l'outbox
saltata. Le prove coprono fonte mancante, altro owner, scadenza, guasto del
database, replay dopo revoca e chiusura dell'outbox da un altro worker prima
dell'ack. Il goal completato non viene falsificato per chiudere l'outbox.

## Collaudo reale e3a: report originale

Revisione `e3a843c2730d4a35708777f81e403b8b5f89868a`, albero
`c18c4300513a101fae5f03ac6d409e95c39c8dcc`, deployment tecnico
`9080e411-301f-4f4f-82dc-33004332dd57`. Esecuzione dalle
**04:15:51.987508 alle 04:26:10.832990 UTC del 12 ottobre 2026**:
**4/9 PASS**, **67 chiamate logiche e 98 HTTP**. Il [report originale](evidence/autonomy_v162_live_2026-10-12_e3a843c.json)
è stato recuperato da due frammenti consecutivi, JSON valido di 132322
caratteri e revisione esatta verificata. Le letture pubbliche non sono state
eseguite, perché successive al superamento di questo gate.

| Caso | Esito effettivo | Revisione del risultato e punto di arresto |
|---|---|---|
| `completed_result` | FAIL, budget esaurito | Prima bozza valida respinta; secondo audit salva 2813 caratteri con un vincolo annuale inventato. Verifica finale non raggiunge il modello |
| `planning_outage` | FAIL, budget esaurito | Testo di 1172 caratteri con disdetta mensile non sostenuta; chooser finale indisponibile prima del modello |
| `home_write_retry` | FAIL, budget esaurito | Testo di 790 caratteri fattualmente valido ma senza differenza 60; nessuna consegna Home raggiunta |
| `source_revoked` | PASS | Revoca della fonte e arresto del lavoro |
| `memory_revoked` | PASS | Ritiro della Memory e arresto del lavoro |
| `memory_corrected` | FAIL, budget esaurito | Rilegge la fonte corretta a 150; testo di 776 caratteri conserva il prezzo corrente ma non esplicita la differenza 30 |
| `source_change_crash` | FAIL, fonte non letta | Prepara senza Evidence, riceve `preparation_sources_required`; rivalutazione `continue` fondata sull'anteprima |
| `already_resolved`, `irrelevant` | PASS | `no_goal` coerente con assenza di lavoro utile aperto |

### Riscontri manuali dagli intermedi osservati

In `completed_result` la prima generazione Gemini di 1060 caratteri contiene
totali, differenza, periodo, condizione ignota e qualifica della fonte.
L'audit Mistral la respinge per verifica del fornitore e costi non documentati,
che non sono requisiti del confronto attribuito. La seconda generazione
Mistral di 1923 caratteri inventa il non-rimborso mensile. Il secondo audit
corregge quel punto, ma aggiunge all'annuale «Nessun vincolo di durata minima»,
non sostenuto. Quel testo di 2813 caratteri è persistito con `verified=true`,
ma il goal resta attivo e non viene consegnato. I calcoli sono corretti;
questo non rende valida la clausola inventata.

In `planning_outage` generazione, audit e testo salvato coincidono. La
clausola «disdetta gestibile secondo la cadenza mensile» non è sostenuta e
non compare nelle cinque righe dell'audit, senza righe omesse dal report.
Nel caso Home la generazione di 859 caratteri viene ridotta a 790: condizioni
ignote e qualifica restano corrette, ma il delta manca già nella generazione.
Nel caso di Memory corretta la generazione di 987 caratteri viene ridotta a
776; il testo usa 150 e non il vecchio 120, ma non esplicita il delta 30.
Nessuno di questi testi è stato consegnato.

Per Discovery l'audit iniziale modifica un'offerta di preparare in una
affermazione di avere già preparato, pur lasciando il bisogno aperto e senza
prove di completamento. Il piano successivo usa l'anteprima come se fosse
già una lettura: `prepare` fallisce correttamente senza Evidence. La
rivalutazione interpreta erroneamente il fallimento come estraneo ai dati.
Il report non mostra generazione o audit di preparazione per quel caso.

Nei tre chooser finali e nei due verifier del caso ordinario il contatore
delle chiamate non aumenta fra ingresso e ritorno `None`: il giudizio si
ferma prima del modello. La ricostruzione dei payload descritta sopra
conferma un limite di contesto, distinto dalla qualità semantica dei testi.

### CI e3a: verde sul codice esatto

**4/4 workflow e 14/14 job PASS**, senza step saltati:
[CI PR](https://github.com/dangerok97/DANGEROK/actions/runs/38203018472),
[CI push](https://github.com/dangerok97/DANGEROK/actions/runs/38203014619),
[Situation PR](https://github.com/dangerok97/DANGEROK/actions/runs/38203018512),
[Situation push](https://github.com/dangerok97/DANGEROK/actions/runs/38203014589).
Nei backend: **464 PASS** per il gruppo v162 (PR 11,50 s; push 11,67 s),
scripted **9/9** con tutti i contatori esterni a zero, **6 PASS su Mongo e
processi separati** (PR 12,53 s; push 12,46 s), **3 PASS v39** (0,37/0,38 s).
I gate Mongo hanno `PHASE2_REAL_MONGO=1` e nessun test saltato.

Il checkout PR è il merge tecnico
`1ec3f8e48b12a568b0013835c565e3d1d9b33f22`, parent da6c/e3a, con lo stesso
albero c18c del candidato. Il push verifica direttamente e3a. Anche frontend
TypeScript/export iOS, product guard, sicurezza telefonica e scansione dei
segreti sono verdi. La verifica del nuovo candidato è distinta da questa CI.

### Confini della prova

Record, account e clock di collaudo sono sintetici. Nessun messaggio, chiamata,
notifica, pagamento, prenotazione o scrittura di calendario reale viene
eseguito. Il bucato precedente di Tarquinia resta chiuso. Il rilascio sui
servizi app è stato rifiutato dal controllo automatico Railway; il servizio
tecnico isolato non equivale a quel rilascio. Build nativa firmata e ricevuta
del dispositivo non sono attestate da questi test.

---

# QA v162 — premesse documentate e risultato preservato nell'audit

## Candidato successivo a f188: verifica locale

**493 PASS su 28 moduli in 6,44 secondi**, più CLI scripted **9/9**, senza chiamate LLM reali, HTTP del modello o effetti esterni. I 28 moduli includono l'insieme v162 della CI, la prova del runner
dei provider pubblici e i due moduli del clock modificati. Il modulo di
preparazione/recupero conta **10** casi, quello della diagnostica
**42**, i due moduli del clock **12**. I conteggi
sono inclusi nell'aggregato e non si sommano. Le nuove sei varianti di
attribuzione riconoscono le note salvate senza trattare parole simili come
provenienza. Codice congelato prima dell'aggregato.

L'audit riceve anche obiettivo, risultato atteso e criteri del lavoro,
protetti insieme alla bozza e alle fonti citate entro gli stessi 9000
caratteri. Distingue la richiesta della persona dalle interpretazioni
precedenti, che non possono prevalere su una fonte corretta. Il controllo
delle premesse collega le clausole ai passaggi disponibili e considera
controesempi compatibili con quei fatti; una caratteristica tipica della
categoria non sostituisce una premessa documentata. Le correzioni devono
conservare i risultati e le differenze già sostenuti. Restano due chiamate,
generazione e audit, con lo stesso parser operativo e senza regole di dominio.

I test controllati verificano trasporto, limiti, conservazione delle fonti,
persistenza e rifiuto operativo. Non dimostrano che il modello reale non
inventi una premessa. La revisione manuale resta obbligatoria. Il collaudo
osserva ora anche la funzione di rivalutazione nel contesto del metodo
eseguito sul database sintetico marcato, con il budget osservativo esistente
e senza modificare la risposta o l'attesa decisa.

## Gate reale f188: esito originale e revisione manuale

Head `f188b4bb0f0a3eaad4042761eac11130e709e7db`, deployment tecnico
`31f71e3f-0988-4f9c-a3f6-196e003cbe72`. Esecuzione dalle
**04:00:25.729633 alle 04:03:48.606785 UTC del 12 ottobre 2026**:
**6/9 controlli limitati PASS**, **64 chiamate logiche** e **73 HTTP**.
Il [report originale](evidence/autonomy_v162_live_2026-10-12_f188b4b.json) è
stato recuperato concatenando senza separatore due frammenti consecutivi
di log: JSON valido, 111883 caratteri, revisione esatta verificata. Non è
stato modificato per incorporare i giudizi manuali. Letture pubbliche non
eseguite perché subordinate al superamento del gate.

| Caso | Gate limitato | Revisione e prova effettiva |
|---|---|---|
| `completed_result` | PASS | 1111 caratteri validi, identici fra generazione/audit/persistenza; Home, replay e isolamento verificati |
| `planning_outage` | FAIL | Completa il lavoro interno, ma “disdetta gestibile sul mensile” non è sostenuta; anche falso negativo lessicale su “note salvate” |
| `home_write_retry` | PASS, manualmente respinto | Recupero Home verificato; testo di 1691 caratteri ratifica una premessa inventata sulla flessibilità |
| `source_revoked` | PASS | Fonte chiusa, cancellazione, wake rimossa e replay senza riapertura |
| `memory_revoked` | PASS | Abbandono dopo ritiro della Memory |
| `memory_corrected` | FAIL | Rilegge 150 euro/30 di differenza; audit negativo, nessuna bozza salvata, attesa persistita e non anticipata dal runner |
| `source_change_crash` | FAIL | Recupera, legge e prepara; audit elimina il delta corretto di 60 euro presente nella generazione |
| `already_resolved`, `irrelevant` | PASS | `no_goal` coerente con le fonti |

### Diagnosi sostenuta dagli intermedi

In `home_write_retry` generazione e audit Groq `qwen/qwen3.8-27b` conservano
lo stesso testo. La premessa dichiarata è un'assenza di anticipo “implicita”
nel modello mensile; l'audit la classifica come derivazione e descrive la
flessibilità come caratteristica intrinseca. Il difetto è la sostituzione
di una premessa documentata con una convenzione di categoria, non una
perdita di contesto o una riga mancante nella diagnostica.

In `planning_outage` generazione e audit Gemini conservano la clausola non
sostenuta sulla disdetta, che non compare nelle sei righe della revisione.
Il report non ha omesso righe. L'attribuzione alle note salvate è presente,
quindi correggere il riconoscitore lessicale non rende semanticamente valido
il testo. Quel gate storico resta fallito.

In `source_change_crash`, la generazione di 901 caratteri contiene il delta
corretto di 60 euro. L'audit restituisce 863 caratteri con 180 contro 120,
aggiunge il limite sulla conferma esterna e rimuove il delta. L'audit non
riceveva l'obiettivo né i criteri del risultato e non esaminava quella
derivazione nella propria revisione. È la perdita corretta dal nuovo
contratto di conservazione; i numeri della fixture non vengono riscritti.

In `memory_corrected`, la generazione di 1478 caratteri inventa la facoltà
di interrompere in qualsiasi momento. L'audit la respinge con booleano
negativo; il testo proposto di 1533 caratteri contiene ancora l'assenza di
una clausola che la fonte semplicemente non specifica. Il rifiuto evita
correttamente il salvataggio. Le ultime tre chiamate Mistral erano contate,
ma la decisione della rivalutazione non era osservata: non vengono
retroattivamente attribuite a chiamate o risposte particolari. Il nuovo
wrapper serve a distinguere questi casi futuri, senza anticipare le attese.

### CI f188: errore nel confronto della serializzazione

**10 job PASS, 2 FAIL, 2 SKIPPED** sui quattro workflow:
[CI PR](https://github.com/dangerok97/DANGEROK/actions/runs/38201953132),
[CI push](https://github.com/dangerok97/DANGEROK/actions/runs/38201951231),
[Situation PR](https://github.com/dangerok97/DANGEROK/actions/runs/38201953172),
[Situation push](https://github.com/dangerok97/DANGEROK/actions/runs/38201951361).
I due backend si fermano nel test
`test_exact_minute_followups_v68.py::test_reasoning_payload_accepts_absolute_minute_checkpoint`:
il risultato `18:35:00+02:00` è corretto, ma l'assert richiede spazi nel JSON
che ora è compatto. PR: 1 failed/145 passed; push: 1 failed/138 passed,
conteggi parziali da failfast parallelo. Anche il test chooser del modulo
v65 contieneva lo stesso confronto fragile; entrambi ora confrontano la
struttura del clock completa. Il test della rivalutazione v65 è invariato.

I gate v162/scripted9, Mongo e v39, successivi allo step fallito, non sono
stati eseguiti su f188. Frontend, sicurezza telefonica, scansione dei segreti
e Situation sono verdi. Il merge tecnico
`d0cda7b812ebba03fb006f250d9ad79efca3e441` ha parent da6c/f188 e albero
`3249b9ff1886be727d55c19edccc9191c48b7b15`, identico al candidato.

### Limiti invariati

Il servizio tecnico usa record sintetici, senza messaggi, chiamate,
notifiche, pagamenti, prenotazioni o scritture di calendario reali. Le
letture pubbliche sono un gate separato, non ancora eseguito in questo giro.
Il bucato precedente di Tarquinia resta chiuso. L'approvazione automatica
Railway ha rifiutato l'applicazione della patch ai servizi app; nessun
aggiramento. Build nativa firmata e ricevuta del dispositivo restano prove
distinte da backend, web e SDK con HTTP finto.

---

# QA v162 — fonti integre, premesse e recupero della preparazione

## Candidato successivo a e4b: verifica locale

**463 PASS su 26 moduli in 5,82 secondi**, più CLI scripted **9/9** con zero chiamate LLM, HTTP del modello ed effetti esterni. I quattro nuovi moduli comprendono **6** casi del chooser, **8** di
preparazione/recupero, **32** di diagnostica e **14** del recupero del worker.
Questi 60 casi sono già inclusi nel totale; le prove mirate precedenti si
sovrappongono. Codice congelato prima dell'aggregato, `git diff --check` pulito.
Nessuna chiamata reale o effetto esterno è attestato dalle prove simulate.

Il chooser conserva tutte le informazioni essenziali, rimuovendo soltanto
copie esattamente identiche dei passi. Se ancora troppo grande, restituisce
indisponibilità tecnica prima del modello; non sceglie al suo posto. Le
prove sul trasporto SDK con HTTP finto verificano anche letture realmente
parziali, cursori, clock e baseline meteo, senza mutare gli input.

L'audit esistente richiede una revisione sintetica delle affermazioni e
delle premesse, comprese quelle introdotte nella correzione. I parser e i
limiti operativi non cambiano. La prova controllata verifica che si salvi
soltanto `checked.content` con `verified is True` e riferimenti validi;
non dimostra che un modello reale riconosca una specifica deduzione falsa.

Una preparazione fallita in `_finish` raggiunge la normale rivalutazione
con motivo, provenienza e possibilità di retry. Quattro errori del percorso
reale di preparazione vengono riprodotti: modello indisponibile, citazione
di generazione errata, audit negativo e citazione di audit errata. Un nuovo
servizio rilegge lo stato persistito e prepara senza una seconda lettura
della fonte ancora corrente; lo storico del fallimento resta conservato.

Il runner osserva le continuazioni attive già presenti entro il limite di
tre esecuzioni background, aggiornando atomicamente solo la scadenza del
checkpoint sintetico. Non azzera contatori e non supera richieste di input,
autorità, attese del modello o rinvii dell'utente. La prova con guasto
temporaneo usa le esecuzioni 2 e 3 dopo la lettura nella prima, poi verifica
Home, replay e owner. Il guasto persistente esaurisce il budget e non produce
un falso risultato. Una riga `failed` è cronologia conclusa: è ammessa dal
verificatore solo dopo goal e piano completati, con tutti gli altri
controlli su testo, evidenza, consegna e idempotenza ancora operativi.

Il `prepare` locale con capability vuota segue ora il comportamento già
supportato dall'executor. È ammesso solo sul database e owner sintetici
marcati; altri passi vuoti ed effetti restano vietati. La diagnostica dentro
il contesto effettivo di preparazione distingue generazione e audit senza
riconoscere parole nel prompt. Registra bozze e correzioni fino a 4000
caratteri, 12 osservazioni, 12 affermazioni per audit con campi da 280
caratteri e riferimenti limitati. Redazione prima del taglio; tipi, ritorni,
eccezioni e cancellazioni invariati. Non esporta prompt di utenti reali.

## Gate reale e4b: 6/9 limitati, con ulteriore rifiuto manuale

Head `e4b68b1c9a30eda285d39b7d203a1ca897dc71fd`, deployment tecnico
`ef4a2b88-8797-454d-8731-dde81fa0248a`, dalle **03:36:01.217500 alle
03:38:40.723273 UTC del 12 ottobre 2026**. Il [report originale](evidence/autonomy_v162_live_2026-10-12_e4b68b.json)
riporta **6/9 PASS**, **56 chiamate logiche** e **66 HTTP osservati**. La
revisione manuale respinge anche `memory_corrected` senza riscrivere il
report. Fixture `personal_outcome_v1` invariata. Letture pubbliche non eseguite.

| Caso | Controllo codificato | Riscontro e limite |
|---|---|---|
| `completed_result` | PASS | Testo di 907 caratteri manualmente valido; Home, replay e isolamento verificati |
| `planning_outage` | FAIL | Lettura completa; preparazione fallita, goal attivo e checkpoint ancora presente; causa esatta della bozza/audit non osservata |
| `home_write_retry` | FAIL | Richiesta di dati già letti dopo riduzione del payload chooser; guasto Home non ancora raggiunto |
| `source_revoked` | PASS | Fonte chiusa, goal cancellato, wake rimossa e replay senza nuovo lavoro |
| `memory_revoked` | PASS | Abbandono dopo ritiro della Memory |
| `memory_corrected` | PASS, manualmente respinto | Rilettura e calcolo 180/150/30 corretti; testo di 1087 caratteri attribuisce al mensile maggiore flessibilità non documentata |
| `source_change_crash` | FAIL | Discovery recupera e ammette; il guard del runner blocca erroneamente il prepare locale senza capability |
| `already_resolved`, `irrelevant` | PASS | `no_goal` rispettato |

La bozza valida del primo caso attribuisce i dati alla nota interna, conserva
15×12=180 euro, annuale 120 e differenza 60, anticipo e annuale non rimborsabile;
le condizioni ignote del mensile restano ignote. La bozza corretta della
Memory dimostra invece che l'audit ha accettato o introdotto una premessa
non sostenuta. Il report precedente non contiene gli intermedi: non è
possibile assegnare la frase alla generazione oppure all'audit. La fonte
completa arriva alla preparazione; questo difetto non deriva dal chooser.

Per `home_write_retry`, la ricostruzione sul percorso reader/evidenze/chooser
produce 9774 caratteri, 9396 compatti. Le copie dei passi occupano 1700
caratteri; il riduttore precedente taglia invece fonte e anteprima da 565
a 283, perdendo prezzo annuale e non rimborsabilità e marcando l'estratto
come troncato. È una riproduzione deterministica, non il corpo HTTP storico.

Per `planning_outage` non è documentata la causa precisa del fallimento di
preparazione. La prova controllata del retry dimostra che il runner poteva
osservare troppo presto un goal ancora attivo; non riclassifica il caso
storico. Per `source_change_crash`, il difetto del guard è riprodotto prima
della patch e le due varianti con prepare locale completano dopo la patch.

### CI dell'esatto e4b, distinta dal gate reale

**14/14 job PASS**: CI principale e Situation su PR e push. [CI PR](https://github.com/dangerok97/DANGEROK/actions/runs/38200268210),
[CI push](https://github.com/dangerok97/DANGEROK/actions/runs/38200264326),
[Situation PR](https://github.com/dangerok97/DANGEROK/actions/runs/38200268266),
[Situation push](https://github.com/dangerok97/DANGEROK/actions/runs/38200264335).
I due backend eseguono **386 test v162**, scripted **9/9**, **6 prove Mongo
reale senza skip** e **3 regressioni v39**. Il merge tecnico
`eb3cc9fef55d9e4b381628792a4b3fb0266da1a0` conserva l'albero del candidato
`884f86ba174b595531c2cee0becc419bb5c20049`.

### Stato del rilascio

Nessun esito reale viene anticipato per il candidato successivo. Il servizio
tecnico è isolato e usa note sintetiche; nessun messaggio, chiamata, notifica,
pagamento, prenotazione o scrittura di calendario reale. Il precedente
bucato di Tarquinia resta chiuso. L'applicazione della patch ai servizi app
è stata rifiutata dal controllo di approvazione Railway e non viene aggirata.
Build nativa firmata e ricezione su dispositivo rimangono prove distinte,
non fornite da CI, web o SDK con HTTP finto.

---

# QA v162 — contratto, recupero e verifica senza perdita di prove

## Verifica locale della revisione successiva a c38b

**403 PASS su 22 moduli in 4.73 secondi**, più CLI scripted **9/9** con zero chiamate LLM, HTTP del modello ed effetti esterni. Il codice è congelato prima dell'aggregato. I tre nuovi moduli
comprendono **13** prove di ammissione, **16** di conservazione
del contesto e **28** di recupero/diagnostica. Sono già inclusi
nel totale; le esecuzioni mirate precedenti si sovrappongono.

### Correzioni e perimetro

L'ammissione valida prima della creazione del goal: le stringhe vuote o
composte soltanto da spazi non definiscono un obiettivo; un elenco restituito
come stringa non viene spezzato in caratteri; una domanda vuota non chiude
una decisione `clarify`. I quattro rami hanno esempi JSON completi. Il campo
annidato nell'assessment non sostituisce il `desired_outcome` obbligatorio.
Array opzionali assenti o vuoti restano ammessi. Il retry applicativo conserva
tre tentativi, backoff, lease e protezione della revisione già presenti.

La verifica del risultato riceve integralmente il testo, i criteri e le prove
citate. La riduzione elimina prima copie e dettagli accessori, con lo stesso
limite di 9000 caratteri. Riferimenti necessari fuori dalle ultime dodici
prove vengono mantenuti; contenuti essenziali mancanti o eccessivi producono
indisponibilità tecnica prima di chiamare il modello. La bozza non diventa
una fonte indipendente e i controlli di proprietà/revoca non vengono rimossi.

Il runner segue soltanto retry `pending/unavailable` già persistiti sul
database sintetico marcato. Cambia solo la scadenza, con confronto atomico
di owner, fonte, revisione, tentativi e lease. Assenza del retry, esaurimento
e cambio di revisione restano fallimenti; `wait`, `no_goal` e `clarify` non
sono convertiti. Il reporter separa proposta Discovery, audit e scarti, con
contatori e riferimenti limitati, senza esportare prompt o messaggi privati.

Il riconoscitore del limite della fonte accetta ora negazioni equivalenti
come «non sono confermate» e «non costituiscono una conferma». I dieci nuovi
esempi producono cinque fallimenti attesi prima della correzione e passano
dopo; le cinque frasi senza negazione pertinente restano respinte. Con la
regressione precedente sono **11 PASS** mirati. La revisione manuale continua
a essere necessaria: questi controlli non sono un giudice semantico generale.

## Gate reale c38b: 2/9, conservato integralmente

Il head `c38b8d11f3b521a63034e7bf3d892f4ae1ad9d3f` viene eseguito nel
deployment tecnico `a8cabcf3-7e4c-4c36-a2ad-c1ad6636d66b`, fra
**03:08:43.802699 e 03:10:05.250279 UTC del 12 ottobre 2026**. Il
[report originale](evidence/autonomy_v162_live_2026-10-12_c38b.json) attesta
**2/9 PASS**, **28 chiamate logiche**, **32 HTTP osservati**. La fixture resta
`personal_outcome_v1`; le letture pubbliche condizionate al superamento non
partono. Le prime risposte arrivano da Gemini 2 `gemini-flash-lite-latest`,
poi interviene il fallback Mistral `ministral-8b-2512`.

| Caso | Esito storico | Diagnosi verificata |
|---|---|---|
| `completed_result` | FAIL | Bozza di 1151 caratteri manualmente valida, falso negativo lessicale sulla qualifica della fonte |
| `planning_outage` | FAIL | Goal non completato, bozza di 1098 caratteri senza differenza esplicita di 60 euro; verifica segnala anche condizioni presenti nel testo |
| `home_write_retry`, `source_revoked`, `memory_revoked`, `memory_corrected` | FAIL | Risposte `create_goal` incomplete; il vecchio runner pretende un goal dopo il primo tentativo |
| `source_change_crash` | FAIL | Discovery non produce un'opportunità recuperata; il vecchio reporter non separa proposta, audit e scarti |
| `already_resolved`, `irrelevant` | PASS | Decisione `no_goal` rispettata |

La bozza del primo caso include 15×12=180 euro, annuale 120 e differenza 60,
pagamento anticipato, annuale non rimborsabile e condizioni del mensile non
note. La frase finale nega esplicitamente la conferma diretta o indipendente
del fornitore. Il controllo aggiornato la accetta su riesame statico, ma
questo **non** riclassifica il gate storico: Home e replay di quel caso non
sono stati verificati dopo l'assert che ha fermato l'esecuzione.

Nel secondo caso il testo conserva non rimborsabilità e qualifica della
fonte. Una riproduzione sul percorso reale di lettura, evidenze e preparazione
mostra però il payload ridotto da 10173 a 8767 caratteri e la bozza tagliata
da 1098 a 550, perdendo quelle clausole. È una riproduzione del difetto,
**non** il corpo HTTP storico, che non era stato conservato. La mancanza
della differenza numerica resta un problema distinto e non viene sanata dal
solo riconoscitore o dalla protezione del contesto.

Per le quattro ammissioni incomplete, una riproduzione conferma che la
validazione precedente lasciava la review `unavailable/pending`, con lease
rilasciata e retry a 60 secondi. Una risposta valida al successivo drain
crea un solo goal e una sola wake. Non è quindi dimostrata una perdita di
lavoro in quei quattro casi; era incompleta l'osservazione del recupero.

Il post-audit di Discovery dichiara `resolved` e non mostra prove di
completamento. Il parser non usa quel campo per scartare la proposta: senza
i riferimenti e gli scarti originali non è possibile attribuirgli la causa
del fallimento. La nuova diagnostica registra quei passaggi distintamente.

### CI c38b, separata dal gate reale

**14/14 job PASS** sull'esatto head: CI principale 5/5 e Situation 2/2 sia
sulla PR sia sul push. [CI PR](https://github.com/dangerok97/DANGEROK/actions/runs/38198568099),
[CI push](https://github.com/dangerok97/DANGEROK/actions/runs/38198565459),
[Situation PR](https://github.com/dangerok97/DANGEROK/actions/runs/38198568107),
[Situation push](https://github.com/dangerok97/DANGEROK/actions/runs/38198565395).
Entrambi i backend riportano **319 PASS v162**, scripted **9/9**, **6 prove
Mongo senza skip** e **3 regressioni v39**. Il job PR verifica i tre gruppi
pytest rispettivamente in 8,20, 12,50 e 0,38 secondi. Il merge tecnico
`366315cad13f918c0d2e9f171d9b753208a574c4` ha l'albero
`f41ad43afd44aedcbef4a6d584e5597b878584e6`, identico al head.

Il nuovo gate reale e le letture pubbliche restano da eseguire sulla revisione
corretta. Questo collaudo tecnico non rilascia i servizi app e non dimostra
ricezione su un dispositivo nativo. I report precedenti restano di seguito.

---

# QA v162 — dipendenza lettura/preparazione, verifica locale conclusa

La revisione successiva ad aa6bef supera **336 test su 19 moduli in 4,56
secondi** e il CLI scripted **9/9**. Tutti i nove report scripted attestano
zero tentativi LLM, zero HTTP del modello e zero effetti esterni. La suite
CI comprende il nuovo modulo `test_agent_preparation_dependency_v162.py`.

La review indipendente ha corretto nel nuovo test la collection controllata
per l'assenza di azioni: `agent_action_attempts`, effettivamente usata
dall'executor. Il modulo è stato rieseguito dopo questa sola correzione:
**10 PASS in 1,26 secondi**; il codice applicativo non è cambiato rispetto
all'aggregato di 336 casi.

Le dieci nuove prove verificano il payload fino al vero SDK con solo HTTP
simulato, il reader reale, il riuso di evidenze correnti, una continuazione
parziale e gli esiti del parser senza coercizione. Il recupero applicativo
respinge una preparazione senza evidenze, persiste il nuovo piano, ricarica
servizio e piano, esegue una lettura e salva la bozza dopo audit. Lo storico
fallito resta conservato e il goal non viene chiuso prima della verifica.
L'aggregato mirato di 74 casi si sovrappone a quello finale.

Solo le istruzioni di `make_plan`, `choose_next_action` e `reconsider`
cambiano. Il confronto AST lascia invariati parser, firme, altre funzioni e
costanti. Il contesto corrente resta distinto dalle evidenze; l'assenza di
un inventario nel payload non viene equiparata a uno store vuoto.

Questi esiti locali non provano le scelte del modello reale. Il prossimo
gate esegue direttamente tutti e nove i casi con la fixture invariata e,
solo se superato, la lettura dei provider pubblici. Il riscontro precedente
rimane sotto con il proprio head, report integrali e limiti.

---

# QA v162 — diagnostica aa6bef: risultato valido, lettura nel piano ancora aperta

## Riscontro reale del 12 ottobre 2026: 3/4, diagnostica non completa

Il head `aa6bef5078b1e6ab190dfc2886da571438589680` è stato eseguito nel
deployment tecnico `50813148-0997-458a-b57b-1be328fe2e30`, fra
**02:49:34.910 e 02:50:02.476 UTC**. La fixture resta
`personal_outcome_v1`. Il [report diagnostico](evidence/autonomy_v162_diagnostic_2026-10-12_aa6bef.json)
conserva i quattro report originali, incluso il fallimento: **3/4 PASS**,
`diagnostic_only=true`, esito complessivo `passed=false`.

| Caso | Esito | Riscontro |
|---|---|---|
| `completed_result` | PASS | Lettura completa, preparazione persistita e risultato nella Home; replay idempotente e isolamento fra owner verificati |
| `source_change_crash` | FAIL | Discovery apre il lavoro, ma il piano contiene soltanto `prepare` e omette la lettura; `OWNED_SOURCE_NOT_READ_ONCE` |
| `already_resolved` | PASS | `no_goal`, senza lavoro aggiunto a un risultato già ricevuto |
| `irrelevant` | PASS | `no_goal`, senza attività sulla fonte irrilevante |

Sono osservate **18 chiamate logiche e 21 richieste HTTP**. Il caso positivo
e quello di Discovery ricevono risposte da Gemini 2
`gemini-flash-lite-latest`; i due negativi passano rispettivamente con i
fallback Groq `qwen/qwen3.8-27b` e Mistral `ministral-8b-2512`. Il conteggio
HTTP mantiene il perimetro dichiarato del runner, non quello di un sandbox
globale di socket o DNS.

### Revisione manuale del risultato completato

Il testo preparato, conservato integralmente nel report, contiene **1031
caratteri** e `prepared_text_truncated=false`. La revisione manuale rispetto
alla nota immutata non rileva errori sostanziali: attribuzione ai dati riferiti
dall'utente e non confermati dal fornitore; orizzonte di dodici mesi; costi
180/120 euro e differenza di 60 euro; spese iniziali nulle, spazio e assistenza
uguali; pagamento anticipato e assenza di rimborso dell'annuale in caso di
disdetta anticipata.

Non compaiono più la flessibilità non documentata del mensile o la conclusione
che ogni interruzione anticipata annulli il risparmio. La qualifica
«differenza stimata» conserva la prudenza sui dati riferiti; il calcolo su
quei dati è corretto. Nessun criterio lessicale è stato cambiato per far
passare il testo. Home, idempotenza e isolamento sono esiti del caso
completato; non sono attribuiti al caso fallito.

### Confine ancora aperto: anteprima e prova letta

Nel caso `source_change_crash`, Discovery e ammissione riconoscono ora il
confronto ancora mancante. `make_plan` riceve però `evidence_kind=none` e
sceglie un solo `document.create`, motivandolo con i dati già disponibili
nella Memory. L'anteprima è così trattata come se fosse l'evidenza del reader.
La preparazione fallisce senza salvare testo o fonti: il goal rimane attivo,
con zero evidenze e un passo fallito. Il guard esistente conserva il
fallimento invece di certificare una bozza priva di lettura.

La correzione del contratto di pianificazione è in verifica. Questo report
non ne dimostra l'esecuzione né il recupero del caso. Il prossimo collaudo
è direttamente il gate completo di **nove casi**, seguito dalla lettura
pubblica se il gate è superato. Entrambi restano da eseguire sulla revisione
corretta. Il collaudo usa note sintetiche, reader reale e storage in memoria,
senza letture live di provider personali o effetti esterni. La ripresa dopo
un vero riavvio di processo resta distinta dalla prova diagnostica.

### Test locali e CI, separati dal verdetto reale

Confermati **326 test locali su 18 moduli** e scripted **9/9**, senza modello
reale, HTTP del modello o effetti esterni. I 53 casi mirati della preparazione
e i 47 di Discovery si sovrappongono all'aggregato e non vanno sommati.

Sull'esatto head aa6bef, i workflow Situation della
[PR](https://github.com/dangerok97/DANGEROK/actions/runs/38197284632) e del
[push](https://github.com/dangerok97/DANGEROK/actions/runs/38197282001)
concludono entrambi **2/2 PASS**. La CI principale della
[PR](https://github.com/dangerok97/DANGEROK/actions/runs/38197284701) e del
[push](https://github.com/dangerok97/DANGEROK/actions/runs/38197281974)
concludono entrambe **5/5 PASS**: **14/14 job complessivi verificati**, senza
failure. Il backend della PR riporta **309 PASS v162** in 7,68 secondi,
scripted **9/9** senza LLM/HTTP/effetti, **sei prove Mongo senza skip** in
12,70 secondi (`PHASE2_REAL_MONGO=1`) e **tre regressioni v39** in 0,39
secondi. Il push conferma gli stessi conteggi; i tre tempi pytest sono
rispettivamente 6,79, 11,26 e 0,33 secondi. I conteggi dei due workflow si
sovrappongono e non vengono sommati come casi distinti.

Il merge tecnico della PR è `a846966703ae5c931437eb7c645d83e92ff89b16`,
con albero `0f88fda58a91da249b8bd1c1976de02f30019e55` identico al head.
Il JSON scripted è nei log, senza artifact separati caricati. Questi verdi
attestano la CI del codice aa6bef; la diagnostica reale resta 3/4 e non
certifica né la futura correzione del planner né il gate completo.

Gli stati storici seguenti sono conservati integralmente; questo riscontro
aggiorna l'esito corrente senza riscrivere le prove precedenti.

---

# QA v162 — iniziativa, prosecuzione e risultato

## Ultima verifica locale: scoperta coerente e qualifiche fino alla verifica

La revisione successiva alla diagnostica 1292788 supera **326 test su 18
moduli in 4,65 secondi** e il CLI scripted **9/9**, senza modello reale,
HTTP del modello o effetti esterni. Comprende sei nuove prove del vero
schema JSON di Discovery e nove del percorso di provenienza nella preparazione.
Gli aggregati mirati di 47 e 53 casi si sovrappongono a quello finale.

La regressione sul reader reale era rossa perché `bears_on` mancava dal
payload della preparazione. La correzione conserva qualifiche note e ignote,
cursori e letture parziali nei limiti esistenti. Preparazione, audit e verifica
condividono il contratto di fedeltà ai fatti, senza nuovi giudizi o controlli
deterministici del contenuto. Il parser mantiene gli esiti del modello.

I quattro casi diagnostici verranno ripetuti sulla stessa fixture prima del
gate completo; questi test locali non dimostrano ancora la correttezza delle
nuove decisioni o dei nuovi testi prodotti dal modello reale.

## Verifica locale precedente: stato dell'esito e report revisionabile

La revisione del contratto decisionale e dell'esportazione diagnostica supera
**311 test su 16 moduli in 4,25 secondi** e il CLI scripted **9/9**, senza
modello reale, HTTP del modello o effetti esterni. I 26 nuovi casi verificano
il percorso reale fino all'SDK con solo HTTP simulato e il mantenimento delle
decisioni anche senza `outcome_assessment`. Il modulo del reporter contiene
49 casi PASS, inclusi cinque nuovi controlli del testo esportato. I conteggi
si sovrappongono all'aggregato e non vanno sommati.

Il report conserva il testo preparato anche dopo un errore tardivo, soltanto
nel database marcato del collaudo e per il suo owner. Successo e fallimento
esportano al massimo 6000 caratteri, dopo redazione delle credenziali note,
compreso l'alias `GEMINI_API_KEY_2`; il flag di taglio riguarda il testo
sanificato e il conteggio conserva la lunghezza originale. Il testo persistito
e tutti i criteri di accettazione restano invariati. I report falliti dei due
head precedenti sono conservati nei JSON collegati sotto.

La prova reale diagnostica successiva usa `completed_result`,
`source_change_crash`, `already_resolved` e `irrelevant`, senza cambiare la
fixture. Il suo esito è registrato sotto; il gate completo di nove casi e
la successiva lettura pubblica restano necessari dopo la diagnosi.

## Diagnostica del head 1292788: ammissione ripresa, qualità e scoperta aperte

Il head `12927881483d4102b657625ea4c8a36a26f9f551`, albero
`b732a46b2f967dd693e143f5b07d1633dcc2f6ce`, è eseguito nel deployment
`2d8281e8-1b70-4f21-9ebc-696b7f25352d` il 12 ottobre 2026 fra
02:37:15.909 e 02:37:32.808 UTC. La diagnostica è **2/4 PASS**, con
**13 chiamate logiche e 14 HTTP osservati**, Gemini 2
`gemini-flash-lite-latest`. Il [report integrale](evidence/autonomy_v162_diagnostic_2026-10-12_1292.json)
conserva separatamente i quattro report originali. Non è il gate completo.

Sul medesimo head concludono **14/14 job CI PASS**: sette sulla PR
([CI](https://github.com/dangerok97/DANGEROK/actions/runs/38196412622),
[Situation](https://github.com/dangerok97/DANGEROK/actions/runs/38196412589))
e sette sul push ([CI](https://github.com/dangerok97/DANGEROK/actions/runs/38196409711),
[Situation](https://github.com/dangerok97/DANGEROK/actions/runs/38196409721)).
Entrambi i backend riportano 294 PASS v162, scripted 9/9, sei prove Mongo
senza skip e tre regressioni v39. Il merge tecnico della PR
`0d41df2ca3b2ea86c406bfff0eacd263121dfcd0` ha parent `da6c7456`/`1292788`
e lo stesso albero. Il rapporto del push riporta direttamente il head.
Nessun workflow mobile attivato e nessun artifact separato caricato;
il JSON scripted è nei log. Questi verdi non sostituiscono il live fallito.

`completed_result` riconosce ora il bisogno aperto, crea il goal, legge
l'intera nota e completa i due passi di lettura/preparazione. Il report
conserva il testo anche dopo il fallimento tardivo. L'esito automatico è
`SEMANTIC_RESULT_REJECTED:INTERNAL_SOURCE_NOT_ATTRIBUTED`: la locuzione
«In base alle informazioni registrate» non è riconosciuta dal controllo
lessicale. Questo limite del riconoscitore non rende valido il testo.

La revisione manuale rileva due difetti sostanziali: attribuisce al mensile
una flessibilità contrattuale che la nota non documenta e conclude che ogni
interruzione anticipata azzeri il risparmio dell'annuale. Quest'ultima è una
generalizzazione non sostenuta; la comparazione a dodici mesi non basta
a dedurre tutti gli scenari di interruzione. Occorrerebbero anche condizioni
del mensile e durata effettiva. Cifre e differenza a dodici mesi sono corrette,
e la necessità di verificare i dati col fornitore è espressa, ma il risultato
non supera la revisione semantica complessiva.

`source_change_crash` continua a scegliere silenzio con una sola chiamata,
motivandolo con dati già completi e assenza di scadenze o documenti nuovi.
Il riepilogo `outcome_assessment` è assente: il contratto lo chiedeva nel
testo, mentre il vero esempio JSON del silenzio lo ometteva. La correzione
successiva rende coerente lo schema e riduce i filtri locali contraddittori.
`already_resolved` e `irrelevant` restano entrambi correttamente `no_goal`.

L'esame del percorso di preparazione individua inoltre la qualificazione
`supports` della fonte esclusa dalle righe inviate a generazione e audit.
Il passo seguente ne conserva il significato entro lo stesso limite e
chiarisce il contratto generale su attribuzione, derivazioni e condizioni
non note. Nessun prezzo, esito o frase del gate viene imposto dal codice.

## Verifica locale precedente: fonti, completamento e consegna

La revisione con `fixture_revision=personal_outcome_v1` e la correzione della
consegna finale supera **280 test su 15 moduli in 3,97 secondi** e il CLI
scripted **9/9**, senza modello, HTTP del modello o effetti esterni reali.
Il modulo della consegna finale aggiunge 44 casi; un aggregato separato con
le regressioni Situation, Memory, riesame e apertura produce 118/118 PASS.
Questi conteggi si sovrappongono e non vanno sommati. La CI e il live
sull'esatto commit pubblicato sono registrati sotto e rimangono distinti.

La riproduzione attraversa offerta reale alla Delivery, scelta del canale,
piano differito, invio a un trasporto sintetico e apertura del risultato.
Un risultato generale completato è ora ammesso solo con legame all'esatta
chiusura vista dalla decisione, prove reali dello stesso owner/goal e fonti
correnti. La stessa chiusura non genera duplicati; una vecchia domanda, un
aggiornamento intermedio, una riapertura o un nuovo completamento non ne
eredita il legame. Consenso assente e silenzio scelto dal modello restano
rispettati. Il ritiro dell'Opportunity dopo la normale risoluzione blocca
l'avviso ancora in attesa. La destinazione del risultato è costruita dal
codice sul dettaglio del goal e viene verificata anche all'apertura; il
percorso delle domande continua a rifiutare un lavoro già chiuso.

## Riscontro live dopo l'integrazione iniziale

La [PR #211](https://github.com/dangerok97/DANGEROK/pull/211) è integrata nel commit
`da6c7456efebe5f21f4bd9ea55491236a0d9512a`, con albero
`e06d41c9a6bce2961a34add05a1608d3fccf165d`. La CI della PR e quella del merge
sono verdi: [CI del merge](https://github.com/dangerok97/DANGEROK/actions/runs/38191301620)
e [Situation](https://github.com/dangerok97/DANGEROK/actions/runs/38191301639).
Il gate mobile della PR ha eseguito 28 casi in Chromium e WebKit. La CI
backend ha verificato 128 casi v162, il collaudo scripted 8/8, sei casi con
Mongo reale senza skip e i tre casi v39 di consenso e provenienza.

Il modello reale **non ha superato il gate sulla stessa revisione**:

| Esecuzione Railway | Esito effettivo | Osservazioni |
|---|---|---|
| `0705c9f1-f841-4626-86b6-a67f984410de` | 2/8 PASS | Passano revoca Memory e caso irrilevante; cinque ammissioni non creano una goal e la scoperta non produce l'Opportunity attesa |
| `57cb647d-b38a-44ab-88b0-6fc1231220ea` | 2/8 PASS | Passano revoca Opportunity e caso irrilevante; emergono anche `UNFINISHED_PLAN_STEPS` e `CORRECTED_SOURCE_DID_NOT_CONTINUE` |

Il secondo avvio intendeva applicare un osservatore a due casi; il redeploy
ha invece riutilizzato il comando dell'immagine precedente ed eseguito gli
otto casi originali. È registrato come ulteriore esecuzione fallita della
stessa versione, senza attribuirgli osservazioni diagnostiche che non contiene.
La prova pubblica concatenata non è partita perché il gate precedente è fallito.

Il report di `57cb647d-b38a-44ab-88b0-6fc1231220ea` ha inoltre mostrato
risposte riuscite di Gemini 2 con `model_http_requests=0`. Il limite di 80
intercettava `httpx.AsyncClient.send`, mentre `google-genai==2.15.0`, con
`aiohttp==3.14.3` installato, sceglieva aiohttp. I trasporti HTTPX dei fallback
erano contati, quelli Gemini no. **Il vecchio contatore non provava quindi
un limite complessivo di 80 richieste HTTP per caso.** Restavano distinti i
limiti sulle chiamate logiche e sul tempo; nessuno di questi esiti viene
reinterpretato come prova riuscita dopo la correzione del runner.

La riproduzione locale dei payload ha confermato due perdite di informazioni:
l'ammissione non includeva le Memory citate in `source_context`, e lo snapshot
di scoperta riceveva soltanto il segnale di cambiamento troncato a 160 caratteri.
Il reader canonico corretto in v162 si trova più avanti nella catena e non
può compensare una fonte assente prima della creazione della goal. La nota
sintetica non documenta una scadenza: la frase sul rinnovo prossimo della
fixture viene rimossa, senza aggiungere una nuova urgenza alla fonte.

Questi esiti non autorizzano una dichiarazione di autonomia completa.
La correzione successiva deve conservare i rifiuti legittimi, rendere leggibili
le fonti citate e superare nuovamente i casi con le decisioni reali osservabili.

La diagnostica osservativa effettiva è stata eseguita nel deployment
`76f6fc34-f8a7-418f-ad1f-d66eae8487ee`, ancora sul medesimo commit, limitata a
`completed_result` e `source_change_crash`. Ha confermato l'assenza delle Memory
nel contesto di ammissione e della seconda opzione nello snapshot di scoperta.
Non costituisce un nuovo gate completo. La riproduzione locale del piano
pendente ha poi verificato un risultato semanticamente corretto: il difetto
era il vecchio passo `prepare` ancora pending dopo la conclusione verificata.
La correzione ritira quel passo senza eseguirlo e senza cambiare il gate.

Il reporter successivo registra, entro limiti espliciti, le risposte di
ammissione, scoperta, planning, scelta del passo e verifica. Sui fallimenti
legge lo stato del solo database sintetico: goal, piano, stati dei passi e
conteggi delle evidenze. Non cambia decisioni, eccezioni o stato. La fixture
scripted non indica più la correzione della nota come motivo automatico di
abbandono: ciò contraddiceva il caso che richiede di proseguire con i dati nuovi.

## Verifiche sulla prima revisione della PR #212

Il 12 ottobre 2026, sull'albero locale congelato successivo a `da6c7456`,
l'aggregato poi pubblicato nella [PR #212](https://github.com/dangerok97/DANGEROK/pull/212),
head `0297f86778ca909c9bd6ca8de4cf6a52770ced78`, ha prodotto
**232 PASS in 3,34 secondi su 14 moduli**:
contesto e lettura delle fonti, ripianificazione, continuazione della Memory,
chiusura dei piani, trasporto SDK, recovery, invalidazione delle fonti, OAuth,
push, collaudo autonomo e letture Phase 1. Il comando CLI scripted finale ha
superato **8/8 casi**, con zero tentativi di modello reale, zero HTTP del
modello e zero effetti esterni.

Il controllo mirato dei quattro moduli SDK, autonomia, restart e provider
Phase 1 ha prodotto **70 PASS e 1 SKIP**. Lo skip è soltanto il test con Mongo
reale, disattivato localmente; resta obbligatorio nella CI del nuovo commit.
Questi conteggi si sovrappongono all'aggregato e non vanno sommati. Le
[otto prove del trasporto Gemini](../backend/tests/test_eval_gemini_transport_v162.py)
usano l'SDK e l'adapter di produzione con HTTP simulato: verificano il
confine di trasporto, senza chiamare un modello o un account reale.

Su questo head tutti i **7 job attivati sono PASS**:
[CI](https://github.com/dangerok97/DANGEROK/actions/runs/38193889396) e
[Situation](https://github.com/dangerok97/DANGEROK/actions/runs/38193889324).
Il log backend verifica **215 PASS** nel gate v162, **scripted 8/8**,
**6 PASS con Mongo reale senza skip** e **3 PASS** nei nodi v39 di consenso
e provenienza. Il checkout CI è il merge tecnico `d43f743789784aa1a6f306bb9ac6947fdd293276`,
con albero `d5f4edaf3b18cabf2d9a1ca5d3f7b7fb89930dbd` identico a quello del head.
Il workflow mobile non è stato attivato: i suoi percorsi frontend sono invariati.

Il live sullo stesso head, deployment tecnico
`efdeacc4-6fff-45d5-afee-92f91ad50831`, è invece **1/8 PASS**
(12 ottobre, 01:58:05.131–01:58:14.373 UTC). Passa il solo caso irrilevante.
Le sei ammissioni ricevono ciascuna una Memory completa nel contesto e
restituiscono `no_goal`; anche la scoperta vede la Memory ma decide silenzio.
Il report registra **8 chiamate logiche e 9 tentativi HTTP osservati**:
il precedente contatore Gemini a zero non si ripete. La lettura pubblica
concatenata non parte, perché il primo gate è fallito.

Il [report JSON originale di questa esecuzione](evidence/autonomy_v162_live_2026-10-12_0297.json)
conserva decisioni e contatori del solo account sintetico.

La disponibilità della fonte è ora provata, ma la fixture informativa non
attestava un bisogno personale ancora aperto: elencava già costi e vincoli,
senza dire che la persona stesse scegliendo o aspettasse un confronto.
`no_goal` era quindi un esito difendibile, non una prova univoca di ammissione
difettosa. L'assenza di urgenza, citata in alcune motivazioni, non è da sola
una ragione sufficiente per tacere. Questo risultato rimane fallito e non
viene convertito retroattivamente in un PASS.

## Fixture con esito personale aperto e controllo già risolto

La revisione `fixture_revision=personal_outcome_v1` conserva integralmente
`baseline.FACT` di v140 e aggiunge alla sola fonte canonica v162 uno stato
personale: la persona usa il mensile, prevede di tenere l'archivio per dodici
mesi, valuta le due formule e non ha ancora ricevuto il confronto scritto
di costi e vincoli. `FIXTURE_NOTE` viene usata nella governance, nel segnale
di cambiamento e nella successiva correzione 120→150. Il bisogno resta nella
fonte anche dopo quella correzione; summary e motivo della review derivano
da ciò che la nota attesta. Non vengono aggiunti scadenze, autorizzazioni
a cambiare contratto o istruzioni che impongano al modello una decisione.

Il nuovo caso `already_resolved` conserva gli stessi termini economici,
ma la fonte attesta il confronto già ricevuto, la scelta del mensile
conclusa e l'assenza di dubbi o verifiche aperte. L'esito richiesto è
`no_goal`, con la fonte presente e senza goal, wake o capacità eseguite.
Questo porta il collaudo completo a **9 casi**. Entrambe le note restano
entro il limite di preview di 600 caratteri e sono verificate nel payload
di ammissione reale, non soltanto nei metadati dell'Opportunity.

Sulla nuova fixture la suite locale autonomia/restart riporta
**49 PASS e 1 SKIP in 2,02 secondi**, con il solo Mongo reale escluso in locale.
Il CLI scripted eseguito successivamente riporta **9/9 PASS**, zero tentativi
di modello, zero HTTP del modello e zero effetti esterni. Il report espone
`fixture_revision` per distinguere questi input dai precedenti otto casi.
Il live e la CI della revisione con nove casi sono stati eseguiti come
riportato nella sezione seguente; i verdi precedenti non li sostituiscono.

## Seconda revisione della PR #212: trasporto integro, decisione ancora errata

Il head `e2bc1322f0aa9093eeab7e6097ef07cd30d0be20`, albero
`c97923fa916365c2445efe13b5a085a47db3e3d6`, conclude **7/7 job PASS**:
[CI](https://github.com/dangerok97/DANGEROK/actions/runs/38195001018) e
[Situation](https://github.com/dangerok97/DANGEROK/actions/runs/38195001003).
Il log backend contiene **263 PASS in 4,80 secondi**, scripted **9/9**,
**6 PASS con Mongo reale** senza skip e **3 PASS** nei nodi v39. Il checkout
`5474f0b97704b72288cfcb682f7283b476fd3fbc` ha parent `da6c7456` e `e2bc1322`
e lo stesso albero. Nessun artifact separato è caricato: il JSON scripted
è nel log. Il workflow mobile non è stato attivato su questi file backend.

Il live sul medesimo head, deployment
`170e4cf3-9346-46ac-a097-9bd7f79d86ac`, resta **2/9 PASS**
(12 ottobre 2026, 02:15:03.354–02:15:12.054 UTC). Passano soltanto
`already_resolved` e `irrelevant`. Le sei ammissioni positive ricevono una
Memory completa ma restituiscono `no_goal`; Discovery vede la Memory e tace.
Sono osservate **9 chiamate logiche e 10 HTTP** con Gemini 2,
`gemini-flash-lite-latest`. La lettura pubblica concatenata non parte.

Il [report JSON originale del head e2bc](evidence/autonomy_v162_live_2026-10-12_e2bc.json)
conserva anche i due rifiuti corretti e tutte le ammissioni mancate.

La fixture `personal_outcome_v1` documenta adesso esplicitamente il confronto
scritto mancante. Motivazioni come «confronto già disponibile» contraddicono
quella fonte; dati completi o assenza di urgenza non provano l'esito consegnato.
Una riproduzione senza rete attraversa `consider`, ragionamento, manager,
adapter Gemini e SDK reali con `httpx.MockTransport`: system e payload HTTP
sono identici a quelli passati al manager, con tutta la nota e autorità
`user_stated`, senza troncamento. Ammissione: system 4604 e payload 1763
caratteri; Discovery: system 12645 e payload 2416. Due risposte sintetiche,
zero rete e zero LLM: questa prova esclude la perdita di contesto in quei
percorsi, senza attribuire qualità semantica al modello.

La correzione successiva rende esplicita la distinzione fra esito aperto,
materiali disponibili e prova di completamento nel contratto generale.
Il riepilogo `outcome_assessment` è solo osservabile: nessuna conversione
automatica di `no_goal`, nessun router di dominio e nessuna nuova urgenza.
La fixture resta invariata e le prove reali della nuova revisione devono
ancora essere registrate prima di dichiarare superato questo limite.

## Cosa dimostra il gate

Il nuovo [harness](../backend/scripts/autonomy_completion_eval_v162.py) mantiene collegati i servizi di produzione: admission, goal, wake persistita, claim del worker Ambient, piano, lettura della fonte, preparazione, verifica, completion, visibility, outbox e lettura della Home. Il caso `source_change_crash` parte prima dell’admission, da un cambiamento registrato: passa dallo snapshot reale e da OpportunityDiscovery prima di arrivare al risultato.

Il risultato atteso è un confronto utile per la scelta personale ancora aperta, non la sola esistenza di un goal o di un testo. La nota sintetica attesta questo bisogno e dichiara 15 euro al mese, 180 per dodici mesi, oppure 120 anticipati per l’anno, con pari capacità/assistenza e senza rimborso dell’annuale. ORA deve leggere la nota canonica, preparare il confronto con differenza 60, attribuire i dati alla nota e conservare il limite della mancata verifica presso il fornitore. Non viene autorizzato né tentato un cambio di contratto. Il controllo `already_resolved` verifica che gli stessi dati non generino altro lavoro quando la scelta risulta già conclusa.

La memoria viene scritta da `MemoryGovernanceService.apply`, nel formato effettivo `statement`/`content`. L’evidenza deve contenere il riferimento della memoria e la sua versione. Il vecchio seed `memories.summary` non viene riutilizzato: avrebbe nascosto la divergenza fra lo schema scritto dalla governance e quello letto dall’agente. Fonti: [test del reader canonico](../backend/tests/test_agent_memory_read_v162.py), [test del collaudo](../backend/tests/test_autonomy_completion_eval_v162.py).

### Livelli dichiarati separatamente

| Livello | Decisioni | Fonti e persistenza | Prova effettiva |
|---|---|---|---|
| `autonomy_completion_eval_v162 --mode scripted` | Risposte previste e guasti iniettati | Record sintetico canonico, reader/worker/outbox reali, Mongo in memoria | Contratto completo e negativi ripetibili, senza rete esterna |
| Lo stesso harness con `--mode live` | Provider LLM configurato, chiamate osservate e contate | Stessi record sintetici e servizi di produzione | Decisioni effettive del modello lungo la catena, comprese ripresa e consegna interna |
| `test_autonomy_completion_restart_v162.py` | Scripted | Mongo reale isolato, quattro processi Python distinti | Il lavoro e l’outbox sopravvivono all’uscita dei processi |
| `phase1_read_provider_eval --mode live` | LLM reale | Handler di produzione, route/weather pubblici reali, account sintetico | Letture datate, provenienza, limiti semantici e risposta nel ciclo cognitivo |
| Test push/sessione v162 | SDK e trasporti iniettati | Sessioni e dispositivi sintetici | Registrazione, revoca, scadenza, cambio account e recupero degli errori |

Nessuno dei primi quattro livelli dimostra la ricezione su un telefono. La prova con fonti pubbliche non viene etichettata come esecuzione del worker autonomo: la catena worker completa è provata sui record interni. Nessuno dei livelli autorizza accesso a database utente, messaggi, pagamenti o nuove attività personali.

## Casi della catena completa

| Caso | Interruzione o condizione | Condizione necessaria per PASS |
|---|---|---|
| `completed_result` | Budget di un passo al primo worker | Lettura effettiva, checkpoint persistito, nuovo claim, risultato fondato recuperabile dalla Home, replay senza duplicati |
| `planning_outage` | Il primo tentativo di piano restituisce indisponibilità | Goal aperta, retry persistito, nessun falso risultato; altro tick completa senza apertura della Home |
| `home_write_retry` | Fallisce la prima scrittura della visibility finale | Outbox pending persistita; recupero della stessa decisione, risultato recuperabile, nessun nuovo ragionamento al replay |
| `source_revoked` | L’Opportunity viene ritirata dopo la lettura | Goal cancellata, nessun passo ulteriore, nessuna wake residua; anche il replay resta fermo |
| `memory_revoked` | La memoria citata viene dimenticata dopo la lettura | L’evidenza già acquisita non produce un risultato; lavoro abbandonato e nessuna preparazione finale |
| `memory_corrected` | La nota cambia da 120 a 150 euro annui | Stessa goal prosegue, vecchia evidenza esclusa, nuova memoria riletta, risultato 180/150/30 con provenienza corrente |
| `source_change_crash` | Cancellazione durante il primo scan | Cambiamento ancora pending, nuova review lo elabora e lo conferma; Opportunity, goal, worker e Home arrivano poi al risultato |
| `already_resolved` | La fonte attesta confronto ricevuto e scelta conclusa, senza verifiche residue | Decisione `no_goal` pur con la Memory presente, nessuna wake e nessuna capacità eseguita |
| `irrelevant` | Contenuto promozionale privo di bisogno documentato | Decisione `no_goal`, nessuna wake e nessuna capacità eseguita |

Il test accelera soltanto `next_run_at`, `scheduled_for` e scadenze dell’outbox nel database sintetico marcato. Prima di farlo verifica che il checkpoint esista già: non crea un retry per riparare un difetto del prodotto. La gestione delle wake resta quella di `Ambient.tick`, inclusi claim e completion.

Il mock Mongo richiede un adattatore per `find_one_and_update`: senza `_id`, mongomock cerca il documento aggiornato tramite il vecchio filtro e può restituire `None` pur avendo acquisito il claim. L’adattatore conserva `_id` durante quella ricerca e ripristina poi la proiezione richiesta. Non modifica Motor; la prova con Mongo reale e processi separati è il controllo indipendente di questo limite del mock.

## Errori concreti emersi nell’audit

| Confine | Comportamento riprodotto prima della correzione | Gate dedicato |
|---|---|---|
| Primo piano indisponibile | Una sola indisponibilità chiudeva definitivamente la goal; le wake successive vedevano lavoro chiuso | [Planning recovery](../backend/tests/test_agent_planning_recovery_v162.py) e `planning_outage` |
| Scan interrotto | Il batch di cambiamenti era consumato prima che la review fosse persistita; dopo una cancellazione il retry concludeva che nulla era cambiato | [Discovery recovery](../backend/tests/test_opportunity_discovery_recovery_v162.py) e `source_change_crash` |
| Schema della memoria | La governance scriveva `statement`/`content`, mentre la lettura automatica dipendeva dal campo legacy `summary` | [Memory reader](../backend/tests/test_agent_memory_read_v162.py) e seed canonico nel nuovo harness |
| Fonte prima dell'ammissione e della scoperta | La Memory citata mancava dal contesto di ammissione; il solo delta di 160 caratteri non conteneva entrambe le opzioni | [Memory source context](../backend/tests/test_memory_source_context_v162.py) |
| Ripianificazione dopo correzione | I riferimenti aggiornati non garantivano che il contenuto corrente arrivasse al nuovo planner e al verifier | [Memory replanning context](../backend/tests/test_agent_memory_replanning_context_v162.py) |
| Lettura parziale della Memory | Il taglio a 600 caratteri non esplicitava una continuazione; cursori e limiti potevano perdersi nel contesto ridotto | [Memory continuation](../backend/tests/test_agent_memory_continuation_v162.py) |
| Piano dopo completion | Il risultato poteva essere valido mentre un passo ormai superfluo rimaneva pending nel piano concluso | [Terminal plan](../backend/tests/test_agent_terminal_plan_v162.py) |
| Conteggio HTTP di Gemini | Il trasporto aiohttp dell'SDK evitava il controllo HTTPX e il relativo budget, pur producendo risposte reali | [Gemini SDK transport](../backend/tests/test_eval_gemini_transport_v162.py) e guard `MODEL_HTTP_NOT_OBSERVED` nel collaudo |
| Riuso dopo revoca/correzione | Dopo una lettura valida, una memoria forgotten poteva ancora alimentare una preparazione e una card Home al tick seguente; anche una card già completata rimaneva visibile dopo la revoca | [Memory source fence](../backend/tests/test_agent_memory_source_fence_v162.py), `memory_revoked`, `memory_corrected` e due regressioni Home già visibile/outbox pendente |
| Disponibilità dei connector | Sincronizzazione, account multipli, grant mancanti e provider non disponibili potevano essere presentati come lettura disponibile o indisponibile in modo incoerente | [Connector readiness](../backend/tests/test_agent_connector_readiness_v162.py) |
| Registrazione nativa | La chiave dell’identificativo del dispositivo usava un carattere rifiutato dal validatore effettivo di SecureStore | [Adapter push](../frontend/src/ambient/pushRegistration.test.cjs) |
| Logout con rimozione locale fallita | Un `secureRemove` fallito silenziosamente, insieme alla revoca server offline, poteva permettere al refresh di riattivare la sessione vecchia | [Session lifecycle](../frontend/src/auth/sessionLifecycle.test.ts), [token store](../frontend/src/auth/tokenStore.test.ts) e coda di cleanup |
| Ritorno OAuth nativo | Il collegamento doveva aprire una auth session nativa e verificare l’account restituito; lo stato Calendar poteva inoltre consumare un flow Gmail o essere consumato due volte in concorrenza | [OAuth frontend](../frontend/src/connectors/connectorOAuth.test.ts) e [OAuth backend](../backend/tests/test_connector_oauth_return_v162.py) |

Il retry del piano è tecnico e limitato: quattro tentativi totali, con attese di 60, 300 e 1800 secondi. Dopo l’esaurimento il lavoro resta aperto e sospeso come indisponibile, senza successo inventato né domanda superflua all’utente. Un piano valido azzera i tentativi; un fatto nuovo o una ripresa esplicita possono aprire un nuovo ciclo. Il test non scambia questa sospensione finale per un risultato raggiunto.

## Esecuzione offline e ripartenza reale

Dalla directory `backend`, con le dipendenze bloccate e `mongomock-motor==0.0.36` installati:

```sh
python -m pytest -q -n 0 tests/test_autonomy_completion_eval_v162.py -x
python -m scripts.autonomy_completion_eval_v162 --mode scripted \
  --output /tmp/ora-autonomy-v162-scripted.json
```

Il [test a processi separati](../backend/tests/test_autonomy_completion_restart_v162.py) è opt-in localmente e obbligatorio nella [CI](../.github/workflows/ci.yml):

```sh
PHASE2_REAL_MONGO=1 MONGO_URL=mongodb://127.0.0.1:27017 \
  python -m pytest -q -n 0 tests/test_autonomy_completion_restart_v162.py -x
```

Accetta soltanto un endpoint Mongo locale, singolo, senza credenziali o nome di database preesistente nell’URI. Crea un database casuale `ora_autonomy_v162_<nonce>`, controlla un secondo nonce per proprietà e pulizia, e non eredita le credenziali del processo chiamante. I processi figli vietano DNS e connessioni diverse dalla porta Mongo indicata. La sequenza termina realmente ciascun processo: errore di planning → lettura → completion con outbox non consegnata → recupero e replay.

La CI usa il servizio `mongo:6` già presente. Un’esecuzione locale senza Mongo deve essere riportata come processo non verificato; lo skip non è una prova di persistenza.

## Esecuzione live richiesta

Il nuovo [workflow manuale](../.github/workflows/autonomy-completion-eval.yml) esegue prima i casi scripted, poi due job distinti: autonomia con LLM reale e letture pubbliche con LLM/provider reali. Non è attivato da pull request di fork o da un timer. Le chiavi di valutazione dedicate hanno precedenza su quelle repository già configurate.

```sh
python -m scripts.autonomy_completion_eval_v162 --mode live \
  --output /tmp/ora-autonomy-v162-live.json
python -m scripts.phase1_read_provider_eval --mode live --max-steps 7 \
  --output /tmp/ora-public-read-v162-live.json
```

Il secondo comando richiede il provider route compatibile configurato (`google_routes` o `mapbox`) e la sua chiave, oltre al modello; il meteo usa `open_meteo`. Nel workflow il provider viene da `vars.ORA_EVAL_ROUTING_PROVIDER`, poi da `vars.ROUTING_PROVIDER`, infine da `google_routes`. La chiave corrispondente viene dal secret `ORA_EVAL_ROUTING_API_KEY`, oppure `ROUTING_API_KEY`. Per usare Mapbox va impostata una delle due variabili provider a `mapbox`: la presenza di una chiave non ne determina il tipo. Nel runner Railway si conserva il provider già configurato, senza forzarlo a Google. I punti sono i luoghi pubblici fissi Roma Termini e Colosseo. Non sono posizioni della persona né dati estratti dai suoi account.

Le credenziali si usano tramite il runtime predisposto; non vanno stampate, esportate nel report o copiate nella documentazione. Nell’harness autonomo solo `ProviderManager.chat` abilita gli endpoint HTTPS del modello nel controllo di `httpx.AsyncClient.send`. Nel runner corretto anche l'SDK Gemini usa questo trasporto. Restano utilizzabili soltanto `information.read` e `document.create`; un tentativo di effetto esterno, invio push, altro owner o endpoint HTTPX non consentito fa fallire il gate. Questo controllo non è un sandbox globale delle connessioni del processo.

Esiti CLI del nuovo harness:

| Exit code | Significato |
|---|---|
| `0` | Tutti i casi richiesti hanno soddisfatto il contratto del livello dichiarato |
| `1` | Caso non raggiunto, risultato non valido, boundary tentato o errore durante la prova |
| `3` | Live richiesto ma senza credenziali del modello: `status=blocked`, `passed=false` |

Il workflow non contiene un ramo “credenziali assenti → salta e passa”. I report includono tempi di esecuzione, eventuale commit dalla metadata CI/deployment, `fixture_revision`, chiamate LLM osservate, richieste HTTP del modello, capacità eseguite, tick, guasti iniettati, livello delle fonti, risultato e testo sintetico da revisionare. I conteggi delle chiamate già avvenute sopravvivono anche a un verdetto fallito. `live_provider_reads=0` nel collaudo autonomo interno è intenzionale ed esplicito.

### Ambito e budget del live

| Passaggio | Numero di casi | Limiti applicati |
|---|---|---|
| Autonomia completa | 9: cinque completamenti utili e quattro negativi | 40 chiamate `ProviderManager.chat` e 80 tentativi HTTPX async del modello per caso, incluso Gemini selezionato dal runner corretto; 240 secondi per caso |
| Totale autonomia | 9 | 360 chiamate logiche, 720 tentativi HTTPX async del modello nel confine controllato, 36 minuti massimi di esecuzione dei casi |
| Lettura pubblica successiva | 1, `trip_today` | 7 passaggi cognitivi, fino a 14 chiamate logiche con il retry di JSON invalido; 12 HTTP route/weather complessivi; timeout 210 secondi |

Nel runner corretto il limite comprende retry e fallback che attraversano quel confine HTTPX; il tentativo eccedente viene bloccato prima del trasporto e rende il gate non superato. Il collaudo pubblico preesistente mantiene i propri fallback: il limite di 720 riguarda soltanto le nove catene autonome, non le chiamate del modello nella prova pubblica. Il job concatenato consente quindi fino a 374 chiamate logiche al manager e 39 minuti e 30 secondi per i casi, oltre all’installazione. Sono tetti di arresto, non un numero di richieste che il runner cerca di consumare. La copertura Gemini di questi limiti è provata localmente con l'SDK reale e HTTP simulato; i live storici precedenti alla correzione non la possedevano. I report dei precedenti otto casi mantengono i loro limiti originali: non vengono ricalcolati sul nuovo numero di scenari.

### Trasporto Gemini controllato nel runner

Il [boundary condiviso](../backend/scripts/phase1_read_provider_eval.py) copia
le opzioni pubbliche `HttpOptions` e seleziona HTTPX attraverso
`async_client_args.transport`, senza modificare l'adapter di produzione.
Timeout, header e altre opzioni restano conservati. Il wrapper di
`genai.Client` esiste soltanto durante il collaudo: il provider crea quel client
in ogni `chat`, anche quando `ProviderManager` è già in cache. All'uscita il
wrapper viene ripristinato e l'SDK chiude il trasporto.

Le prove verificano la scelta effettiva con aiohttp installato, il blocco
prima del trasporto per host e contesti non ammessi, i redirect non seguiti,
il contatore nel vero adapter Gemini e l'arresto del tentativo eccedente.
Una risposta riuscita senza incremento HTTP nella stessa chiamata fa fallire
il runner autonomo con `MODEL_HTTP_NOT_OBSERVED`: un client preesistente o
un altro trasporto non possono produrre un PASS con quel contatore a zero.
La diagnostica conserva la risposta osservata e non azzera cache o retry.

Il report dichiara lo scope
`httpx_async_send_attempts_including_runner_selected_gemini_sdk` e
`global_socket_dns_sandbox=false`. **Non viene dichiarato un blocco globale
di socket, DNS o trasporti diversi da quelli controllati.** La verifica locale
del budget non attesta qualità delle risposte reali o spesa effettiva.

Non viene indicato un importo monetario preventivo: il provider effettivo può cambiare con il fallback e il costo dipende dai token e dal piano configurato. Per le risposte riuscite, il report autonomo registra soltanto provider, modello e i contatori numerici disponibili `prompt_tokens`, `completion_tokens`, `total_tokens`. Non copia il resto del campo `usage`, che può contenere messaggi di errore del fallback. La dicitura `successful_responses_with_provider_usage_only` rende esplicito che eventuali richieste fallite ma fatturabili non sono incluse nei token restituiti. Il report consente di confrontare l’uso osservato con la fatturazione del provider; non certifica da solo la spesa totale.

## Runner Railway esistente: configurazione e comando

Metadata dell'audit iniziale del servizio tecnico, precedente alla PR #211.
I successivi avvii v162 e i relativi fallimenti sono riportati all'inizio:

| Campo | Valore osservato |
|---|---|
| Progetto | `ORA Staging` |
| Environment nel progetto | `production` |
| Servizio tecnico | `phase1-read-eval-v126` |
| Root / Dockerfile | `/backend` / `/backend/Dockerfile.staging` |
| Ripartenza | `NEVER`, nessun volume o dominio |
| Sorgente osservata | branch `staging/cloud`, commit `74dd1d2acc91cbb718f83913152b92dc143a8842` |
| Ultimo risultato osservato | 8 ottobre 2026, `phase2-autonomous-outcome-v140`, `mode=live`, `passed=true` |

Il risultato storico riguarda v140 su quel commit. Non prova v162 e non attraversava la nuova catena worker/outbox. Per il prossimo rerun occorre allineare la sorgente del servizio all’esatto commit della correzione v162 integrato e verificato; un redeploy della vecchia immagine può ripetere anche il vecchio comando, come osservato sopra. La valutazione deve restare un job manuale legato a quel commit, senza eseguirsi a ogni futuro push del branch applicativo.

Comando proposto per il runner tecnico, dopo integrazione del commit corrente:

```sh
env PYTHON_DOTENV_DISABLED=1 MONGO_URL=mongodb://127.0.0.1:27017 \
  DB_NAME=ora_eval_synthetic_only AMBIENT_RUNTIME=0 \
  CALENDAR_PROVIDER_MODE=fake DOCUMENT_AI_ENABLED=0 RESEARCH_ENABLED=0 \
  sh -c 'python -m pip install mongomock-motor==0.0.36 && python -m scripts.autonomy_completion_eval_v162 --mode live --output /tmp/ora-autonomy-v162-live.json && python -m scripts.phase1_read_provider_eval --mode live --max-steps 7 --output /tmp/ora-public-read-v162-live.json'
```

Il prefisso `env` vale soltanto per il processo di valutazione: il Mongo applicativo ereditato non viene usato e non si modificano le variabili persistenti del servizio. Entrambi gli harness creano un database in memoria. Si conservano le credenziali modello e la configurazione route già predisposte nel servizio. Il secondo comando parte solo se il primo supera tutti i casi: altrimenti il job resta fallito e la prova pubblica è non eseguita, senza un PASS implicito. I riepiloghi restano distinti (`ORA_AUTONOMY_COMPLETION_SUMMARY` e `ORA_PHASE1_READ_EVAL`). Non è necessario un nuovo servizio. Questa sezione prepara il comando; non attesta che sia già stato distribuito o eseguito.

## Verifiche locali precedenti all'integrazione della PR #211

Il 12 ottobre 2026, il collaudo autonomo scripted ha completato **8 casi su 8**, con zero chiamate al modello, zero HTTP esterni e zero effetti. La suite dedicata (`test_autonomy_completion_eval_v162.py` e `test_autonomy_completion_restart_v162.py`) ha prodotto **27 PASS e 1 SKIP**: lo skip è esclusivamente il caso Mongo reale con quattro processi, non disponibile nel runtime locale e obbligatorio nella CI. I due casi di revoca della memoria dopo completion sono PASS, sia con Home già visibile sia con consegna ancora pendente. Le prove live sul commit v162 e la ricezione su dispositivo non sono incluse in questi risultati.

L'aggregato backend locale finale riporta **322 PASS e 1 SKIP**, compresa la suite dedicata: l'unico skip è il gate Mongo reale descritto sopra. Il controllo frontend finale riporta **90 test su 90 PASS** fra sessione/token/cleanup, push lifecycle, adapter SDK effettivo, identità di installazione, apertura dalla notifica, auth e OAuth. Il primo giro Chromium ha trovato la perdita della destinazione dopo un nuovo login; la allowlist è stata corretta per le pagine reali del risultato e della preparazione di chiamata, mantenendo il test browser invariato. La ripetizione delle quattro nuove prove sull'export integrato con Vision #210 è **4/4 PASS**; TypeScript ed export sono PASS. Questi risultati usano trasporti e callback sintetici: non attestano un accesso OAuth esterno né una notifica ricevuta su telefono.

La prima CI ha inoltre individuato un'aspettativa legacy in `test_scheduled_discovery_continuity.py`: zero righe di stato dopo l'indisponibilità del modello. La riga dell'owner ora conserva anche la lease; il test verifica quindi l'assenza di uno scan riuscito, il rilascio della lease e il cambiamento ancora pending, poi riprova lo stesso wake e richiede il consumo solo al successo. Nodo riprodotto prima della correzione; modulo locale **4/4 PASS** dopo. Il runtime non è stato cambiato per soddisfare questa vecchia aspettativa. Il caso negativo dell'URI Mongo con credenziali sintetiche è costruito da parti per non imitare un segreto letterale nel repository; il controllo dell'intera storia Git resta invariato.

Prima dell'integrazione sono stati eseguiti anche i 50 moduli locali del gate di continuità (**231 PASS**) e altri 11 moduli dei gate successivi (**48 PASS**). I conteggi possono sovrapporsi all'aggregato precedente e non vengono sommati. I due moduli Ambient con fixture Mongo autouse e i restart opt-in restano alla CI. Due controlli statici storici sono stati riallineati senza cambiare il runtime: il refresh dei luoghi ora è provato tramite ChangeLog, Discovery e routine persistita prima dello snapshot; la non-persistenza del token Expo è verificata anche registrando tutte le scritture dell'adapter SDK su iOS e Android. Il web è verificato senza effetti nativi. La suite frontend finale comprende quindi **90/90 PASS**, inclusi i **9/9** dell'adapter SDK; il token Expo non è confuso con la credenziale di revoca conservata nello storage protetto per il logout offline.

## Quando dichiarare dimostrato il risultato

1. Suite di regressione v162 e nove casi scripted verdi sul commit in esame, incluso `already_resolved`.
2. Gate Mongo obbligatorio verde: quattro processi terminati, lettura non ripetuta, outbox recuperata e replay senza duplicati.
3. Job live autonomo verde sullo stesso commit, con chiamate reali osservate in ogni caso richiesto; missing credentials o provider outage sono risultati non superati.
4. Job pubblico verde con HTTP effettivi, fonte, orari e date coerenti; il modello deve rispettare ciò che quelle letture sostengono.
5. Revisione del testo sintetico prodotto: correttezza del confronto e dei vincoli, fonte corrente, utilità, nessuna richiesta superflua o azione inventata. Il controllo automatico è limitato a questa fixture; `human_review_still_required=true` resta esplicito. Il gate lessicale può accettare anche un'inversione dell'attribuzione dei costi alle due opzioni: per ogni caso riuscito va letto `prepared_text`, verificando importi, opzioni, differenza e vincoli, prima di accettare il risultato.
6. Per dichiarare anche il canale telefono verificato, serve una prova distinta di registrazione e ricezione su un dispositivo autorizzato. Le fixture SDK e i transport fake non bastano a dimostrarla.

Per il caso panni, le regressioni Situation v160 restano parte della CI: località fissata alla Situation, meteo datato, stima distinta da certezza fisica, esito corrente, pioggia anticipata, scadenza e chiusura esplicita. Il precedente caso personale di Tarquinia è già concluso e non viene ricreato dal collaudo. Un’eventuale fixture Tarquinia usa soltanto un owner sintetico, senza dispositivo, attività personale o formula fisica inventata.
