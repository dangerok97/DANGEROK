# ORA v156 — Accesso Google web su iPhone senza pulsante invisibile

**Difetto osservato**: la pagina Login su Chrome iOS mostrava lo spazio riservato al bottone Google ma non il bottone. La configurazione Google risultava presente sia su ORA Web sia sul backend Railway; il widget Google Identity Services era caricato dinamicamente, con UX popup anche su iOS. Google richiede il flusso redirect in quel contesto (https://developers.google.com/identity/gsi/web/guides/supported-browsers).

## Soluzione

Su Chrome/Safari iPhone/iPad la schermata presenta un vero pulsante **Continua con Google**. A differenza dell'iframe/popup, apre una pagina Google tramite Authorization Code + PKCE, con stato e nonce casuali validati lato server. La pagina torna a ORA nella stessa scheda e conferma l'accesso con un biglietto monouso vincolato a una prova che resta nel `sessionStorage` di quella scheda.

Il backend riusa il **client OAuth Google già configurato** e l'URI callback già registrato per il calendario, ma la nuova richiesta contiene **solo `openid email profile`**: non collega Google Calendar, non richiede permessi calendario, non copia impegni e non salva refresh token. Gli stati di login e di sincronizzazione Calendar sono in collezioni distinte e una richiesta di login non può diventare una connessione al calendario.

Il biglietto di completamento appare **solo nel frammento dell'URL** (mai in una richiesta HTTP). Non contiene né credenziali Google né JWT ORA; è valido per due minuti, utilizzabile una volta e richiede una prova non presente nell'URL. Stato PKCE e nonce scadono dopo dieci minuti. Le chiavi Mongo TTL puliscono i documenti. Il risultato finale è il normale JWT di sessione ORA ricevuto via POST HTTPS e persistito nel gestore autenticazione esistente.

Sugli altri browser il widget ufficiale Google resta in uso; se lo script non genera un pulsante, la pagina mostra un messaggio e un metodo di accesso Google con redirect invece di lasciare spazio bianco.

## Sicurezza e limiti

- Le pagine di ritorno sono limitate agli origin presenti in `FRONTEND_URLS` / `FRONTEND_URL`; mai redirect arbitrari.
- Il callback verifica firma Google, `aud` uguale al client OAuth server, `iss`, `exp` e nonce; sessioni di callback e ticket sono monouso.
- Un account ORA con password e stessa email Google non viene collegato automaticamente: prima accesso email/password, poi collegamento esplicito dalle impostazioni.
- Gli endpoint sono soggetti a rate limit. Nessun token o client secret stampato nei log o inserito nel codice.
- I test di regressione utilizzano credenziali e soggetti sintetici: non costituiscono una prova di accesso live su uno specifico iPhone.

## Collaudo

Eseguire i test `backend/tests/test_google_browser_login_v156.py`, il controllo UI `frontend/src/auth/googleBrowserRedirect.regression.test.ts`, i test autenticazione preesistenti e la CI completa. Dopo il deploy controllare `/api/auth/providers`, `/api/health`, `/healthz` e l'apertura del login da Chrome iOS. Non effettuare login reale con l'account di un'altra persona in test.
