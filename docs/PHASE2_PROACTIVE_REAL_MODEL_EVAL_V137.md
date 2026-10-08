# ORA v137 — Valutare l'autonomia sulle decisioni, non sui soli job

### Scopo
Un assistente utile deve distinguere una situazione che merita un obiettivo da informazione già gestita o semplice pubblicità. Un test che controlla soltanto che il server sia acceso non può certificarlo.

Il nuovo evaluator esercita il codice reale di OpportunityRepository, agent.admission, AgentService, governance delle code, salvataggio di AutonomousGoal e wake persistente. Solo i dati dell'utente sono fittizi e il database è in memoria. Il test non usa Gmail, calendario o altri provider personali, non invia messaggi, non crea contratti e non compie azioni verso terzi.

### Scenari

- Conflitto fra nuova comunicazione e orario di appuntamento: creare un obiettivo verificabile, salvare il goal e programmare un wake, senza fare modifiche esterne.
- Newsletter pubblicitaria irrilevante: `no_goal`, nessun lavoro generato.
- Conferma già coerente con calendario: `no_goal`, nessuna duplicazione.
- Provider del modello non disponibile: stato `unavailable` distinto dal silenzio volontario, record retryable e nessun obiettivo inventato.

### Due tipi di prova

La modalità `scripted` contiene soltanto una scelta AI prefissata: prova il collegamento fra decisione, persist e wake e deve essere riproducibile in CI. La modalità `live` usa il gestore LLM reale esclusivamente su dati sintetici isolati e registra separatamente i risultati. Può fallire: un errore osservato in live resta un errore, non viene convertito in successo perché la modalità scripted passa.

Il comando `python -m scripts.phase2_proactive_live_eval --mode live --scenario all` è esclusivamente un collaudo esplicito, non un'automazione che si ripete ogni ora. L'output stampa conteggi e codici di esito, mai chiavi, contenuti di messaggi personali o argomenti del modello.

### Limiti

Questa verifica prova soltanto l'ammissione proattiva. Non dimostra una ricerca multi-provider, un acquisto, un trasferimento bancario, un contatto telefonico, l'esecuzione di un piano o una notifica ricevuta da un dispositivo reale. Il criterio 'create_goal' verifica la creazione dell'obiettivo e del wake, non l'avvenuto successo dell'obiettivo. I controlli sul completamento del lavoro rimangono separati.

Si confrontino sempre almeno una situazione positiva e due negative: la metrica corretta è il lavoro utile senza falsi allarmi, non il numero di nuovi job.