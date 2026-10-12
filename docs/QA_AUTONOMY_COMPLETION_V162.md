# QA v162 — iniziativa, prosecuzione e risultato

## Cosa dimostra il gate

Il nuovo [harness](../backend/scripts/autonomy_completion_eval_v162.py) mantiene collegati i servizi di produzione: admission, goal, wake persistita, claim del worker Ambient, piano, lettura della fonte, preparazione, verifica, completion, visibility, outbox e lettura della Home. Il caso `source_change_crash` parte prima dell’admission, da un cambiamento registrato: passa dallo snapshot reale e da OpportunityDiscovery prima di arrivare al risultato.

Il risultato atteso è un confronto utile, non la sola esistenza di un goal o di un testo. Una nota sintetica dichiara 15 euro al mese, 180 per dodici mesi, oppure 120 anticipati per l’anno, con pari capacità/assistenza e senza rimborso dell’annuale. ORA deve leggere la nota canonica, preparare il confronto con differenza 60, attribuire i dati alla nota e conservare il limite della mancata verifica presso il fornitore. Non viene autorizzato né tentato un cambio di contratto.

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
| `irrelevant` | Contenuto promozionale privo di bisogno documentato | Decisione `no_goal`, nessuna wake e nessuna capacità eseguita |

Il test accelera soltanto `next_run_at`, `scheduled_for` e scadenze dell’outbox nel database sintetico marcato. Prima di farlo verifica che il checkpoint esista già: non crea un retry per riparare un difetto del prodotto. La gestione delle wake resta quella di `Ambient.tick`, inclusi claim e completion.

Il mock Mongo richiede un adattatore per `find_one_and_update`: senza `_id`, mongomock cerca il documento aggiornato tramite il vecchio filtro e può restituire `None` pur avendo acquisito il claim. L’adattatore conserva `_id` durante quella ricerca e ripristina poi la proiezione richiesta. Non modifica Motor; la prova con Mongo reale e processi separati è il controllo indipendente di questo limite del mock.

## Errori concreti emersi nell’audit

| Confine | Comportamento riprodotto prima della correzione | Gate dedicato |
|---|---|---|
| Primo piano indisponibile | Una sola indisponibilità chiudeva definitivamente la goal; le wake successive vedevano lavoro chiuso | [Planning recovery](../backend/tests/test_agent_planning_recovery_v162.py) e `planning_outage` |
| Scan interrotto | Il batch di cambiamenti era consumato prima che la review fosse persistita; dopo una cancellazione il retry concludeva che nulla era cambiato | [Discovery recovery](../backend/tests/test_opportunity_discovery_recovery_v162.py) e `source_change_crash` |
| Schema della memoria | La governance scriveva `statement`/`content`, mentre la lettura automatica dipendeva dal campo legacy `summary` | [Memory reader](../backend/tests/test_agent_memory_read_v162.py) e seed canonico nel nuovo harness |
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

Le credenziali si usano tramite il runtime predisposto; non vanno stampate, esportate nel report o copiate nella documentazione. Nell’harness autonomo solo `ProviderManager.chat` apre la rete agli endpoint HTTPS del modello già consentiti dal boundary del collaudo pubblico. Restano utilizzabili soltanto `information.read` e `document.create`; un tentativo di effetto esterno, invio push, altro owner o endpoint non consentito fa fallire il gate.

Esiti CLI del nuovo harness:

| Exit code | Significato |
|---|---|
| `0` | Tutti i casi richiesti hanno soddisfatto il contratto del livello dichiarato |
| `1` | Caso non raggiunto, risultato non valido, boundary tentato o errore durante la prova |
| `3` | Live richiesto ma senza credenziali del modello: `status=blocked`, `passed=false` |

Il workflow non contiene un ramo “credenziali assenti → salta e passa”. I report includono tempi di esecuzione, eventuale commit dalla metadata CI/deployment, chiamate LLM osservate, richieste HTTP del modello, capacità eseguite, tick, guasti iniettati, livello delle fonti, risultato e testo sintetico da revisionare. I conteggi delle chiamate già avvenute sopravvivono anche a un verdetto fallito. `live_provider_reads=0` nel collaudo autonomo interno è intenzionale ed esplicito.

### Ambito e budget del live

