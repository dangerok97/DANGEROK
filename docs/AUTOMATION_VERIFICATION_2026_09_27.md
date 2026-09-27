# ORA — Verifica delle automazioni, 27 settembre 2026

## Comportamento richiesto

Il primo messaggio di **ogni nuova sessione di conversazione** apre la rete
progressivamente da un punto alla mappa 3D. Testo e voce condividono l'ingresso.
Secondi messaggi, retry, navigazione e riapertura di una sessione esistente non
lo ripetono. La risposta non aspetta l'animazione. Il moto leggero già approvato
rimane; interazione immediata e riduzione del movimento sono rispettate.

## Lacune corrette

| Caso | Comportamento verificato |
|---|---|
| ORA chiede un dato prima di iniziare | Domanda visibile nel dettaglio, risposta sulla sua revisione e ripresa della stessa admission, senza chat parallele |
| Risposta duplicata o ormai superata | Idempotenza per la stessa risposta; conflitto esplicito sulla vecchia domanda; isolamento fra proprietari |
| Fonte modificata durante il lavoro | Stesso goal, nuovo piano, vecchie prove conservate come superate; preparazione e richieste precedenti ritirate |
| Fonte chiusa o scaduta | Il lavoro automatico viene fermato, anche se era in attesa di una risposta |
| Utente annulla un'attività | Fermata di quel goal e delle sue sveglie; nessuna cancellazione delle altre; vecchio worker non può rianimarlo |
| Risposta a una domanda informativa | Ripresa del lavoro e azzeramento del budget dei tentativi precedenti; non vale come autorizzazione a un'azione |
| Ricerca/provider lento | Attività dovute separate e limitate; timeout inferiore alla lease; arresto raccoglie le attività in corso |
| Retry esauriti o ultimo worker morto | Sveglia terminale, identità liberata per il recupero del lavoro persistito |
| Sveglia oltre sette giorni | Conservazione fino alla scadenza più sette giorni; aggiornata anche sul rinvio, senza cancellazione TTL anticipata |
| Rinvio oltre sei ore | Timer segmentato che si riarma senza un riavvio; una nuova data anticipata sostituisce quella vecchia |

Le nuove informazioni vengono rivalutate dal pianificatore comune. Nessuna
regola specifica per un settore sostituisce il giudizio del modello. Le
verifiche deterministiche dimostrano persistenza, isolamento e transizioni;
non certificano da sole la qualità di una raccomandazione generata dal modello.

## Percorsi esistenti conservati e gate

- Calendario e Gmail: polling incrementale con fairness, revoca e prima
  sincronizzazione; test collegamenti/autosync nel gate backend.
- Documenti: discovery → admission → lettura reale/paginata → risultato
  verificato con provenienza, senza visita alla Home; test controllati.
- Energia/gas/telefonia/assicurazioni: monitor offerte già presente, suo gate
  dedicato preservato. Il lavoro lento ora non serializza tutto il runtime.
- Preparazione calendario, consensi e fuso orario: suite dedicate preservate.
- Chiamate: correzioni dei destinatari e recupero dopo la telefonata, trasporto
  e runtime nel gate separato; nessuna telefonata reale di prova.
- Voce: sintesi progressiva e identità originale Algieba preservate.

## Evidenza al commit applicativo

109 test backend locali PASS (12 file, inclusi 17 nuovi casi di continuità).
41 test frontend PASS, oltre ai product guard Home/Vita/chiamate. TypeScript,
compileall, lint senza errori ed export web/iOS PASS. Renderer della scena
condivisa ispezionato su desktop e mobile: quattro istanti dell'ingresso.

Il container locale non avvia Mongo (`open: Operation not permitted`); nessun
aggiramento. CI aggiunge suite ambient, continuità e documento automatico,
più una seconda esecuzione dei 17 nuovi casi su database Mongo 6 isolati.
Ciò verifica gli indici/claim con il database reale, oltre al mock locale.
Esito CI e distribuzione saranno registrati nel verbale di rilascio.

## Limiti ancora aperti

- Push reale su telefono richiede registrazione dispositivo, configurazione
  Expo/EAS e prova su dispositivo. Il backend può lavorare senza consegnare push.
- Posizione in background e dialogo al microfono richiedono prova su dispositivo;
  l'export iOS non equivale a una prova nativa fisica.
- EnableBanking dipende da configurazione sandbox/callback/chiave privata:
  nessuna integrazione bancaria viene presentata come operativa senza tali dati.
- La lettura automatica degli allegati PDF Gmail non è inclusa: il percorso
  attuale usa corpo/metadata email e i documenti caricati/connessi disponibili.
- La matrice V4 con modelli live (studio, viaggio, controllo neutro) e
  l'osservazione per sette giorni restano gate aperti. Non si dichiara ORA un
  assistente universale completato né si azzera il backlog V4 con questo rilascio.

Nessuna nuova dipendenza di runtime, migrazione distruttiva, modifica alle
credenziali, telefonata o comunicazione reale. Dataset di prova sintetici.
