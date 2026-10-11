# Verifica v160 — momento utile e avviso della Situation

## Scopo e base

La richiesta è conoscere il momento utile per intervenire su un'attività
reale segnalata a ORA. Il caso di riferimento è il bucato all'aperto: stimare
quando ritirarlo, aggiornare la stima con le condizioni effettive e segnalare
un rischio anticipato. Il codice rimane generale; nessun classificatore per
parole chiave e nessuna durata fissa specifica del bucato.

Base di lavoro: `e15bc7a9e6f98153a8c9dc9b5f62243ac8eb065a`, comprendente
il rilascio Situation/finanza #204 e la successiva PR Vision #205. Le modifiche
Vision sono conservate. Il rapporto conclusivo del precedente rilascio è
in `QA_ROADMAP_RESUME_2026_10_11.md`.

Durante i gate è arrivata la PR Vision #206 sulla base
`424372f10a512847cdecb736ba53460ce5c48eb7`: integrata conservandone tutti i
14 file, incluse le aggiunte in coda ai quattro documenti condivisi. Il
commit candidato viene quindi verificato con entrambe le lavorazioni.

## Comportamento richiesto

1. Una segnalazione reale ancora attiva conserva il proprio scopo utile,
   luogo e inizio fisico quando stabilito dalla persona. Un esempio futuro
   non avvia un'attività e la creazione del record non inventa un inizio.
2. Il worker rilegge le fonti pertinenti e produce una valutazione sostenuta
   da evidenze: finestra stimata, azione attuale o un dato indispensabile
   mancante. Il tempo del controllo non viene esposto come tempo di ritiro.
3. Mappa, Home, Situation e dettaglio usano la stessa valutazione. L'azione
   anticipata per pioggia è distinta dalla stima di completamento.
4. Il nuovo controllo rilegge le condizioni; il semplice timer non conclude
   il lavoro. Scadenza e revisione tolgono autorità a una vecchia stima.
5. L'avviso utile può essere consegnato dopo il completamento del watch,
   senza dichiarare risolta l'attività fisica. Una conferma di ritiro o
   annullamento della persona chiude invece la Situation e blocca i vecchi avvisi.

## Cambiamenti verificabili

- `desired_outcome` e `started_at` sono campi opzionali separati da
  `attention_intent`, registrazione e stima. Ammissione, refresh e schedule
  mantengono lo scopo della persona.
- `SituationOutcomeAssessment` è persistita sul goal esistente e proiettata
  come `follow_up.outcome`; identità, revisioni, riferimenti, date e validità
  vengono controllati dal codice.
- Il meteo mantiene istanti del provider, date orarie, fuso e recupero.
  La località è ancorata alla Situation; la posizione corrente della persona
  non sostituisce quella dell'attività.
- Le evidenze recenti non vengono escluse dalla selezione quando si accumulano
  molti controlli; una base empirica limitata resta disponibile alla valutazione.
- I payload lunghi delle Situation restano JSON validi e limitati: orologio,
  inizio fisico, riferimenti e ultimo insieme di condizioni restano disponibili
  al modello; un contesto eccessivo viene dichiarato incompleto esplicitamente.
- La consegna rilegge la fonte prima di inviare. Il completamento del watch
  permette soltanto il suo esito finale ancora valido, non vecchie domande.
- L'outbox della Home conserva il legame verificato con l'esito prima della
  scrittura. Ripristino dopo riavvio e lettura di righe storiche rivalidano
  fonte, scadenza e testo, impedendo la ricomparsa di indicazioni superate.
- I controlli raggiungono la Situation anche durante la verifica iniziale;
  una correzione esplicita può rimuovere un inizio fisico non fondato.
- Le superfici condividono un componente con scadenza a pagina aperta e
  dettagli del controllo richiudibili; nessuna stima viene ricavata da «oggi».
- Una chiusura strutturata riuscita non viene descritta come strumento
  indisponibile soltanto perché la risposta del modello conteneva un tool vuoto.

## Test e limiti del collaudo