| Passaggio | Numero di casi | Limiti applicati |
|---|---|---|
| Autonomia completa | 8: cinque completamenti utili e tre negativi | 40 chiamate `ProviderManager.chat` e 80 richieste HTTP del modello per caso; 240 secondi per caso |
| Totale autonomia | 8 | 320 chiamate logiche, 640 richieste HTTP del modello, 32 minuti massimi di esecuzione dei casi |
| Lettura pubblica successiva | 1, `trip_today` | 7 passaggi cognitivi, fino a 14 chiamate logiche con il retry di JSON invalido; 12 HTTP route/weather complessivi; timeout 210 secondi |

Il limite HTTP autonomo comprende retry e fallback all’interno del manager; il tentativo eccedente viene bloccato prima del trasporto e rende il gate non superato. Il collaudo pubblico preesistente mantiene i propri fallback: il limite di 640 riguarda soltanto le otto catene autonome, non le chiamate del modello nella prova pubblica. Il job concatenato consente quindi fino a 334 chiamate logiche al manager e 35 minuti e 30 secondi per i casi, oltre all’installazione. Sono tetti di arresto, non un numero di richieste che il runner cerca di consumare.

Non viene indicato un importo monetario preventivo: il provider effettivo può cambiare con il fallback e il costo dipende dai token e dal piano configurato. Per le risposte riuscite, il report autonomo registra soltanto provider, modello e i contatori numerici disponibili `prompt_tokens`, `completion_tokens`, `total_tokens`. Non copia il resto del campo `usage`, che può contenere messaggi di errore del fallback. La dicitura `successful_responses_with_provider_usage_only` rende esplicito che eventuali richieste fallite ma fatturabili non sono incluse nei token restituiti. Il report consente di confrontare l’uso osservato con la fatturazione del provider; non certifica da solo la spesa totale.

## Runner Railway esistente: configurazione pronta da revisionare

Audit limitato a metadata e log del servizio tecnico, senza deploy o cambi di variabili:

| Campo | Valore osservato |
|---|---|
| Progetto | `ORA Staging` |
| Environment nel progetto | `production` |
| Servizio tecnico | `phase1-read-eval-v126` |
| Root / Dockerfile | `/backend` / `/backend/Dockerfile.staging` |
| Ripartenza | `NEVER`, nessun volume o dominio |
| Sorgente osservata | branch `staging/cloud`, commit `74dd1d2acc91cbb718f83913152b92dc143a8842` |
| Ultimo risultato osservato | 8 ottobre 2026, `phase2-autonomous-outcome-v140`, `mode=live`, `passed=true` |

Il risultato storico riguarda v140 su quel commit. Non prova v162 e non attraversava la nuova catena worker/outbox. Prima di un rerun occorre allineare la sorgente del servizio all’esatto commit v162 integrato e verificato; un redeploy del vecchio commit ripeterebbe il vecchio codice. La valutazione deve restare un job manuale legato a quel commit, senza eseguirsi a ogni futuro push del branch applicativo.

Comando proposto per il runner tecnico, dopo integrazione del commit corrente:

```sh
env PYTHON_DOTENV_DISABLED=1 MONGO_URL=mongodb://127.0.0.1:27017 \
  DB_NAME=ora_eval_synthetic_only AMBIENT_RUNTIME=0 \
  CALENDAR_PROVIDER_MODE=fake DOCUMENT_AI_ENABLED=0 RESEARCH_ENABLED=0 \
  sh -c 'python -m pip install mongomock-motor==0.0.36 && python -m scripts.autonomy_completion_eval_v162 --mode live --output /tmp/ora-autonomy-v162-live.json && python -m scripts.phase1_read_provider_eval --mode live --max-steps 7 --output /tmp/ora-public-read-v162-live.json'
```

Il prefisso `env` vale soltanto per il processo di valutazione: il Mongo applicativo ereditato non viene usato e non si modificano le variabili persistenti del servizio. Entrambi gli harness creano un database in memoria. Si conservano le credenziali modello e la configurazione route già predisposte nel servizio. Il secondo comando parte solo se il primo supera tutti i casi: altrimenti il job resta fallito e la prova pubblica è non eseguita, senza un PASS implicito. I riepiloghi restano distinti (`ORA_AUTONOMY_COMPLETION_SUMMARY` e `ORA_PHASE1_READ_EVAL`). Non è necessario un nuovo servizio. Questa sezione prepara il comando; non attesta che sia già stato distribuito o eseguito.

## Verifica locale di questa revisione

