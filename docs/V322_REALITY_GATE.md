# V3.22 — prova conclusiva sul cloud

Stato al 25 settembre 2026: preparata, non eseguita. Usare esclusivamente
un evento dedicato «ORA TEST V3.22» e il numero del proprietario già usato
per le prove. Non coinvolgere contatti o appuntamenti reali. Concordare con
il proprietario il momento delle chiamate e la creazione dell'evento test.

## 1. Decisione e richiamata

1. Creare l'evento test per un giorno futuro, 16:00–17:00 Europe/Rome.
2. Preparare una missione per spostarlo alle 18:00; autorizzare la chiamata.
3. Il destinatario rifiuta le 18:00 e propone le 19:00, senza confermare uno
   spostamento. ORA deve riportare la proposta e chiedere una decisione.
4. Accettare la proposta dal resoconto. Deve apparire una richiamata pronta,
   senza composizione automatica. Ricaricare il dettaglio: deve restare pronta.
5. Premere «Chiama ora» una volta e confermare le 19:00 al telefono.
6. Dopo il saluto di ORA, rispondere «arrivederci»: nessun secondo saluto;
   chiusura dopo la fine del parlato. Il dettaglio segue l'esito e il calendario
   mostra un solo evento alle 19:00–20:00, conservando lo stesso ID.

Registrare ID missione, prima call, richiamata, evento e application; stati
prima/dopo reload; esito carrier, transcript finale e stato sincronizzazione.
Non considerare una risposta HTTP positiva prova sufficiente di applicazione.

## 2. Conflitto durante la chiamata

1. Con lo stesso evento test ripristinato alle 16:00–17:00, preparare una nuova
   missione per spostarlo alle 18:00.
2. Avviare la chiamata; prima della conferma del destinatario modificare
   l'evento tramite ORA alle 17:00–18:00 e verificare la sincronizzazione.
3. Solo dopo, il destinatario conferma le 18:00 per la missione originaria.
4. Atteso: application `conflict`; nessuna sovrascrittura delle 17:00,
   nessun evento duplicato e resoconto che distingue accordo telefonico da
   modifica calendario non applicata. Reload e recovery non devono forzare
   lo spostamento.

Registrare ID evento prima/dopo, snapshot della missione, stato application,
orario canonico e provider. Se una precondizione manca, interrompere la prova
e marcarla non conclusiva. Non iniettare esiti telefonici o modifiche Mongo
per far passare il gate. Lasciare l'evento identificabile; rimuoverlo solo con
consenso del proprietario.

## Evidenza già disponibile

- Due chiamate cloud `deliver_message` completate.
- Correzione saluto finale pubblicata; 134 test voce mirati PASS.
- 87 test application/continuation/recovery PASS, eseguiti il 25/09 con
  `pytest --noconftest` sui tre file `test_post_call_application_v315.py`,
  `test_needs_user_continuation_v317.py`, `test_post_call_recovery_v322.py`.
- Queste prove locali non chiudono i due gate cloud descritti sopra.
