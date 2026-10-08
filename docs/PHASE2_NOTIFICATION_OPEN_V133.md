# ORA v133 — Notifica aperta → contenuto corretto → esito registrato

Una richiesta push e la sua ricevuta Expo non dimostrano che una persona abbia aperto una notifica. Questo intervento collega il tocco sull'avviso alla schermata dell'app **senza** concedere autorità ad eseguire azioni.

Il client iOS/Android ascolta gli eventi di risposta e l'ultimo evento pendente al lancio, anche se la sessione autenticata si apre successivamente. Per evitare duplicati tiene una chiave per account, notifica e piano. Il backend registra il piano aperto solo se appartiene all'utente autenticato ed era già nello stato delivered (ticket accettato dal provider).

Il payload Expo NON decide dove navigare. Il client consente soltanto un sottoinsieme noto di percorsi relativi, invia esclusivamente l'identificativo opaco del piano a Delivery, e naviga solo quando il server conferma l'apertura e restituisce lo stesso percorso canonico costruito dal codice. Un percorso esterno, modificato o che suggerisce di autorizzare un goal non viene aperto. Il tap non crea né esegue lavoro.

Si mantengono due risultati separati: provider accepted, ricevuta Expo; e opened_at, il tocco effettivamente registrato dall'utente nell'app. La conferma del tocco non prova che l'OS abbia mostrato la notifica sul lock screen prima dell'apertura.

Test: permessi per account, piani non inviati, link manipolati, idempotenza dei tap, percorsi opportunity e agent need, controllo frontend dei link, TypeScript e bundle iOS. Restano da eseguire prove reali su dispositivi con l'app installata e notifiche abilitate.

Commit di base: 51f3355 (v132). Nessuna azione sensibile è autorizzata da questa modifica.