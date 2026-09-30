# Dangerok

Assistente **privato, single-user** per controlli e verifiche fiscali, costruito sulla Circolare 1/2018 del
Comando Generale della Guardia di Finanza (volumi in questo repository). Bozze di PVOC, PVV, PVC e CNR con
controlli sull'ordine delle fasi e sui contenuti obbligatori. **Le bozze non sono atti**: firma e responsabilita'
restano di chi verbalizza.

## Principi
1. **La circolare e' la fonte di verita'** (`app/workflow.py` cita ogni punto). Gli esempi servono per il lessico.
2. **Privacy by design**: nessun dato identificativo va all'AI. Il filtro (`app/privacy/pseudonymizer.py`) sostituisce
   nomi, enti, CF, P.IVA, IBAN, e-mail, telefoni, targhe, indirizzi, documenti, luoghi/date di nascita con segnaposto;
   se resta un residuo l'invio e' **bloccato**. Prima di ogni generazione l'anteprima mostra cosa parte.
3. **Accesso solo per il proprietario**: password (Argon2) + codice TOTP, blocco dopo 5 errori, nessuna registrazione.
4. **Dati cifrati a riposo** (Fernet) e titolo pratica = codice interno, mai il nominativo.
5. Nessun atto reale nel repository (`.gitignore`); usare `python -m app.cli anonimizza` prima di caricare esempi.

## Avvio in locale
```bash
pip install -e ".[dev]"
python -m app.cli genera-chiavi          # copia le due righe in .env (vedi .env.example)
set -a; . ./.env; set +a
HTTPS_ONLY=0 python -m app.cli crea-utente   # password + QR per l'app di autenticazione
HTTPS_ONLY=0 uvicorn app.main:create_app --factory --port 8000
pytest
```
`ANTHROPIC_API_KEY` vuota = assistente AI disattivato (il resto funziona).

## Anonimizzare un file prima di caricarlo
```bash
python -m app.cli anonimizza atto.docx --persona "Nome Cognome" --ente "Ditta S.r.l." --militare "Mar. Nome Cognome"
```
Produce `atto.anon.docx` e una mappa `*.mappa.json` (**resta in locale, non caricarla**). Si ferma se il file
contiene immagini/oggetti incorporati. I `.doc` vanno prima convertiti in `.docx`. Controllare sempre a mano.

## Pubblicazione online
Guida completa: `docs/PUBBLICAZIONE.md` (Dockerfile e supporto Postgres pronti).

### Note generali
Serve un hosting con HTTPS obbligatorio, Postgres (`DATABASE_URL`) e i segreti nelle variabili d'ambiente del
servizio, mai nel repository. Prima di usare dati reali: verificare le regole del proprio Comando sull'uso di
servizi cloud e di AI esterne. Fino ad allora usare solo dati fittizi.

## Stato
Scheletro funzionante: accesso, pratiche, fasi in ordine (controllo e verifica), scheda Allegato 23, inviti per
tipologia, filtro privacy con test, generazione bozze con anteprima e registro di cio' che esce.
Da fare: generazione documenti Word dai modelli, libreria del lessico (da esempi anonimizzati), regole di
coerenza tra atti, calcoli (scaglioni, aliquote), soglie D.Lgs. 74/2000 versionate, percorso CNR, PVV giornalieri.
