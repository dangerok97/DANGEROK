# Calendario ORA — verifica del 28 settembre 2026

## Versioni pubblicate

- Backend Railway: `fb668c883dd17d3465dfd194b0ec9063001d4144`, deployment `7fa269a8-9c33-4e90-be4c-610e7e6ec739`, SUCCESS.
- Frontend Railway: `49f69652ed45bf25a777b4df90953b2680ffeee5`, deployment `b396b9af-54e2-4a66-996f-5bd9d4ae8068`, SUCCESS. Le revisioni successive modificano soltanto backend, test e documentazione.
- Nessuna modifica a credenziali, domini, volumi o configurazione dei servizi.

## Risultato per l'utente

Home → giorno → Aggiungi impegno salva titolo, ora, durata, luogo e note nel calendario ORA. La scheda consente modifica diretta e cancellazione. La conversazione legge e modifica lo stesso evento. L'origine locale è esplicita, senza richiedere Google o dichiarare sincronizzazioni inesistenti.

## Prove sul servizio reale

Due account sintetici separati dagli account personali; autenticazione email/password attraverso l'API esistente. Nessun calendario esterno collegato agli account di prova.

| Controllo | Riscontro |
| --- | --- |
| Creazione e invii concorrenti della stessa richiesta | Un solo identificativo, una sola riga nella lettura del giorno |
| Rilettura della scheda | Luogo, note, durata e origine locale conservati |
| Isolamento | Il secondo account riceve 404 su lettura, modifica e cancellazione del primo |
| Modifica e retry | Stesso evento; retry riuscito senza nuova revisione; modifica incompatibile da revisione vecchia respinta con 409 |
| Agenda e mese | Ora 11:30–13:00 e indicatore del 30 settembre presenti |
| Riavvii backend | L'evento rimane disponibile dopo i rilasci successivi |
| Lettura con AI reale | Risposta corretta: mercoledì 30 settembre, Studio di prova, portare il promemoria azzurro |
| Spostamento con AI reale | Richiesta naturale eseguita senza seconda conferma: 15:00–16:30, stesso ID, luogo e note invariati |
| Cancellazione con AI reale | Domanda legata all'evento; dopo «Sì», stato riletto `cancelled=true` |
| Controllo dopo cancellazione | Evento assente da giorno, mese e agenda; retry della cancellazione verificato `already_gone` |
| Frontend servito | HTTP 200; bundle online contiene modulo condiviso e controllo revisione |

La conferma finale della cancellazione ha richiesto **80 ms di elaborazione backend**, una chiamata al tool e zero nuove chiamate al modello. Non è una misura della latenza totale di rete o vocale. Il precedente spostamento in linguaggio naturale ha richiesto 22.789 ms di elaborazione: la latenza generale dell'AI resta un lavoro distinto.

## Problemi scoperti e corretti durante la prova reale

1. Il contesto delle prossime 48 ore scartava le note: ora conserva description, timezone e data/giorno calcolati.
2. Il modello proponeva una durata diversa: gli spostamenti locali mantengono per default la durata osservata.
3. Il catalogo compatto scartava proprietà annidate, inclusa requested_by_user: ora conserva struttura, obbligatorietà, enum e default.
4. Dopo una conferma il modello poteva rispondere senza eseguire: la ripresa usa la richiesta preparata e rivalida snapshot, proprietà e autorità. La risposta di successo segue la rilettura.

## Verifiche automatiche

- **125 test Python PASS**, sei avvisi di deprecazione esistenti. Suite calendario, autorità, catalogo e lifecycle con Mongo simulato in memoria; non sono 125 prove contro Mongo o Google reali.
- Il lifecycle comprende HTTP/dominio e il loop completo proposta → sì → tool → verifica. Un test impedisce che la conferma richieda una nuova scelta del modello; un altro impedisce di cancellare un evento modificato dopo la proposta.
- TypeScript PASS, contratto Home PASS.
- ESLint dei file modificati: zero errori, 45 avvisi preesistenti nel client API.
- Export Expo web PASS.
- Dipendenza aggiuntiva esclusivamente di test: `mongomock-motor==0.0.36` in `requirements-test.txt`. Nessuna nuova dipendenza runtime.
- Indice Mongo aggiunto senza migrazioni distruttive: `owner_event_starts`.

Per ripetere i nuovi test: installare `backend/requirements-test.txt`, quindi eseguire `PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_home_calendar_lifecycle.py -v`. `QA_MONGO_URL` permette di usare un database reale temporaneo; quel database di prova viene eliminato al termine.

## Limiti della verifica

- Non effettuata verifica grafica autenticata su iPhone/touch: il browser disponibile era alla schermata di login. I controlli live descritti sopra sono HTTP e conversazionali.
- Nessuna nuova prova live di scrittura Google, invio notifiche, telefonate o voce in questa sessione.
- Gli impegni locali si creano dalla Home; `create_calendar_event` dalla chat continua a usare il percorso Google.
- Gli account sintetici e le loro conversazioni di test rimangono separati; l'impegno creato è stato archiviato. Nessun impegno personale è stato modificato.
