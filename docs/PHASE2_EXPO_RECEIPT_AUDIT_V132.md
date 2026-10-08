# ORA v132 — Ricevute Expo senza falsi claim di consegna

L'accettazione iniziale di una richiesta Expo non dimostra che sia stata inoltrata ad APNs o FCM, e neppure che il dispositivo abbia mostrato la notifica. La documentazione Expo raccomanda di verificare le ricevute circa 15 minuti dopo l'invio; sono disponibili fino a circa 24 ore.

Questa revisione limita l'invio a endpoint Expo attivi con permesso granted, verifica che ci sia un ticket per ogni destinatario e memorizza gli identificativi necessari alla successiva lettura di ricevute, senza token, testo o altri dati personali nel registro di audit.

Il servizio ExpoReceiptAudit interroga getReceipts con un lotto limitato, conserva lease e retry nel database, classifica l'esito come handoff_confirmed, rejected o unconfirmed, e disabilita DeviceNotRegistered soltanto se l'endpoint appartiene ancora allo stesso account. Le vecchie registrazioni scadono tramite TTL.

Il controllo viene eseguito nella corsia delivery-admission già esistente: nessun worker o cron di sviluppo aggiuntivo. Gli errori temporanei producono rinvii, non nuove notifiche duplicate.

I test usano Mongo sintetico e HTTP Expo simulato: successo multi-dispositivo, permessi negati, ticket incompleti, ricevute assenti, errori del provider, riassegnazione di account e isolamento tra proprietari.

Limiti: il campo storico Delivered significa ticket accettato, non notifica vista. Una ricevuta positiva conferma soltanto l'inoltro al servizio Apple/Google. La prova della comparsa sul telefono richiede dispositivi e ricevute lato client. Se il database non riesce a registrare un ticket già accettato, non viene reinviata la notifica per evitare duplicati, ma l'audit resta incompleto.

Documentazione: https://docs.expo.dev/push-notifications/sending-notifications/