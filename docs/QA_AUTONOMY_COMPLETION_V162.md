# QA v162 — iniziativa, prosecuzione e risultato

## Ultima verifica locale: stato dell'esito e report revisionabile

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

La prossima prova reale è diagnostica e limitata a `completed_result`,
`source_change_crash`, `already_resolved` e `irrelevant`, senza cambiare la
fixture. Il gate completo di nove casi e la successiva lettura pubblica
restano necessari dopo la diagnosi; la loro riuscita non è presunta.

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
