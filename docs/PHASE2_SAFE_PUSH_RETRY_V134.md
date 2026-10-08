# ORA v134 — Ripresa sicura delle notifiche rifiutate da Expo

## Obiettivo

Un errore temporaneo del provider non deve lasciare una notifica importante in attesa senza una nuova verifica. Tuttavia, ripetere una richiesta dall'esito incerto può provocare notifiche duplicate; la sicurezza precede il tentativo di recupero.

## Regole implementate

- Solo una risposta HTTP 429 esplicita dell'API Expo autorizza un ulteriore controllo programmato: l'intero lotto è stato rifiutato. Timeout di rete, HTTP 5xx con stato di accettazione incerto, numero di ticket non corrispondente o accettazione parziale **non** abilitano un reinvio automatico.
- Dopo un rifiuto esplicito, il piano già approvato dalla Delivery policy resta in stato held, con numero di tentativi e prossimo controllo salvati nel database. Il backoff è 5, 10 e 20 minuti; massimo tre nuovi controlli. Il limite di validità originale della notifica non può essere superato.
- Un record AmbientWake persistente di tipo retry viene creato nella coda già esistente; non vengono aggiunti nuovi worker né timer di sviluppo. Il risveglio rilegge la fonte, il consenso alla notifica, il contesto e il giudizio del modello. Non invia ciecamente il vecchio messaggio.
- Un passaggio del servizio Delivery admission recupera i wake mancanti quando il processo si interrompe dopo aver salvato il piano. Il recupero non chiama Expo e non consulta il modello.
- Nessuna notifica viene inviata se il soggetto originale è stato risolto; un piano scaduto o una finestra troppo breve non genera nuove sveglie. Il client può mostrare la data del prossimo controllo senza promettere una consegna.

## Collaudi

`tests/test_safe_push_retry_v134.py` usa account, opportunità, token e ticket sintetici, con l'adapter Expo reale ma HTTP simulato. Copre HTTP 429, riuscita dopo ri-valutazione, riavvio tra piano e wake, rete incerta, ticket incompleti, accettazione parziale su più dispositivi, chiusura della fonte, finestra scaduta, limite dei tre tentativi e isolamento per account. I test non emettono notifiche reali.

## Limiti

Non è una garanzia di recapito sul telefono. Un HTTP 429 è una risposta esplicita di rifiuto dell'intero lotto; l'assenza di risposta potrebbe invece nascondere una richiesta già accettata, perciò il prodotto conserva la situazione in-app senza ritentare automaticamente. I casi di errore alle ricevute Expo vengono registrati separatamente. Una conferma da Expo/APNs/FCM non significa che l'utente abbia effettivamente visualizzato la notifica.

Riferimento: https://docs.expo.dev/push-notifications/sending-notifications/