# ORA v137 — Cursore di recupero protetto tra istanze

## Risultato concreto

La v136 ha introdotto un cursore Mongo persistente e indicizzato per leggere gli obiettivi scaduti a pagine. Con più backend attivi, senza un claim sul cursore due istanze potevano leggere la stessa pagina e sovrascrivere i progressi reciprocamente. Il planner/worker degli obiettivi possiede già lease separati, ma quei lease non serializzavano la **scansione condivisa**.

Il recupero mantiene il cursore in un documento singolo e ora ne reclama l'uso con find_one_and_update atomico, token casuale e lease di 120 secondi. Solo il proprietario del token può spostare i tre campi next_run_at / owner_id / id. Al termine l'istanza rilascia il lease in ogni caso; un arresto del processo lascia il lease recuperabile dopo la scadenza. Nessun nuovo scheduler o worker; il limite di pagina esistente resta 32-128.

## Test sintetici

1. Due chiamate concorrenti: la prima trattiene il claim Mongo, la seconda non programma lavoro né modifica il cursore.
2. Un worker terminato lascia un lease non scaduto, quindi nessuna modifica prematura; dopo la scadenza il lavoro prosegue.
3. Un errore durante la programmazione rilascia il claim e consente un nuovo tentativo senza perdere il cursore.
4. Le due autorizzazioni di esecuzione restano indipendenti: niente risveglio ordinario se una delle due attende l'utente; un aggiornamento esplicito delle fonti è ancora riesaminabile senza agire al suo posto.

## Limiti

Questa protezione evita la concorrenza sul cursore e conserva il contratto del job. Non dimostra da sola che l'agente completi qualsiasi azione reale; il completamento rimane vincolato alle skill, all'evidenza disponibile e alle autorizzazioni specifiche. Un worker scaduto può ancora tentare un effetto già iniziato: gli effetti reali devono continuare ad essere protetti dalla loro idempotenza e rilettura.

Il cursore contiene riferimenti tecnici sintetici o di account nel database interno; non viene esposto nelle notifiche né a provider esterni. Nessun test usa account personali.