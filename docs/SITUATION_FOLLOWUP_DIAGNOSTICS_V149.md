# ORA v149 — Perché non sono partiti i controlli sui panni?

## Segnalazione reale (9 ottobre 2026)

Conversazione ORA:
- «A che punto siamo con i panni stesi?» → risposta generica «Non risulta confermato un controllo automatico per la situazione...»
- «Come mai?» → stessa frase ripetuta, senza causa né prossimo passo verificabile.

Non è prova che i panni siano asciutti, bagnati, all'aperto o ritirati. È **solo** l'assenza di un controllo programmato verificabile.

## Due cause architetturali documentate nel codice

1. `FollowupTurnGate.failure_text()` aveva una risposta fissa per ogni mancata gestione. Per una domanda sul *perché* non veniva indicato il motivo registrato, perché `get_situation_followup` non produceva una `factual_readback` accettabile da `status_only`: una domanda legittima sulla programmazione poteva ricadere nella stessa frase generica anche al turno successivo.
2. `EligibilityService._has_unattended_situation()` vedeva un goal aperto e riteneva per questo il follow-up già seguito. Se il goal esisteva con `next_run_at`, ma la sveglia durevole era assente/fallita, mancava un percorso di recupero su base periodica. Il goal da solo NON è una sveglia.

## Interventi

- `read_followup` espone una diagnosi in italiano derivata dallo stato **reale**, senza dedurre condizioni meteorologiche o esiti fisici. Distingue:
  * situazione senza un primo checkpoint;
  * lavoro presente senza sveglia eseguibile;
  * runtime disattivato;
  * programmazione rifiutata (orario/fuso invalido, revisione cambiata, goal chiuso, ecc.);
  * controllo in corso/schedulato/chiuso.
- Il tool di lettura restituisce una `factual_readback` validata con `situation:<id>`; l'AI può rispondere a «Come mai?» come `status_only` **senza** riprogrammare qualcosa soltanto perché l'utente ha chiesto spiegazioni.
- I tentativi falliti tramite il tool `schedule_situation_check` registrano un codice errore nel journal per l'owner corretto. Non vengono conservati o mostrati contenuti privati, proposte meteo o parametri grezzi.
- Se il modello non completa comunque il ragionamento, il fallback usa il riscontro del database e la situazione identificata, non la frase fissa.
- Il dettaglio della situazione mostra la diagnosi esatta.
- Recupero indipendente: il fallback ambient individua anche un goal aperto con checkpoint non eseguibile. Il worker può ripristinare **soltanto una sveglia con un orario già persistito**, senza inventare un tempo di asciugatura, chiamare il meteo a vuoto o notificare falsi risultati. Quando non esiste alcun orario valido, è necessaria una valutazione cognitiva: non si inventa una data.

## Limiti e accettazione

La presenza della variabile `AMBIENT_RUNTIME` su Railway **non ne dimostra il valore né dimostra che un controllo per l'account sia realmente schedulato**. Gli strumenti connessi non consentono di leggere la sessione autenticata della persona o i suoi singoli record nel database. Servono verifiche end-to-end nell'account reale e, per dichiarare un avviso meteorologico, dati meteo correnti e un checkpoint/una notifica effettivamente eseguiti.

Non cancellare una Situation o una memoria permanente per nascondere il problema. Non dichiarare conclusa l'asciugatura per decorso del tempo.
