# V4 — primo checkpoint pubblicato

## Secondo checkpoint — lettura documentale mirata

25/09: commit 6e052d842729608610ea639547b72a750ed0426f, deployment
d715a0cc-89f5-4db3-86a9-16af0fe58115 SUCCESS. 50 test locali PASS su quattro
suite; compileall/diff-check PASS. La funzionalità legge estratti di un
documento esplicito con riferimenti/versione, non automaticamente l'archivio.
Resta da provare scelta spontanea dei documenti e risultato utile con modello
e fonti reali; il deploy non chiude questo gate.

25 settembre 2026, 10:44 UTC / 12:44 Europe/Rome.

- Branch staging/cloud, commit bc6aef1571a5350f82917f095ac3ea8f8fc66a51.
- Railway backend deployment abc4ad59-d32c-460d-8c03-1a4c5baa18a0: SUCCESS.
- Application startup complete; GET /api/health 200 nei log runtime.
- Ambient runtime started, tick 10 s; life orchestration worker started.
- Opportunity e Agent indexes ready; primo auto_sync read=1, failed=0.
- Ambient push channel=stub: consegna push reale non verificata né attiva
  attraverso quel provider. Non equivale a fallimento del lavoro backend.

La chiamata di orchestrazione deploy ha restituito timeout 504, ma il deploy
è proseguito: verificato per ID e SHA, senza inviare una seconda richiesta.
Nessuna applicazione delle patch staged di servizi diversi dal backend.

183 test locali PASS nel checkpoint precedente. Questo smoke test cloud
dimostra startup/health/runtime attivo, non una prova completa di iniziativa,
ricerca, confronto e risultato su dati sintetici con provider reali.
Restano i gate di AUTONOMY_PROGRAM.md; prossimo collegamento A1: contenuto
documentale mirato, oggi l'agente legge metadati.

## 2026-09-25 — V4: ciclo documentale e falsi eventi

Il ciclo admission → pianificazione → lettura → evidenze → verifica è
verificato su documenti sintetici brevi e paginati con decisioni AI controllate.
Un risultato partial ora attiva reconsider; il modello riceve source_refs e
observed_at e istruzioni per trattare documenti come dati non attendibili,
mai come autorizzazioni. Non è prova di iniziativa del modello reale.

La prova UI cloud ha rilevato un falso exhibition_ticket nel documento
sintetico sui costi: la ricerca per sottostringa leggeva mostra in dimostrativo.
La tassonomia ora usa confini lessicali, conservando i due stem intenzionali.
La regressione attraversa anche analyze_document e vieta eventi inventati
per questa fixture. 60 test mirati PASS; nessuna dipendenza runtime, schema
Mongo o configurazione nuova. Rianalisi cloud e risultato spontaneo restano
da verificare dopo il deploy. Nessun acquisto o calendario modificato.

## 2026-09-25 — V4: documenti nella valutazione preventiva

Lo snapshot di discovery ora include fino a sei documenti recenti attivi del
solo proprietario, con anteprima non verificata di massimo 1.200 caratteri,
riferimento document:id, versione SHA256 e disponibilità del testo. Accesso
tramite il gate document.read; fonte indisponibile distinta da archivio vuoto.
La versione entra nel fingerprint: anche cambiamenti oltre l'anteprima
richiedono rivalutazione. Il prompt distingue fonti, istruzioni e casi ipotetici.
Non si forza ogni documento a diventare opportunità e non si presume che
un documento sintetico rappresenti un contratto reale dell'utente.

65 test mirati PASS (decisioni modello controllate), compileall/diff-check PASS.
Nessuna dipendenza runtime, configurazione o migrazione. Limite esplicito:
sei documenti recenti, nessuna garanzia di copertura dell'intero archivio.
La selezione spontanea con modello live e il risultato utile restano gate aperti.

Il checkpoint precedente 42a3f1f90547012a4356f797c2165ac0b48056db è su Railway,
deploy c4af7aca-5fef-46fe-94fd-9d0101b4dfaf SUCCESS. Rianalisi UI del documento
sintetico conferma categoria Documento/generic, senza appuntamento proposto.
Nessun messaggio, acquisto o evento calendario esterno eseguito.

## Quarto checkpoint pubblicato — 25/09, 13:15 Europe/Rome

Commit 1f612bb1f3ccd700809c4deacc096c5e2a5a135c, Railway backend deployment
a941cd60-7a68-41b1-b5d6-022dea82dc75 SUCCESS. Log: Ambient runtime started,
Application startup complete, GET /api/health 200. 65 test locali PASS.
Nessuna altra variabile o servizio modificato.

Verifica UI precedente: documento di prova ora generic, senza evento proposto.
Difetto UI ulteriore osservato, ancora aperto: SuggestedPanel.tsx associa
needs_review sempre a testo illeggibile/copia più chiara, anche quando la
classificazione generica a bassa confidenza è l'unico motivo di revisione.
Il documento sintetico non rappresenta un contratto reale: non si pretende
un'offerta commerciale o un risparmio reale come esito del test. Nessun
confronto spontaneo live validato; la prova locale con modello controllato
non chiude il gate di qualità dell'iniziativa.

