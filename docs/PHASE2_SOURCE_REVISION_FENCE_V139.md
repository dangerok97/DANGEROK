# ORA v139 — Protezione degli obiettivi da fonti cambiate

## Problema verificato nel codice

L'ammissione di una nuova opportunità usava già un token Mongo e un
`agent_review_revision` per non registrare come conclusa una valutazione
vecchia. Tuttavia `AgentService.consider()` poteva creare un nuovo obiettivo
*prima* che l'ammissione controllasse se il suo ragionamento era ancora valido.
Se, durante la risposta del modello, un messaggio veniva corretto, una
prenotazione annullata o la stessa valutazione veniva reclamata da un altro
backend, il goal provvisorio poteva riferirsi ai vecchi fatti.

## Modifica

Il claim corrente (owner, opportunità, revisione, token del lease) viene
passato come **contesto tecnico non visibile al modello** al medesimo
`AgentService.consider()` usato per tutte le richieste. Prima di inserire
un nuovo goal spontaneo, il servizio rilegge la fonte: deve esistere,
appartenere al medesimo utente, essere attiva e non scaduta, e mantenere sia
la revisione sia il token iniziale.

Dopo l'inserimento viene ripetuto il controllo: qualora la fonte cambi
nell'intervallo tra verifica e scrittura, il nuovo goal viene marcato
`abandoned`, senza pianificazione, comunicazioni o wake. La revisione
successiva rimane in coda e sarà valutata con le informazioni aggiornate.
La funzione risponde `unavailable`, non finge `no_goal` o `create_goal`.

Le richieste dirette dell'utente **non** dipendono da un lease di admission
e conservano il loro flusso; non nasce un secondo orchestratore.

## Test

`tests/test_agent_source_revision_fence_v139.py` copre:
- modifica della fonte mentre il modello decide, seguita da rivalutazione valida;
- fonte risolta durante il ragionamento;
- lease preso da un altro worker mentre il vecchio worker sta pensando;
- revisione che cambia proprio dopo l'inserimento, con abbandono del goal
  provvisorio e successiva creazione di uno solo nuovo.

I test usano dati e modello fittizi ma il codice reale di ammissione,
persistenza e sveglie. La CI ordinaria li esegue su ogni PR.

## Limiti

Non è una transazione Mongo multi-collezione. Se un altro componente
osservasse il nuovo goal tra l'inserimento e il controllo successivo, potrebbe
vedere per un istante un record ancora attivo. Prima di compiere effetti,
il worker applica comunque la verifica della fonte corrente e delle
autorizzazioni. Questo intervento chiude la finestra del ragionamento e del
salvataggio, ma non equivale a un collaudo di azioni esterne o a un'app iOS
nativa completamente verificata.
