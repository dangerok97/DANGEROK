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