## 2026-09-25 — V4: riesame dopo estrazione e cambiamenti di vita

L'estrazione salva extracted_text_hash insieme al testo. Il sensore documenti
osserva il digest, senza copiare contenuto nei segnali: il testo arrivato dopo
la prima osservazione provoca document.updated; una riestrazione identica
non genera rumore. I record storici privi di hash restano compatibili, senza
backfill. Nessuna nuova integrazione o dipendenza runtime.

Il fingerprint della discovery comprende ora anche situazioni, disaccordi,
quadro economico e fonti indisponibili: prima un cambiamento solo in queste
fonti poteva essere saltato come già esaminato. Log a contatori distinguono
review silenziosa, opportunità, errore e risultato admission senza contenuti
o identificativi personali. Il messaggio needs_review non presume più OCR
fallito o necessità di una copia più chiara.

71 test PASS su nove suite mirate. La prova integrata parte dalla discovery
documentale effettiva, passa per admission/background e termina con evidenze
lette; restano controllate le decisioni AI. TypeScript noEmit, export web,
compileall e diff-check PASS. Il modello live ha risposto nei log del cloud,
ma ciò non dimostra da solo un risultato utile autonomo. Serve ancora il gate
positivo live in ambiente isolato; la fixture dimostrativa non è un contratto
reale e non deve produrre false raccomandazioni personali.

## 2026-09-25 — V4: risultato preparato reale, non solo dichiarato

Rimosso il falso successo di prepare_locally: ripeteva il nome dell'azione
senza creare alcuna bozza. Ora richiede evidenze del medesimo proprietario
e obiettivo, produce contenuto tramite modello, valida i riferimenti citati
e salva prepared_text/prepared_sources dentro agent_goals prima del successo.
Nessuna raccolta o indice nuovo. Bozze precedenti non sono fonti indipendenti.
Obiettivi chiusi o non appartenenti all'utente non possono essere modificati.
La bozza completa è visibile nel dettaglio dell'aggiornamento; non equivale
a un'azione esterna o a un fatto verificato indipendentemente.

78 test mirati PASS, TypeScript noEmit/export web e compilazione Python PASS.
Script opt-in scripts/autonomy_model_smoke.py: sola diagnostica di discovery,
admission e piano con modello reale e persona interamente sintetica. Non
importa deps/server, non legge Mongo e non esegue capability. Deadline 150 s,
esito esplicito anche su errore; non blocca l'avvio dell'app. Non prova il
ciclo completo in produzione. Esecuzione manuale nel predeploy temporaneo,
poi ripristino della configurazione precedente.

### Esito prima diagnostica live e correzione ammissione

Deployment backend b91e973b-959d-4994-bdae-451ef1ae582c e frontend
5024b1aa-9780-4d1d-a947-a51bec418507, SHA 6f3f4b5055f01dc4266afe38d0679d798f650bf5,
SUCCESS. Health 200. La diagnostica live ha trovato un'opportunità fondata,
ma admission ha deciso no_goal perché informativa: gate di pianificazione
NON passato. Non è prova che ogni risposta informativa richieda un goal.
Il prompt conteneva però una scorciatoia esplicita: inform/recommend di norma
no_goal e solo obiettivi con più passi. Rimossa: anche un singolo approfondimento
utile può essere avviato, mentre una risposta già completa non va trasformata
in lavoro superfluo. Aggiunto secondo caso diagnostico con condizioni mancanti
nelle pagine successive. Primo esito preservato; nessun successo live inventato.
Predeploy diagnostico temporaneo ripristinato a [] dopo la prima esecuzione.

### Seconda diagnostica live: esito misto, contesto ripristinato

SHA b79b91be8a6f55df2f7802f0501102eadfed6a15, deploy
2dd489a9-8158-43ef-bd7d-be5482092eac. Caso con prezzi completi:
discovery fondata → create_goal → piano di due passi, lettura della fonte,
nessuna domanda iniziale o esecuzione esterna: gate parziale live PASS.
Caso con condizioni nelle pagine successive: discovery fondata ma no_goal,
gate FAIL. Non si estende il primo successo al secondo caso.

L'ammissione riceveva il riassunto senza gli estratti citati. Ora rilegge solo
le anteprime documentali citate, filtrate per proprietario/archivio/cancellazione
e permesso, con troncamento e indisponibilità espliciti. Lo stesso contesto
entra nella diagnostica isolata. 79 test locali PASS, compileall/diff-check PASS.
Il gate live dell'approfondimento resta da rieseguire; l'esecuzione completa
con modello reale non è ancora verificata. Predeploy di nuovo ripristinato a [].
