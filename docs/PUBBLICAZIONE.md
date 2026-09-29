# Pubblicare Dangerok online (guida passo passo)

> **Solo dati inventati finche' il tuo Comando non ha autorizzato l'uso.** Questa guida serve a mettere online
> l'app per visionarla e provarla. Non caricare atti o dati di contribuenti reali su un servizio esterno senza
> aver verificato le regole del Comando (cloud, AI esterne, localizzazione dei dati).

## PERCORSO RAPIDO (consigliato per provare): un solo Blueprint su Render, senza installare nulla sul computer
Il file `render.yaml` nella radice del repository descrive tutto: sito (Docker, piano gratuito, Frankfurt) e database.
Le chiavi (`DATA_KEY`, `SESSION_SECRET`, `SETUP_TOKEN`) le genera Render da solo. Non serve Python.
1. Registrati su render.com e collega GitHub, dando accesso **solo** al repository `dangerok97/DANGEROK`.
2. **New +** > **Blueprint** > scegli il repository e il branch `claude/fiscal-verification-automation-yev7yy` >
   conferma. Se Render segnala un errore nel file, incollamelo: lo correggo.
3. Attendi che il sito sia "Live" (alcuni minuti al primo avvio).
4. Nel pannello del sito apri **Environment** e copia il valore di `SETUP_TOKEN`.
5. Apri l'indirizzo del sito: ti porta a **Configura il tuo accesso**. Incolla il codice, scegli la password
   (almeno 12 caratteri), inquadra il QR con l'app di autenticazione e scrivi il codice a 6 cifre. Fatto: la pagina
   di configurazione sparisce e da quel momento entri con password + codice.
6. Facoltativo: `ANTHROPIC_API_KEY` nelle variabili, per attivare l'AI (a consumo).

**Attenzione:** con questo Blueprint il database e' quello gratuito di Render, che **scade dopo 30 giorni** (poi 14
giorni prima della cancellazione). Va bene per PROVARE con dati inventati. Per un uso duraturo passa a un database
esterno (Neon, sotto) cambiando `DATABASE_URL` e togliendo il database dal Blueprint.
Non ho potuto provare il Blueprint su Render (il sito e' bloccato dal mio ambiente): e' scritto secondo il formato
documentato e il file e' verificato come YAML valido, ma il primo avvio e' il vero collaudo.

## Percorso manuale: Render (sito) + Neon (database)
Verificato a settembre 2026 su fonti pubbliche secondarie (non ho potuto aprire le pagine ufficiali di prezzi):
le condizioni cambiano, **ricontrollale prima di iscriverti**.
- **Render, Web Service gratuito** (Docker): 512 MB di memoria, 750 ore gratuite al mese. Dopo 15 minuti senza visite
  il sito si "addormenta" e la prima apertura successiva e' lenta. Il disco non e' persistente: per questo i dati
  vanno in un database esterno.
- **Non usare il Postgres gratuito di Render**: scade 30 giorni dopo la creazione (poi 14 giorni prima della cancellazione).
- **Neon, Postgres gratuito**: 0,5 GB, 100 ore di calcolo al mese, regione **Frankfurt** disponibile, si sospende da
  solo quando non serve. I progetti gratuiti inattivi per 90 giorni possono essere cancellati (regola indicata con
  decorrenza 5 ottobre 2026).
- Alternativa per il database: **Supabase** (500 MB, si mette in pausa dopo 1 settimana di inattivita', senza backup).
- **Railway** (molto comodo: sito e Postgres si creano insieme): NON e' gratuito in pratica. La prova da 5 dollari e'
  una tantum e dura al massimo 30 giorni; poi c'e' un piano gratuito con 1 dollaro di credito al mese, troppo poco per
  un sito acceso piu' un database; il piano Hobby costa 5 dollari al mese (con 5 dollari di utilizzo inclusi) e richiede
  una carta di pagamento. Utile per una prova di un fine settimana, oppure a pagamento se vuoi la strada piu' semplice.
- **Da evitare se cerchi il gratis**: Fly.io e Koyeb non hanno piu' un piano gratuito vero per i nuovi iscritti
  (solo prove). Google Cloud Run ha una quota gratuita ma richiede una carta.
- Il gratuito non ha backup ne' garanzie di servizio: va bene per **guardare e provare l'app con dati inventati**,
  non per lavorare.

Con il gratuito il passo 3 diventa: crea un progetto **Neon** nella regione *AWS Europe (Frankfurt)*, copia l'indirizzo
di connessione (`postgresql://...?sslmode=require`) e incollalo in `DATABASE_URL`. Se il piano gratuito di Render non
offre Francoforte, scegli la regione europea piu' vicina disponibile.

## Scelta a pagamento per lavorare davvero: Render (Frankfurt) + Postgres gestito
Render pubblica direttamente da un repository GitHub con il `Dockerfile` (gia' pronto), offre HTTPS automatico, un
Postgres gestito e la regione di Francoforte (UE). **Controlla tu i costi prima di attivare qualsiasi servizio.**
Per un controllo maggiore dei dati, un provider europeo con server dedicato/VPS (es. Hetzner, OVHcloud, Scaleway)
richiede piu' gestione.

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

## Attivare l'AI (primi esperimenti)
1. Vai su console.anthropic.com, accedi/registrati (l'account e' separato da quello di Claude.ai).
2. **Settings > Plans & Billing > Add to credit balance**: aggiungi un piccolo credito (es. pochi euro) con la tua carta. Senza credito la chiave non funziona.
3. **Limiti di spesa**: nelle impostazioni della workspace (Limits) imposta un tetto **mensile** basso, cosi' un errore non costa di piu'.
4. **API Keys > Create Key**: dai un nome (es. `dangerok-prova`) e **copia subito la chiave**: non e' piu' recuperabile.
5. Su Render: servizio *dangerok* > **Environment** > `ANTHROPIC_API_KEY` > incolla la chiave > salva. Il sito si riavvia.
6. Nell'app apri **Impostazioni** e premi **Prova il collegamento**.
La chiave e' segreta: non incollarla in chat, in file del repository o in schermate che condividi.
Modello predefinito: `claude-opus-5-5`. Per gli esperimenti puoi impostare la variabile `ANTHROPIC_MODEL` (es. `claude-sonnet-5-5`,
meno costoso), a costo di risposte meno accurate.
