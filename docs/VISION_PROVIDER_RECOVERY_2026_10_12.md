# Vision — riconoscimento e indisponibilità del servizio AI

## Segnalazione e riscontro

Il cestino dell'utente continua a mostrare `Non distinguo bene un oggetto` dopo #214. La foto è visivamente interpretabile; non è stata pubblicata nel repository né nei test.

Log del backend, finestra 12 ottobre 2026 08:00:40–08:02:10 UTC: ripetuti 404 sul modello `gemini-2.5-flash`; risposte 402 su un percorso di credenziali; 200 e un 503 sull'altro percorso di `gemini-flash-lite-latest`. Questi log non associano con certezza una risposta alla schermata. Il codice di #214, però, converte riproducibilmente i timeout di riconoscimento in `None`, quindi nel falso messaggio di oggetto non distinguibile.

## Modifiche revisionate

- Trasporto separato con schema JSON di riconoscimento e controllo di integrità della risposta. I timeout e gli errori non diventano risultati visivi negativi.
- Preferenza temporanea del collegamento funzionante; cooldown delle combinazioni modello/credenziale in errore. Credenziali solo sotto hash nello stato di salute, nessuna chiave o foto nei log. Nessun aumento del piano, ricarica o sostituzione delle chiavi.
- Identificazione generale non limitata all'inventario dei 75 seed. L'alias canonico si risolve successivamente nel catalogo. Riquadri normalizzati 0–1 accettati senza ridurli di 1000 volte.
- Due tentativi visivi temporizzati, coerenti col termine del client. Dopo due risposte realmente incerte, domanda facoltativa `Che oggetto stai inquadrando?`, verificata su una nuova acquisizione. Nessuna generazione dal solo nome.
- Pausa delle scansioni automatiche durante la compilazione del suggerimento. La camera rimane aperta; uscita, X, flash e zoom restano indipendenti.
- Gli errori del generatore conservano il codice del servizio dopo aver chiuso il job come fallito. Non pubblicano un modello fittizio.
- Nessun nuovo seed dedicato al cestino usato per aggirare la prova fuori catalogo. Modelli comuni, privati precedenti e versioni ritirate sono preservati.

## Verifica da completare

Il primo giro automatico sul contenuto integrato ha superato il job backend/catalogo, TypeScript, geometrie ed export. I test successivi al raffinamento sono stati fermati da GitHub perché originati dal bot: non sono conteggiati come test superati. Questo commit registra la revisione del contenuto e avvia i normali gate con il collegamento autorizzato dell'utente, senza cambiare policy, permessi o controlli.

L'ulteriore collaudo reale usa solo una fotografia pubblica di un cestino e account QA isolati. Il primo tentativo è fallito nel download pubblico, prima di creare account. Sono stati recuperati gli URL effettivi delle miniature dalla pagina sorgente per ripetere la prova. Nessuna prova del sensore iPhone o del cestino specifico dell'utente è dichiarata riuscita.

La funzione resta una scomposizione illustrativa generica: non determina l'interno esatto dell'esemplare, non produce riparazioni o istruzioni per oggetti rischiosi e non trasforma il suggerimento della persona in evidenza verificata. Lo stato di pubblicazione e gli esiti finali sono registrati nella PR #216, solo dopo i relativi riscontri.
