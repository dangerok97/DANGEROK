# Completamento delle autonomie concordate

Richiesta Francesco, 3 ottobre 2026: completare ogni mancanza, una per volta,
verificare, fare commit e push, pubblicare, riportare l'esito con screenshot
quando pertinenti e continuare senza richiedere ogni volta il via libera.

Non segnare completato ciò che è soltanto implementato. Distinguere sempre
test con confini controllati, prova cloud, UI autenticata e dispositivo reale.
Le telefonate a terzi, gli invii, i contratti e i pagamenti richiedono la loro
autorizzazione concreta; sviluppare i flussi non equivale a effettuarli.

| Passo | Risultato da dimostrare | Stato |
|---|---|---|
| P1 — Partenze | Appuntamento → percorso corrente → valutazione utile → riesame, invalidazione e navigazione | 70 test locali PASS; percorsi cloud reali, decisione avviso ancora in verifica |
| P0 — Iniziativa | Calendario, documenti, comunicazioni e cambi vita avviano lavoro utile senza duplicati o falsa completezza | Da consolidare con scenari completi |
| P2 — Occupatene tu | Lavoro autorizzato prosegue dopo attese e riavvii, verifica il risultato, comunica esito o blocco concreto | Da completare |
| P3 — Risparmio | Costi annui completi, condizioni ed eleggibilità distinguibili dalle sole componenti di vendita; risultato misurabile | Da completare |
| P4 — Conoscenza | Routine e preferenze aiutano decisioni; luoghi nominati/confermati, nessuna attribuzione inventata | Da completare |
| P5 — Interfaccia | Azioni pertinenti e funzionanti lungo l'intero percorso del lavoro | Da completare |
| Ricerca prodotti | Dati verificabili su prezzo/disponibilità e limiti operativi espliciti, oltre al collegamento Amazon | Da completare |
| VITA | Ogni area distingue dati, preparazione e azione realmente supportata; niente finte esecuzioni | Da completare |
| Telefonia | Esito needs_user → decisione → richiamo autorizzato; cambio calendario concorrente; saluto finale | Gate reali rinviati dall'utente, da riaprire al momento opportuno |
| P6 — iPhone | Push, permessi, geofence, background, riavvio e revoca verificati su dispositivo | Penultima fase, dipende dal dispositivo |
| P7 — Alpha | 3–5 persone, almeno 7 giorni, esiti osservati e difetti risolti | Ultima fase, durata e partecipanti necessari |

## P1 — Cosa cambia

Il calendario unificato, inclusi eventi Home e calendario collegato, fornisce
la destinazione. Per massimo due eventi entro 24 ore si leggono i percorsi
realmente supportati dal provider; mezzo non presunto, margine esplicito di
10 minuti e traffico futuro dichiarato incerto. Alternative e meteo arrivano
dagli adattatori già presenti. Il runtime ambient conserva il prossimo
riesame, anche quando la persona chiude l'app.

Il modello continua a decidere rilevanza, superficie e interruzione. Il codice
impedisce orari inventati, rifiuta posizioni scadute o imprecise e invalida la
stima se l'appuntamento cambia. Lo stesso controllo è ripetuto prima del
provider push. Un rifiuto esplicito non è riaperto da un semplice ricalcolo.

La posizione deve essere autorizzata e osservata dal dispositivo da non più
di 120 secondi. Senza nuovi fix non si dichiara una partenza affidabile: la
presenza nativa continuativa resta da provare in P6. Non è un'allerta a tempo
fisso indipendente dalla realtà.

## Verifiche

- 68 test mirati locali PASS; provider e modelli controllati dove indicato.
- TypeScript, compilazione Python e `git diff --check` PASS.
- Build web Expo PASS (esportazione completa); frontend invariato.
- CI, commit, deployment e prove API cloud: da aggiornare dopo l'esecuzione,
  senza considerarli già riusciti.
- Browser attuale non autenticato. Nessuno screenshot autenticato o test su
  iPhone dichiarato; nessuna chiamata o push a persone reali effettuato.

Prossimo passo automatico dopo la consegna P1: P0/P2, iniziativa e chiusura
verificata del lavoro autorizzato.

## P1 — Primo checkpoint cloud e correzione del fix GPS

Commit `03b734cd505e168b63c00e70d9ed8e4770778e5a`: CI `37146068797`,
tutti i cinque job SUCCESS. Backend Railway
`fadf2960-75a3-4ee0-b015-63a89b36de55` SUCCESS; configurazione invariata.
Il primo scenario sintetico ha verificato salute, assenza di endpoint push
e salvataggio dell'appuntamento, ma non ha prodotto la scheda partenza
né in background né dopo scansione esplicita. P1 resta aperto.

Corretto un difetto riprodotto: un nuovo fix allo stesso punto invalidava
una stima ancora fresca. L'identità della posizione dipende dal punto;
la scadenza originale non viene estesa. Un nuovo fix dopo la scadenza
richiede il ricalcolo. Nuovo GET autenticato `/places/departures` espone
i fatti di percorso e gli stati di indisponibilità del solo proprietario,
riusando il servizio esistente e senza forzare avvisi. 68 test mirati PASS.
La nuova prova cloud deve distinguere dati di percorso, decisione del
modello e lavoro in background. Nessun esito positivo anticipato.

## P1 — Secondo checkpoint: errore nel confronto temporale

`3161c4f99bc63288bf51ed4c14686da462d37c71`: CI `37147549552`, cinque
job SUCCESS. Backend `28ffc4d0-1008-4a9d-b8e8-1896bd82ca76` SUCCESS;
configurazione e nomi variabili identici al baseline, nessuna modifica pendente.
La seconda prova ha letto percorsi Mapbox reali per auto, piedi e bici,
traffico e meteo, posizione corrente e wake persistenti. Nessuna scheda.
La scansione ha motivato il silenzio con mezzo non scelto e partenza già
passata, benché auto e bici fossero ancora nei tempi. Il payload mescolava
ora locale e UTC, e solo l'opzione a piedi aveva già perso il margine.

Aggiunta aritmetica per ogni lettura: ora locale, secondi residui per mezzo,
margine ancora disponibile e ritardo stimato partendo ora. Questi fatti
si aggiornano anche con cache riusata, senza cambiare la scadenza della
stima. Discovery e audit devono confrontare ogni mezzo separatamente;
la scelta del mezzo resta dell'utente, quella della rilevanza resta del modello.
70 test locali PASS, inclusi fusi misti e cambio all'ora solare. La terza
prova aspetta fino a sei minuti senza scansioni forzate né lettura preventiva
dell'endpoint dei percorsi: osserva il lavoro avviato dal calendario.
