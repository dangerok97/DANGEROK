# Fase 1 v126 — Letture reali, autenticazione e ripresa

Data: 8 ottobre 2026. Punto di partenza: v125 / PR #161, commit `9d46ac3`.
La Fase 1 della roadmap rimane **aperta**. Questo documento separa i risultati
osservati dai criteri ancora da verificare e conserva anche i tentativi parziali.

## Perché questo intervento

Il checkpoint v125 aveva provato il modello reale con dati e tool esterni
simulati. Collegando il percorso applicativo a errori reali dei provider e a
sessioni rilette sono stati riprodotti tre difetti:

1. Un timeout di routing perdeva il segnale di errore temporaneo, rendendo
   terminale un piano che avrebbe potuto riprendere una lettura.
2. Il retry dello stesso `client_message_id`, dopo la persistenza e la rilettura
   della sessione, richiamava il modello e poteva riscrivere un memo.
3. La skill `get_route` usava anche una posizione vecchia o priva del consenso
   corrente, diversamente dal percorso di apertura della navigazione.

Il primo collaudo con LLM e provider reali ha inoltre mostrato un limite della
risposta: i numeri erano corretti, ma il consiglio di partire subito «per evitare
il traffico» non aveva una prova comparativa sugli orari di partenza.

## Comportamento implementato

Gli adapter di routing e meteo classificano come recuperabili timeout, errori
di rete, HTTP 429 e 5xx. Errori di configurazione, autorizzazione, input, percorso
assente o risposta illeggibile restano terminali. La classificazione alimenta
il meccanismo v122 esistente: non introduce retry illimitati nel provider.

`get_route` e `open_navigation` condividono il requisito di posizione corrente:
consenso `while_using`, permesso foreground concesso, origine dispositivo,
nessun errore di acquisizione e dato non più vecchio di 120 secondi. Una
posizione da aggiornare può richiedere il bridge del client; non viene inviata
al provider come se fosse corrente.

Il meteo conserva `observed_at` del provider, `retrieved_at` di ORA, `timezone`,
`utc_offset_seconds` e la data completa in ogni `hours[].datetime`. Il vecchio
campo `time` resta compatibile. Una rilevazione senza data non riceve una data
inventata; il passaggio oltre mezzanotte conserva il giorno successivo.

L'orchestratore salva il risultato del messaggio e la ricevuta nella stessa
scrittura della sessione. Il retry dello stesso ID e dello stesso contenuto
restituisce il risultato già persistito. Un altro contenuto con lo stesso ID
viene respinto; un nuovo ID resta una nuova richiesta. I metadati privati delle
ricevute non sono inclusi nella cronologia pubblica. Il controllo dell'owner e
della chiusura della sessione precede il replay. La continuazione del dispositivo
aggiorna la ricevuta associata al messaggio sospeso.

## Collaudo con modello e provider reali

Runner: `backend/scripts/phase1_read_provider_eval.py`. Usa manager LLM, loop,
catalogo, governance e handler applicativi reali. Account, consenso, posizione,
luoghi salvati e Mongo sono sintetici/in memoria. I due luoghi sono pubblici:
Roma Termini (41.9010, 12.5018) e Colosseo (41.8902, 12.4922).

Il processo temporaneo consente soltanto letture HTTP dei provider previsti,
con coordinate fisse e senza redirect. Non accede al Mongo degli utenti,
calendari personali o documenti; non può avviare navigazione, inviare messaggi,
creare appuntamenti, notifiche o pagamenti. Le credenziali sono riferimenti
dell'ambiente e non sono scritte nelle evidenze. Non è un worker ricorrente.

La verifica tecnica richiede entrambi i tool, esito utilizzabile, provenienza,
date/fuso meteo presenti nell'Observation passata al modello e rilettura esatta
del risultato dalla sessione. Una risposta presente non basta per promuovere
automaticamente il suo contenuto: viene revisionata separatamente.

### Tentativo 1 — Letture valide, consiglio di partenza non accettato

Commit: `546bf5748790c402dcf0f6555b1e1465ff0df3ec`.
Deployment tecnico: `7ec5c235-8bbe-4fc6-995f-0f789fef89a8`.
Scenario: 8 ottobre, 14:11 Europe/Rome, partenza adesso.

| Controllo | Evidenza osservata |
|---|---|
| Modello reale | 4 chiamate: Mistral `ministral-8b-2512` e OpenAI `gpt-4o-mini` |
| Percorso reale | Mapbox HTTP 200: 793 secondi, 2.990 metri, traffico corrente |
| Meteo reale | Open-Meteo HTTP 200: rilevazione 14:00 Europe/Rome, 25 °C; previsioni fino alle 01:00 del 9 ottobre |
| Persistenza delle letture | Due Observation rilette dal Mongo in memoria, uguali a quelle del modello |
| Confine delle operazioni | Due letture, nessuna operazione vietata tentata |
| Chiusura del loop | `answer`, 103.681 ms; nessun esaurimento del budget |
| Verdetto tecnico | Superato |
| Revisione della risposta | Parziale: valori coerenti; consiglio sul traffico non supportato |

