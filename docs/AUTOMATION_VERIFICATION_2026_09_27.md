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

110 test backend locali PASS (12 file, inclusi 18 nuovi casi di continuità).
41 test frontend PASS, oltre ai product guard Home/Vita/chiamate. TypeScript,
compileall, lint senza errori ed export web/iOS PASS. Renderer della scena
condivisa ispezionato su desktop e mobile: quattro istanti dell'ingresso.

Il container locale non avvia Mongo (`open: Operation not permitted`); nessun
aggiramento. CI aggiunge suite ambient, continuità e documento automatico,
più una seconda esecuzione dei 18 nuovi casi su database Mongo 6 isolati.
Ciò verifica gli indici/claim con il database reale, oltre al mock locale.
CI del primo checkpoint 36330185896 su `7dea1f6b5d91df8d6c91381f2d4f6b2866e9bb04`:
cinque job SUCCESS. Backend: 513 esecuzioni PASS e 5 skip legacy; telefonia:
281 PASS. Nei 513 sono compresi 116 test di autonomia/ambient e 18 casi
rieseguiti con Mongo reale: i conteggi includono quindi le ripetizioni deliberate.

Due controlli storici sono stati corretti senza ridurre la copertura: database
isolato per ciascuna suite ambient (le code globali di utenti sintetici diversi
si consumavano fra loro), e prova comportamentale del lifecycle di polling al
posto dell'obbligo di una chiamata sequenziale nel testo sorgente. La nuova
prova avvia il loop, osserva polling e lavoro dovuto, mantiene la fonte lenta e
verifica la cancellazione pulita all'arresto. Nessun test è stato escluso.

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

## Correzione emersa nella prova pubblica: account con soli documenti

La prima prova dopo il deploy ha caricato ed estratto correttamente un documento
sintetico, ma non ha generato letture automatiche: il selettore cercava nuovi
utenti soltanto fra i connettori esterni. Un account con soli documenti e senza
visita alla Home poteva quindi restare fuori dalla coda.

Caricamento ed estrazione ora scrivono un marker nello stesso documento. Il
polling già esistente ammette quei marker nella propria coda; li rimuove solo
dopo la scrittura riuscita e sulla stessa revisione. Un crash non perde il
passaggio, un'estrazione successiva conserva la propria richiesta e una lettura
in corso non può rinviare per mezz'ora una modifica appena arrivata. Un indice
parziale additivo (`document_read_handoff`) limita la scansione ai marker.
Nessun nuovo scheduler, modello nel caricamento, connettore o backfill storico.

Due nuove prove coprono account senza Google/Home, lettura ed estrazione
successiva, isolamento del proprietario e assenza di backfill. 21 prove locali
PASS: 20 casi di continuità più il test del segnale di estrazione differita.
Il seguito è stato verificato in CI e pubblicamente, come registrato di seguito.

## Rilascio verificato — 27 settembre 2026, continuità e apertura per sessione

- Backend `e85d93567aea9e9b35290f096001ca4f79d2f29d`, deployment
  `1da90de3-41ff-460d-a6e1-96481491252b`: SUCCESS.
- Web `7dea1f6b5d91df8d6c91381f2d4f6b2866e9bb04`, deployment
  `2bbeef90-7c8d-407d-bea9-50c62b070409`: SUCCESS. Il seguito modifica solo il
  backend; il frontend di e85d935 è identico a quello distribuito.
- CI `36330958522`: tutti i cinque job SUCCESS. Backend 518 esecuzioni PASS,
  cinque skip legacy; telefonia 281 PASS. Nel backend: 119 prove di continuità/
  ambient/documenti e 20 casi rieseguiti su Mongo 6 reale (totali con ripetizioni).
- Frontend: 41 test mirati PASS, product guards e TypeScript PASS; export web
  e iOS PASS. Scena effettiva ispezionata su desktop/mobile a quattro istanti.
  Bundle pubblico `entry-d5db9877d0d3511f11a0d1aef9dbed3f.js` con gate per
  sessione, revealKey, risposte revisionate e streaming PCM. Health HTTP 200.
- Prova pubblica: account sintetico nuovo, solo upload; niente Home, chat o
  sincronizzazione manuale. Documento estratto e letto dal sensore dopo
  **8.42 secondi**. Nessun obiettivo per il materiale esplicitamente
  dimostrativo; il log del relativo giro registra un segnale classificato come
  rumore. Questa prova dimostra ingestione autonoma, non una raccomandazione live.
- Configurazione Railway e volume documenti invariati; `preDeployCommand=[]`.
  Nessuna nuova dipendenza. Un solo indice additivo sui marker dei documenti,
  creato dal normale bootstrap. Nessuna migrazione manuale o distruttiva,
  telefonata, messaggio o push reale nelle prove.

La rete si apre al primo messaggio scritto/vocale di **ogni nuova conversazione**;
riapertura della stessa, secondo messaggio e retry non la ripetono. Il dettaglio
degli aggiornamenti segue il lavoro automatico, raccoglie chiarimenti e non
avvia copie. Fonti cambiate/scadute, cancellazioni, rinvii e retry hanno recuperi
verificati. Nuovi account con soli documenti entrano nella coda senza Google.

Limiti ancora aperti e matrice di verifica:
`AUTOMATION_VERIFICATION_2026_09_27.md`. V4 non è dichiarata completa: restano
la qualità della matrice live, l'osservazione longitudinale, configurazioni/
prove push e banca, e l'ingestione degli allegati Gmail.