Il 12 ottobre 2026, il collaudo autonomo scripted ha completato **8 casi su 8**, con zero chiamate al modello, zero HTTP esterni e zero effetti. La suite dedicata (`test_autonomy_completion_eval_v162.py` e `test_autonomy_completion_restart_v162.py`) ha prodotto **27 PASS e 1 SKIP**: lo skip è esclusivamente il caso Mongo reale con quattro processi, non disponibile nel runtime locale e obbligatorio nella CI. I due casi di revoca della memoria dopo completion sono PASS, sia con Home già visibile sia con consegna ancora pendente. Le prove live sul commit v162 e la ricezione su dispositivo non sono incluse in questi risultati.

L'aggregato backend locale finale riporta **322 PASS e 1 SKIP**, compresa la suite dedicata: l'unico skip è il gate Mongo reale descritto sopra. Il controllo frontend finale riporta **90 test su 90 PASS** fra sessione/token/cleanup, push lifecycle, adapter SDK effettivo, identità di installazione, apertura dalla notifica, auth e OAuth. Il primo giro Chromium ha trovato la perdita della destinazione dopo un nuovo login; la allowlist è stata corretta per le pagine reali del risultato e della preparazione di chiamata, mantenendo il test browser invariato. La ripetizione delle quattro nuove prove sull'export integrato con Vision #210 è **4/4 PASS**; TypeScript ed export sono PASS. Questi risultati usano trasporti e callback sintetici: non attestano un accesso OAuth esterno né una notifica ricevuta su telefono.

La prima CI ha inoltre individuato un'aspettativa legacy in `test_scheduled_discovery_continuity.py`: zero righe di stato dopo l'indisponibilità del modello. La riga dell'owner ora conserva anche la lease; il test verifica quindi l'assenza di uno scan riuscito, il rilascio della lease e il cambiamento ancora pending, poi riprova lo stesso wake e richiede il consumo solo al successo. Nodo riprodotto prima della correzione; modulo locale **4/4 PASS** dopo. Il runtime non è stato cambiato per soddisfare questa vecchia aspettativa. Il caso negativo dell'URI Mongo con credenziali sintetiche è costruito da parti per non imitare un segreto letterale nel repository; il controllo dell'intera storia Git resta invariato.

Prima dell'integrazione sono stati eseguiti anche i 50 moduli locali del gate di continuità (**231 PASS**) e altri 11 moduli dei gate successivi (**48 PASS**). I conteggi possono sovrapporsi all'aggregato precedente e non vengono sommati. I due moduli Ambient con fixture Mongo autouse e i restart opt-in restano alla CI. Due controlli statici storici sono stati riallineati senza cambiare il runtime: il refresh dei luoghi ora è provato tramite ChangeLog, Discovery e routine persistita prima dello snapshot; la non-persistenza del token Expo è verificata anche registrando tutte le scritture dell'adapter SDK su iOS e Android. Il web è verificato senza effetti nativi. La suite frontend finale comprende quindi **90/90 PASS**, inclusi i **9/9** dell'adapter SDK; il token Expo non è confuso con la credenziale di revoca conservata nello storage protetto per il logout offline.

## Quando dichiarare dimostrato il risultato

1. Suite di regressione v162 e otto casi scripted verdi sul commit in esame.
2. Gate Mongo obbligatorio verde: quattro processi terminati, lettura non ripetuta, outbox recuperata e replay senza duplicati.
3. Job live autonomo verde sullo stesso commit, con chiamate reali osservate in ogni caso richiesto; missing credentials o provider outage sono risultati non superati.
4. Job pubblico verde con HTTP effettivi, fonte, orari e date coerenti; il modello deve rispettare ciò che quelle letture sostengono.
5. Revisione del testo sintetico prodotto: correttezza del confronto e dei vincoli, fonte corrente, utilità, nessuna richiesta superflua o azione inventata. Il controllo automatico è limitato a questa fixture; `human_review_still_required=true` resta esplicito.
6. Per dichiarare anche il canale telefono verificato, serve una prova distinta di registrazione e ricezione su un dispositivo autorizzato. Le fixture SDK e i transport fake non bastano a dimostrarla.

Per il caso panni, le regressioni Situation v160 restano parte della CI: località fissata alla Situation, meteo datato, stima distinta da certezza fisica, esito corrente, pioggia anticipata, scadenza e chiusura esplicita. Il precedente caso personale di Tarquinia è già concluso e non viene ricreato dal collaudo. Un’eventuale fixture Tarquinia usa soltanto un owner sintetico, senza dispositivo, attività personale o formula fisica inventata.