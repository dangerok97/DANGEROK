# ORA — Fase 2 v142: risultato Home persistente attraverso interruzioni

## Difetto riprodotto

La v141 impedisce ai worker concorrenti di decidere due volte di mostrare la
stessa informazione. Tuttavia la decisione è registrata su `agent_updates`
**prima** della successiva scrittura della `AmbientActivity` per la Home.
Se Mongo è temporaneamente indisponibile o il processo si interrompe fra le
due scritture, il risultato era già segnato come «detto» ma non compariva nella
Home; riaprire l'obiettivo completato non ripete la comunicazione.

## Correzione mirata

Il medesimo record owner-scoped `agent_updates` custodisce ora uno stato
`home_pending` e la prossima data di tentativo. Non si introduce una nuova
coda, uno scheduler orario, né un secondo modello di visibilità.

* Solo la visibilità già decisa e ancorata a prove entra nell'outbox.
* `VisibilityService.show` inserisce una `AmbientActivity` con ID
  deterministico calcolato dall'owner e fingerprint della notizia. La scrittura
  nel repository Delivery usa un upsert `$setOnInsert`: se l'Activity è
  stata già creata ma il processo è morto prima dell'ACK, il recupero non
  altera la data originale e non crea una seconda riga.
* Solo dopo la scrittura Home riuscita viene chiuso `home_pending`.
* Il worker `delivery-admission` già attivo rilegge al massimo quattro
  notizie pendenti per passaggio, senza chiamare il modello, inviare push,
  creare ActionIntent o interagire con servizi esterni.
* Un errore transitorio rinvia un nuovo tentativo di due minuti. Una fonte
  obiettivo cancellata o abbandonata non viene annunciata a posteriori.
* I record storici senza `home_pending` **non** vengono ripubblicati:
  nessuna notifica retroattiva, nessun backlog trasformato in spam.

Questo protegge la registrazione Home dalle finestre di crash e dalla
concorrenza. Il blocco owner-scoped resta in Mongo.

## Test CI

`tests/test_phase2_durable_home_outbox_v142.py` verifica errore alla prima
scrittura, recupero e ACK; crash simulato dopo insert prima di ACK; due worker
concorrenti e account separati; goal cancellato; storia legacy non rielaborata.
Il test usa servizi reali di persistenza su dati sintetici, ma nessun provider
notifiche o dispositivo.

## Limiti

Il recupero Home non equivale al recapito di una push o al rendering della
schermata su iOS/Android. Una mancata comunicazione `NeedService` in presenza
di altri guasti ha un suo contratto di retry e non è certificata da questo
intervento. La decisione iniziale del modello e la verifica semantica restano
separate. In caso di blackout Mongo non c'è recupero finché il DB non torna.
