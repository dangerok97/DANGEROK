# Pubblicare Dangerok online (guida passo passo)

> **Solo dati inventati finche' il tuo Comando non ha autorizzato l'uso.** Questa guida serve a mettere online
> l'app per visionarla e provarla. Non caricare atti o dati di contribuenti reali su un servizio esterno senza
> aver verificato le regole del Comando (cloud, AI esterne, localizzazione dei dati).

## Scelta consigliata per la prova: Render (regione Frankfurt) + Postgres gestito
Ho scelto Render perche' pubblica direttamente da un repository GitHub con un `Dockerfile` (gia' pronto),
offre certificato HTTPS automatico, un database Postgres gestito e la regione di Francoforte (UE). Non ho potuto
consultare le pagine ufficiali di prezzi e piani: **controlla tu i costi prima di attivare qualsiasi servizio**.
Alternative equivalenti: Railway, Fly.io; per un controllo maggiore dei dati, un provider europeo con server
dedicato/VPS (es. Hetzner, OVHcloud, Scaleway), che richiede piu' gestione.

## Perche' non MongoDB
L'app usa un database **relazionale** (SQL). MongoDB e' un'altra famiglia: per usarlo andrebbe riscritto il livello
dati e non darebbe vantaggi. Quello che hai scaricato e' inoltre un MongoDB **locale** sul tuo computer, mentre serve un
database **online**. Puoi ignorarlo o disinstallarlo. Il database giusto e' Postgres (gia' supportato).

## Passi
1. **Repository privato**: su GitHub verifica che `dangerok97/DANGEROK` sia *Private*.
2. **Chiavi segrete** (sul tuo computer, con Python installato):
   ```bash
   pip install -e ".[dev]"
   python -m app.cli genera-chiavi        # stampa DATA_KEY e SESSION_SECRET: conservale in un posto sicuro
   python -m app.cli prepara-accesso      # password + QR per l'app di autenticazione; stampa 2 variabili
   ```
   **Perdere DATA_KEY significa perdere i dati cifrati**: fanne una copia (es. gestore di password).
3. **Database**: nel provider crea un database **PostgreSQL** nella stessa regione del sito (Frankfurt). Copia
   l'indirizzo di connessione *interno* (`postgres://...`): l'app lo converte da sola.
4. **Sito**: crea un *Web Service* collegando il repository GitHub, ambiente **Docker**, branch
   `claude/fiscal-verification-automation-yev7yy` (o quello che userai), regione **Frankfurt**.
   Percorso di controllo di stato: `/salute`.
5. **Variabili d'ambiente** del sito:
   | Nome | Valore |
   |---|---|
   | `DATABASE_URL` | indirizzo del database (punto 3) |
   | `DATA_KEY` | quella del punto 2 |
   | `SESSION_SECRET` | quella del punto 2 |
   | `HTTPS_ONLY` | `1` |
   | `BOOTSTRAP_PASSWORD_HASH` | stampata da `prepara-accesso` |
   | `BOOTSTRAP_TOTP_SECRET` | stampato da `prepara-accesso` |
   | `ANTHROPIC_API_KEY` | (facoltativa) chiave per l'AI; senza, l'AI resta spenta |
6. **Primo accesso**: apri l'indirizzo del sito, entra con password + codice dell'app di autenticazione.
   Poi **rimuovi** `BOOTSTRAP_PASSWORD_HASH` e `BOOTSTRAP_TOTP_SECRET` dalle variabili e riavvia.
7. **Verifiche**: `https://<tuo-sito>/salute` risponde `{"stato":"ok"}`; l'indirizzo e' HTTPS; solo tu accedi.

## Cose da tenere presenti
- Il sito e' raggiungibile da chiunque conosca l'indirizzo, ma senza password **e** codice non si entra; dopo 5
  tentativi sbagliati l'accesso si blocca per 15 minuti.
- Backup del database: attiva quelli del provider e verifica come si ripristinano.
- Aggiornamenti: ogni nuovo commit sul branch collegato ripubblica il sito (se attivi la pubblicazione automatica).
- `ANTHROPIC_API_KEY`: ogni generazione e ogni ricerca normativa ha un costo a consumo.
