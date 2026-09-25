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
