# ORA v131 — Collaudo della consegna dei promemoria ad app chiusa

## Perché

La v130 preserva ricordi e promemoria dopo gli arresti del server. Resta separata la prova della **consegna**: un promemoria scaduto viene trasformato in un'Opportunity, analizzato dalla politica di Delivery, eventualmente affidato a Expo e infine mostrato dal sistema operativo del dispositivo. Ognuno di questi confini richiede una prova distinta.

## Test isolato

Il test `test_recurring_memo_delivery_v131.py` usa il codice reale di Memo, OpportunityRepository, DeliveryAdmission, DeliveryService, PushEndpointService e ExpoNotificationProvider. Crea soltanto un utente, un compleanno e un token Expo **sintetici**. Sostituisce esclusivamente il giudizio AI, il contesto di permesso del dispositivo e l'HTTP esterno Expo con risposte deterministiche: non vengono inviate notifiche vere.

Il percorso positivo verifica un memo valido e autorizzato, una Opportunity salvata, un giudizio di push, il controllo del permesso reale del servizio, l'adapter Expo con messaggio pubblico per la schermata bloccata, il deep link e la deduplicazione delle successive revisioni.

## Protezioni aggiunte

Un'Opportunity derivata da un memo ricorrente non basta come prova perpetua. Prima della decisione e prima del passaggio a Expo, il codice verifica che: (1) Memo e Memory siano ancora attivi e dello stesso proprietario, (2) la prova Memory della Opportunity punti esattamente al Memo, (3) la data oggi corrisponda alla ricorrenza ancora autorevole e (4) l'Opportunity non sia scaduta. Se il ricordo viene dimenticato o corretto nel frattempo, l'invio deve essere annullato. Le altre tipologie di Opportunity non cambiano.

I test negativi coprono revoca del ricordo prima della decisione, correzione dopo la pianificazione, permesso push negato e token di un altro utente.

## Limiti

- Il risultato `ok` del provider rappresenta **accettazione da parte di Expo**, non prova che la notifica sia comparsa sul telefono. Questa prova richiede un dispositivo reale, permessi e una ricevuta lato client.
- Il test mantiene reale la logica del gate sui permessi, ma sostituisce con dati sintetici la lettura del consenso. Non dimostra che un particolare telefono sia connesso.
- Gli errori transitori del canale Expo e i casi di accettazione con ricevuta persa restano soggetti a verifiche aggiuntive prima di promettere consegna affidabile.
- Nessuna modifica estetica o automazione di sviluppo è inclusa.