La risposta arrotonda correttamente 793 secondi a circa 13 minuti e descrive
correttamente il rischio di pioggia fino al 90% alle 19:00. La frase «partire ora
per evitare il traffico» non è deducibile da una sola stima corrente: non è stato
letto il traffico futuro né confrontato un altro orario. Il tentativo resta
conservato come **parziale**, senza convertirlo retroattivamente in PASS.

La correzione aggiunge al prompt e alla descrizione della capability la regola
di confronto: neppure una durata statica/tipica o due percorsi allo stesso
orario dimostrano il vantaggio di partire subito. Un test intercetta l'input
successivo alla route e verifica che Observation e limite raggiungano insieme
il modello. Le due suite pertinenti passano 24 test; l'obbedienza del modello
reale alla regola richiede il nuovo tentativo live.

Evidenza completa, inclusi messaggio, decisioni, Observation, metadati HTTP e
testo finale: [JSON del collaudo](evidence/phase1_real_provider_read_2026-10-08.json).

## Autenticazione e persistenza

`test_phase1_authenticated_resume_v126.py` attraversa il router FastAPI reale,
creazione/verifica/revoca JWT, orchestratore e repository con account sintetici.
Verifica 401 senza credenziale, con credenziale malformata o revocata; 404 per
un altro owner; 400 per ID riusato con testo diverso; risposta identica al retry
con credenziale valida, senza nuove chiamate AI. Anche un nuovo token valido
recupera lo stesso risultato. Non è una prova del login OAuth personale.

`test_phase1_resume_idempotency_v126.py` verifica la rilettura della sessione,
un memo annuale non duplicato, separazione degli owner, conflitti, sessione
cancellata, limiti di ricevute e associazione corretta della continuazione GPS.
Un piano incompleto riletto riprende il percorso fallito senza ripetere la
lettura del calendario già riuscita.

`test_phase1_real_restart_v126.py` aggiunge il confine di un vero processo:
con `PHASE1_REAL_MONGO=1` crea un database UUID su Mongo loopback, avvia e termina
un interprete che salva risultato e memo, poi avvia un secondo interprete che
deve restituire tutto senza chiamare il modello. Il secondo processo controlla
sessione e memo invariati e isolamento dell'owner. Un marker permette di
eliminare soltanto il database creato dal test. Modello e persona restano
sintetici; il database e i processi sono reali. Il gate deve passare in CI:
senza flag è esplicitamente saltato, con flag e Mongo assente deve fallire.

## Verifiche e riproduzione

La prima CI completa sul commit `546bf574` è verde:
[run 37774894917](https://github.com/dangerok97/DANGEROK/actions/runs/37774894917).
Include 223 test nel gruppo Fase 1, le regressioni applicative, compilazione
backend, TypeScript, generazione del progetto iOS, bundle iOS di produzione e
scansione dei segreti sull'intera storia Git. Il gate del processo separato e
la correzione del consiglio richiedono una CI successiva sul relativo commit.

Esecuzione ripetibile senza credenziali esterne, dalla cartella `backend`:

```bash
python -m scripts.phase1_read_provider_eval --mode scripted
PHASE1_REAL_MONGO=1 python -m pytest -q tests/test_phase1_real_restart_v126.py -x
```

La seconda riga richiede un MongoDB di test loopback senza credenziali. La
modalità live del runner è opt-in, usa l'ambiente dei provider autorizzato e
deve mantenere lo stesso isolamento; non è inclusa nella CI ordinaria.

## Limiti e criteri successivi

- Il replay garantisce il confine **dopo** il salvataggio del risultato.
  Non è una transazione tra Mongo e un effetto esterno; non risolve da solo
  richieste concorrenti né un crash dopo l'effetto ma prima del salvataggio.
- Le ricevute hanno limiti espliciti: 20 per sessione, 96 KiB ciascuna. Una
  ricevuta non disponibile produce `message_result_unavailable`, non un retry
  che riesegue automaticamente l'effetto. Nessuna migrazione retroattiva.
- Il meteo copre il presente e le prossime 12 ore. Il routing espone traffico
  corrente, senza un parametro di partenza futura. Un ETA per domani o un
  confronto tra orari non sono dimostrati da questo scenario.
- Un solo tragitto live non dimostra robustezza multiutente o su più giorni.
  La latenza osservata va tenuta distinta dalla correttezza del risultato.
- Tre vecchi test di `test_navigation_handoff.py` che esigono il bypass del
  modello falliscono già sul checkpoint `9d46ac3`, prima di questa modifica.
  Il confronto è stato eseguito in un worktree separato. Le fixture di posizione
  sono state aggiornate al consenso corrente; non è stato ripristinato un
  instradamento deterministico incompatibile con il loop AI attuale.
- Restano da valutare più risposte live, inclusi recuperi dopo errore del
  provider, credenziali del tecnico su un vero flusso di login e prove native
  di posizione/notifica. Il successo del deploy non chiude questi criteri.

Nessuna nuova dipendenza di produzione, migrazione distruttiva o modifica
visuale. Nessuna automazione oraria di sviluppo.