Le prove usano dati sintetici, il database in memoria e, dove necessario,
un modello programmato, fonti esterne simulate e un trasporto di notifica
registrabile. Eseguono codice di produzione per persistenza, worker,
proiezione, pianificazione e consegna. Nessun messaggio a terzi, pagamento,
appuntamento o push reale viene effettuato da queste prove.

Il test verticale attraversa creazione della Situation, ammissione, wake
Ambient, due esecuzioni del worker, executor e adapter: prima stima, poi
nuova lettura e avviso finale. Lo stesso percorso copre sia l'esito pronto
stimato (`outcome_ready`) sia l'azione protettiva (`early_risk`). Home e
dettaglio conservano l'esito valido dopo il completamento interno e lo
rimuovono alla scadenza. Modelli e risposte esterne sono fixture sintetiche.

| Area | Evidenza locale |
|---|---|
| Backend aggregato finale | 319 PASS in 34 moduli: valutazione, worker, meteo/luogo, consegna, Home/outbox, chiusura, clock, recupero e azione immediata |
| Conversazione e proiezione | 19 PASS su chiusura, fallimento reale di persistenza, contesto ipotetico, guard memoria temporanea e mappa |
| Frontend integrato | 31 PASS, inclusi 16 nuovi casi sull'esito, controlli Home, calendario e presenza |
| Mobile Chromium | 5 PASS, compreso stima → rischio anticipato → indicazione finale dopo completamento del watch |
| TypeScript | PASS sulla base integrata con Vision #205 e #206 |
| Export web | PASS, 1752 moduli sulla base integrata con Vision #206 |
| Compilazione Python e diff | PASS; nessun errore di sintassi o whitespace |
| WebKit locale | Non avviato per dipendenze di sistema mancanti; copertura affidata al gate CI con installazione delle dipendenze |

I totali dei test che si sovrappongono non vanno sommati. I nuovi test backend
su valutazione, luogo/meteo, consegna e recupero degli aggiornamenti sono gate
espliciti delle workflow CI e Situation. Gli esiti finali del commit candidato
e del rilascio sono registrati nella PR associata alla patch.

L'aggregato finale ha 844 warning delle dipendenze e delle fixture, senza
fallimenti. La verifica ha rilevato e corretto una regressione nel recupero:
un goal legacy parziale o un assessment malformato non deve impedire la
diagnosi di un checkpoint mancante. I due test storici sono rimasti invariati
e passano; un nuovo caso copre la proiezione opzionale malformata. I payload
lunghi sono verificati ai confini reali di choose e verify.
Il gate remoto ha inoltre richiesto di mantenere la formulazione storica
dell'istruzione sulla prima aspettativa utile: ripristinata con il vincolo
esplicito delle evidenze disponibili, mantenendo invariati i test v88b.

## Riscontro sul caso reale precedente

La persona ha confermato che l'attività precedente era già terminata e ha
corretto la località. Queste informazioni sono state inviate nella conversazione
del caso esistente, senza creare un nuovo caso. Alle 22:17 UTC dell'11 ottobre
(00:17 del 12 ottobre in Italia), la mappa mostrava «Nessuna situazione temporanea»
e il precedente dettaglio risultava scaduto o non più attivo.

La risposta in chat aveva mostrato un errore generico nonostante la chiusura:
il difetto è riprodotto dal test con mutazione riuscita e tool vuoto. Un test
separato verifica che un vero errore di persistenza non venga convertito in
una conferma falsa.

Questa verifica non afferma che un nuovo carico reale sia stato steso,
fisicamente asciugato o ritirato. Il software produce una stima del momento
utile; la precisione su una nuova attività e la ricezione sul dispositivo
rimangono riscontri reali distinti dai test del trasporto.

## Integrazione e rilascio

Il rilascio segue i gate del repository sul commit candidato: CI generale,
regressioni Situation e test mobile Chromium/WebKit. Merge e distribuzione
devono indicare l'esatto commit verificato; il risultato viene registrato
anche nella PR con stato dei servizi e health.

Nessuna nuova dipendenza di produzione, configurazione o collezione. I nuovi
campi sono opzionali nelle strutture esistenti; non serve una migrazione
distruttiva. Le integrazioni con account e canali esistenti mantengono i propri
permessi e requisiti di configurazione.
