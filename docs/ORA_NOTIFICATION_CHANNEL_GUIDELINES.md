# ORA: invio autonomo WhatsApp — rilascio e controlli

## Come funziona

1. Il motore ORA esistente valuta se un evento ha un esito utile e merita
   un'interruzione. Senza tale decisione, WhatsApp **non** invia nulla.
2. L'utente associa il proprio numero e sceglie esplicitamente
   "Attiva avvisi WhatsApp" in ORA → Connessioni e servizi. Associazione
   e consenso sono due operazioni diverse. Nessun utente esistente è
   abilitato automaticamente.
3. La stessa DeliveryService verifica la sorgente prima di eseguire la
   consegna; ammette poi una sola notifica in una coda Mongo persistente.
4. Il worker WhatsApp ricontrolla proprietario, numero collegato, consenso,
   sorgente ancora attiva e scadenza prima dell'invio.
5. Entro la finestra WhatsApp di assistenza invia solo il testo definito
   come pubblico per la schermata di blocco. Non invia note private.
6. Fuori dalla finestra, Meta ammette soltanto un **template approvato**.
   ORA usa un template statico senza variabili personalizzate. Non invia
   testo libero fuori finestra. L'approvazione Meta va verificata nel WABA
   reale, non dedotta dalla presenza di una variabile.
7. L'accettazione HTTP 200 di Meta viene registrata come "accepted",
   mai come "delivered". I webhook firmati aggiornano sent, delivered,
   read o failed; la coda non ripete un messaggio dall'esito incerto.

## Passaggio Meta necessario per gli avvisi oltre 24 ore

Nel WhatsApp Manager della WABA di ORA creare un modello di messaggio
coerente con gli aggiornamenti transazionali/di servizio dell'app, nel
rispetto della categoria che Meta autorizza.

Esempio di testo statico, senza informazioni personali:

  ORA ha un aggiornamento importante per te. Apri ORA o rispondi a questa
  chat per conoscere i dettagli.

Nome suggerito: ora_aggiornamento_importante
Lingua: Italiano (codice it)

**Non attribuire a Meta un'approvazione automatica**: nome/categoria/testo
sono una proposta, soggetta a revisione. Dopo approvazione nel WABA giusto,
impostare sul backend Railway:

  WHATSAPP_ALERT_TEMPLATE_NAME = nome reale approvato
  WHATSAPP_ALERT_TEMPLATE_LANGUAGE = it

Non servono nuove copie del token WhatsApp se quello di sistema è valido.
Il modulo non funziona fuori finestra senza template approvato e configurato.

## Verifica operativa

- App ORA → Connessioni e servizi → WhatsApp: scegliere Attiva avvisi.
- Verificare che non compaiano avvisi senza consenso.
- Creare un caso reale con un esito utile, lasciare che sia ORA a valutarlo
  e a produrre la normale delivery plan.
- Controllare il log di consegna autenticato: pending, accepted e delivered
  sono tre stati distinti. Non chiamare "consegnato" un accepted.
- Verificare l'avviso dentro e fuori la finestra Meta.
- Revocare il consenso; ogni avviso non ancora inviato deve essere cancellato.
- Provare modifica/cancellazione dell'evento prima della consegna:
  niente notifiche obsolete o deduzioni inventate.
- Verificare che due worker simultanei non inviino due volte lo stesso piano.
- Verificare ricevute duplicate e fuori ordine; nessuna regressione dello stato.

## Limiti intenzionali

- La prima versione notifica SOLO eventi già classificati da DeliveryService
  come meritevoli di push: non trasforma tutte le card in avvisi.
- Quando non c'è un titolo/corpo pubblico sicuro invia un messaggio generico.
- Per copiare tutti i contenuti specifici anche oltre le 24 ore occorreranno
  template approvati con parametri e una progettazione privacy separata.
- Non sono previsti invii di prova non richiesti, invii a non associati o
  attivazioni massive. Fuori dalla finestra non sono consentite scorciatoie.
