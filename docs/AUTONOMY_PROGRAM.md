# ORA — Programma di autonomia trasversale

Data: 25 settembre 2026. Stato: piano di implementazione, non funzionalità
consegnata. Deriva dalla richiesta del proprietario: ORA deve lavorare di
iniziativa sui diversi aspetti della vita, senza aspettare una domanda.
ROADMAP.md resta la fonte canonica dell'ordine delle fasi.

## 1. Contratto di prodotto

Con informazioni accessibili e autorizzate, ORA riconosce una situazione
utile, approfondisce, prepara o realizza un risultato entro la propria
autorità, verifica ciò che è successo e comunica ciò che serve. Non chiede
all'utente di dirigere ogni passaggio. Non inventa bisogni per generare lavoro.

L'autonomia è generale nel ragionamento; la copertura effettiva dipende da
fonti e strumenti. «Qualsiasi aspetto della vita» è la direzione del prodotto,
non una promessa che oggi ogni dominio e ogni operazione siano supportati.
Ogni capacità deve dichiarare cosa può leggere, preparare, eseguire e verificare.

Tre decisioni distinte: vale la pena approfondire? quale lavoro fare?
quando e come coinvolgere la persona? Il permesso di notificare non deve
essere necessario per fare ricerca; il permesso di leggere non autorizza
scritture, invii o contratti. Ricerca e inferenza consumano risorse: budget
espliciti, senza chiedere conferma per ogni singola ricerca già consentita.

## 2. Evidenze dell'analisi e limiti

### Checkpoint implementazione A0/A2 — 25/09, locale

Riprodotti con test inizialmente rossi: scan di cinque opportunità ne valuta
solo due senza recuperare le altre; una opportunità aggiornata non viene
rivalutata. Correzione locale: repository salva atomicamente fatti e richiesta
di valutazione nello stesso documento. Fingerprint esclude le modifiche di
sola presentazione. Il runtime esistente consuma due record per passaggio,
con lease, timeout, revision fence e recupero dopo arresto. Non viene aggiunto
un nuovo scheduler né avviata una scansione retroattiva di tutto lo storico.

Gli esiti no_goal/create_goal/already_pursuing/clarify/wait/unavailable sono
registrati distintamente, con riferimento all'obiettivo quando disponibile.
Errori temporanei: massimo tre tentativi, poi paused; wait: riesame tecnico
dopo un'ora, massimo tre valutazioni per revisione. Questi sono limiti tecnici,
non una valutazione semantica del momento opportuno. Nuovi fatti riaprono la
valutazione. La creazione fallita di un goal non viene più spacciata per un
goal concorrente senza verificarne l'esistenza. Il recupero periodico rinvia
le nuove valutazioni se è in corso una chiamata.

Limiti ancora aperti: le domande clarify sono persistite ma non ancora
collegate alla UX delle risposte; aggiornare un'opportunità con goal già
aperto non implementa da solo la ripianificazione; fairness tra utenti,
revisione del budget e prova Mongo/cloud restano da completare. Un worker
che abbia già iniziato il giudizio può creare un obiettivo mentre cambiano i
fatti: il fence preserva la nuova valutazione, non sostituisce la successiva
verifica di attualità del piano. Non dichiarare A2 completa.

Ulteriore lacuna A1 confermata leggendo agent/providers.py: document.read
elenca nomi/tag e non legge il contenuto. Servirà un approfondimento mirato
con fonti e permessi, riusando il percorso documentale, non una lettura
indiscriminata di tutti i testi.

Audit Railway read-only: presenti i nomi AMBIENT_RUNTIME, RESEARCH_ENABLED e
TAVILY_API_KEY. Il connettore oscura i valori: la presenza non prova che i
flag siano attivi né che il provider funzioni. Nessuna variabile modificata.

Validazione finale checkpoint: 183 test PASS su admission V4, background,
post-call recovery, autonomous action loop, live runtime, call failure
recovery e readiness. Compileall e git diff --check PASS. Il controllo
architetturale voce ha rilevato un import live nel servizio: readiness ora
delegata a telephone/runtime.py, senza alterare il criterio di disponibilità.
La suite discovery con Mongo reale non è stata completata perché il servizio
non è disponibile localmente; i test con Mongo simulato non la sostituiscono.

Analisi statica del checkout; nessuna nuova verifica live dei flag/provider,
nessuna misura di qualità generale. Commenti e test con mock non sono prove cloud.

| Base presente | Riferimento | Cosa resta da dimostrare |
|---|---|---|
| Polling autonomo delle fonti | backend/connected/polling.py | Ritardo effettivo, autorizzazioni, arretrati e recupero su deployment reale |
| Registro cambiamenti e scansione opportunità | backend/opportunities/discovery.py | Copertura delle mutazioni, dati sufficienti e assenza di perdite |
| Risveglio e recupero in background | backend/ambient/runtime.py, eligibility.py | Funzionamento con app chiusa, più utenti e riavvii |
| Opportunità verso agente | backend/agent/background.py | Considera scan.created[:2]: verificare recupero eccedenze e aggiornamenti |
| Due ingressi alla scansione | backend/ambient/service.py; backend/life_orchestration/scheduler.py | Entrambi chiamano il collegamento all'agente; provare concorrenza e deduplica |
| Obiettivi, passi, evidenze e autorità | backend/agent/service.py, authority.py | Continuità e correttezza oltre il percorso nominale |
| Ricerca e confronto generici | backend/research; backend/comparison | Risultati attuali, pertinenti, applicabili e calcoli completi |
| Dati riassunti per iniziativa | backend/opportunities/snapshot.py | MAX_PER_SOURCE=6 e sintesi brevi: recuperare dettagli senza perdere situazioni |
| Bollette riconosciute | backend/documents/schema_registry.py | Condizioni economiche complete, unità e costo comparabile |
| Gmail come fonte di segnali | backend/connectors/gmail/service.py | Metadati/allegati presenti non equivalgono a contenuto PDF acquisito |
| Home e consegna risultati | backend/home; backend/delivery; backend/agent/visibility.py | Risultati utili, niente duplicati o attività soltanto apparente |

I limiti osservati sono punti da verificare con riproduzioni prima di correggere.
Non introdurre un nuovo orchestratore, un secondo modello della vita o una
tabella di regole del tipo «parola bolletta → compara tariffe».

## 3. Flusso comune da consolidare

Fonte → osservazione con provenienza → situazione collegata alla vita →
opportunità → obiettivo persistente → approfondimento/ricerca/confronto →
risultato o richiesta indispensabile → azione autorizzata → verifica →
comunicazione → revisione quando cambiano i fatti.

Ogni situazione mantiene i riferimenti a persona, oggetti, fonti e obiettivi;
separa fatto osservato, dichiarazione, inferenza, preferenza e informazione
scaduta. Ogni risultato espone fatti usati, assunzioni, calcoli, alternative,
limiti, data delle fonti e condizioni che lo rendono non più valido.
Estendere i modelli esistenti solo dove questo contratto non è già coperto.

## 4. Pacchetti di lavoro, nell'ordine

### A0 — Baseline verificabile e tracciamento

- Inventariare fonti, permessi, strumenti reali/simulati/non collegati,
  flag necessari e configurazione effettiva senza esportare segreti.
- Ricostruire un percorso completo per documenti, calendario, posta e
  informazioni dichiarate; trovare il primo passaggio che perde dati/lavoro.
- Correlare source_ref, change_id, opportunity_id, goal_id, run_id,
  risultato e consegna; riusare journal/evidence esistenti.
- Distinguere silenzio intenzionale, dato assente, provider indisponibile,
  budget esaurito, lavoro rinviato e lavoro completato.
- Riprodurre burst oltre due opportunità, opportunità aggiornata e doppio
  scheduler. Misurare prima di dichiarare che sono bug.

Uscita: matrice con evidenze, baseline riproducibile e lista dei difetti
confermati. Nessuna voce «funziona» basata soltanto sul nome di un modulo.

### A1 — Informazioni sufficienti e relazioni tra ambiti

Checkpoint 25/09: implementata lettura esplicita del testo estratto tramite
document.read, preservando riferimenti nel planner/parser/executor. Elenco
metadati senza input_refs; un documento alla volta con input_refs, estratti
limitati e offset/versione per continuare. Controlli owner/deleted/archived,
permesso capability, testo assente e dati cambiati. 50 test locali PASS.
Non chiude A1: il modello deve ancora dimostrare scelta e lettura spontanea
nel ciclo completo; nessuna acquisizione nuova di allegati Gmail aggiunta.

- Dal riassunto risalire al documento/fatto originale su necessità motivata,
  con controllo permessi e appartenenza a ogni lettura.
- Verificare percorso posta → allegato → ingestione documentale esistente;
  implementare ciò che manca solo entro gli accessi concessi. Limiti MIME,
  dimensioni, deduplica, timeout e provenienza per ogni allegato.
- Collegare fonti che parlano della stessa entità; in caso di ambiguità non
  fondere persone, forniture, eventi o documenti sulla sola somiglianza.
- Trattare validità temporale, documenti sostitutivi, conflitti e revoche.
- Estrarre campi aggiuntivi quando servono al risultato, evitando un enorme
  profilo obbligatorio e domande su informazioni già accessibili.
- Documenti/email/web restano dati non fidati: istruzioni contenute al loro
  interno non cambiano permessi, obiettivi o destinazioni di invio.

Uscita: una situazione usa fatti di più fonti con riferimenti verificabili;
fonte mancante o contraddittoria produce incertezza esplicita, non invenzione.

### A2 — Iniziativa che non perde lavoro

- Persistenza e recupero della valutazione di tutte le opportunità ammesse;
  un limite di batch rinvia il resto, non lo elimina.
- Gli aggiornamenti significativi rivalutano obiettivi e risultati esistenti.
- Distinguere opportunità da mostrare e opportunità su cui lavorare: non
  interrompere alla prima frase «potresti risparmiare» se il lavoro è fattibile.
- Conservare esiti wait/clarify e relativi motivi se oggi non hanno seguito;
  il tempo di ripresa e la condizione di sblocco devono essere tracciabili.
- Ammettere iniziative anche per obiettivi già aperti, scadenze, risultati
  divenuti vecchi e condizioni del mondo cambiate, senza riesaminare ogni
  utente a ogni tick. Riesami mirati e scadenze persistenti.
- Deduplicazione semantica da implementare con identità e evidenze stabili,
  senza affidare l'unicità soltanto al testo generato dal modello.

Uscita: app chiusa, nessuna richiesta Home/chat, nuovo fatto → lavoro autonomo;
burst, riavvio e concorrenza non perdono né duplicano obiettivi.

### A3 — Lavoro fino a un risultato utile

- Recuperare dettagli interni prima di chiedere all'utente; ricercare dati
  esterni quando servono. Informazioni personali non necessarie non vanno
  nelle query pubbliche.
- Definire cosa prova il successo prima dell'esecuzione, con criteri
  verificabili; «ricerca completata» non basta se l'obiettivo era confrontare.
- Ripianificare se emerge un vincolo, scade una fonte o cambia la situazione.
- Ogni dato numerico deve avere unità, periodo e fonte. Conversioni, imposte,
  costi ricorrenti/una tantum e assunzioni vanno trattati coerentemente;
  aritmetica deterministica, nessun numero inventato come operando letterale.
- Per i domini complessi aggiungere validatori/adattatori al confronto
  esistente. Il ragionamento resta trasversale, il controllo del risultato
  usa conoscenze specifiche dove indispensabili.
- Le capacità non collegate producono un risultato parziale esplicito,
  non una dichiarazione di esecuzione riuscita.

Uscita: alternativa applicabile e verificabile, oppure domanda minima davvero
necessaria, oppure conclusione motivata che non conviene cambiare.

### A4 — Autorità, continuità e cambiamenti concorrenti

- Riusare grant/policy, scope, scadenza, revoca e vincolo all'effetto esatto.
- Consultare e preparare entro gli accessi concessi senza conferme ripetute;
  per agire verificare autorizzazione specifica valida al momento dell'atto.
- Invii, chiamate, pagamenti, contratti e atti verso terzi non sono autorizzati
  dalla sola disponibilità di informazioni o da un'opportunità generata.
- Recovery con lease, tentativi limitati, backoff, verifica prima di ripetere
  scritture; invalidare piani su dati cambiati. Un timeout non prova fallimento.
- Budget per lavoro e persona, priorità/fairness della coda e limiti di costo.
  Arresto controllato e spiegabile quando non è possibile proseguire.

Uscita: nessuna azione fuori autorità, nessuna duplicazione dopo retry,
revoca efficace anche durante un lavoro e isolamento fra utenti dimostrato.

### A5 — Esperienza del risultato

- Home mostra che cosa è emerso, perché conta, cosa ORA ha già fatto e
  l'eventuale unica decisione necessaria; prove consultabili senza imporle.
- «Non ora», «non mi interessa», modifica preferenza e ripresa devono
  governare l'obiettivo esistente, senza generarne copie.
- Un risultato sostituito deve essere aggiornato/ritirato. Non notificare
  proposte obsolete né duplicare Home, conversazione e Aggiornamenti.
- Distinguere il successo del lavoro dalla consegna: push assente non deve
  perdere il risultato. Con app chiusa il backend lavora; push sul dispositivo
  resta non verificato finché non supera V3.23.

Uscita: l'utente capisce risultato e scelta necessaria senza leggere un log
tecnico e non deve chiedere «e quindi?» per ottenere il confronto promesso.

### A6 — Prova trasversale e osservazione reale

Eseguire la matrice sotto prima su dati sintetici riproducibili, poi con
modelli/provider reali su dati di prova e infine sul cloud autorizzato.
Nessuna azione reale verso terzi per simulare una prova. Le prove live sono
distinte dai test con risposte del modello prefissate.

## 5. Matrice minima di accettazione

| Caso, senza richiesta di aiuto | Risultato atteso | Variante negativa obbligatoria |
|---|---|---|
| Bolletta disponibile | Approfondimento e confronto personale documentato | Offerta attuale già conveniente; consumi mancanti; prezzo pubblicitario incompleto |
| Turno cambiato + appuntamento | Impatti e proposta praticabile | Falso conflitto di fuso; modifica già risolta dall'utente |
| Esame vicino + avanzamento studio | Piano sostenibile sui tempi disponibili | Dato di avanzamento vecchio; nessun tempo realmente libero |
| Contratto prossimo al rinnovo | Condizioni, alternative e finestra decisionale | Rinnovo disattivato o vincolo incompatibile con l'offerta |
| Prenotazione modificata + viaggio | Conseguenze sui collegamenti e opzioni praticabili | Messaggio duplicato o prenotazione annullata successivamente |
| Documento casa + pratica aperta | Documento collegato e prossimo passo preparato | Documento intestato a un'altra persona; versione superata |
| Spesa ricorrente cambiata | Verifica della causa prima di suggerire interventi | Aumento dovuto a consumo/servizio diverso, non al prezzo |
| Informazione neutra/promozionale | Silenzio motivato, nessun lavoro inutile | Testo tenta di impartire istruzioni all'agente |

Almeno un caso non usato nello sviluppo e almeno due che collegano ambiti
diversi. Salute, questioni legali e finanziarie delicate: organizzazione,
raccolta fonti e preparazione; nessuna decisione professionale o impegno
automatico senza limiti specifici. Non introdurre nuove integrazioni bancarie
per far funzionare questa fase: usare fonti già disponibili/autorizzate.

## 6. Misure e criteri di rilascio proposti

Raccogliere tempo fonte→acquisizione→lavoro→risultato→consegna, distribuzione
p50/p95, costo per risultato utile, domande evitabili, duplicati, falsi allarmi,
opportunità utili perse e risultati obsoleti. Il numero di notifiche non è
una metrica di successo. Definire in anticipo l'esito atteso per ogni fixture.

- Tutti i casi minimi devono superare le varianti obbligatorie; nessun errore
  critico di autorizzazione, isolamento, numeri inventati o scrittura duplicata.
- Almeno tre esecuzioni per scenario con modello reale, registrando anche i
  fallimenti; non provano affidabilità universale, rilevano instabilità evidenti.
- Almeno 7 giorni di osservazione cloud controllata prima di dichiarare la
  fase completata; provider reali e app chiusa, con prove di restart/revoca.
- Obiettivi iniziali da validare sulla baseline: avvio lavoro entro 60 s dal
  fatto già acquisito; risultato semplice entro 2 min; ricerca multi-fonte
  entro 5 min, p95 sotto carico alpha. Sono target, non prestazioni attuali.
- Misurare separatamente il ritardo del provider/polling: questi target non
  promettono un risultato entro 60 s dall'email ricevuta dal provider.
- Se il target non è raggiungibile, documentare causa e correggere budget,
  coda o perimetro; non dichiarare successo sulla sola presenza di un job.

## 7. Sequenza, rischi e primo intervento

A0 → A1/A2 → A3 → A4 → A5 → A6, con autorità e osservabilità presenti fin
dall'inizio. A1 e A2 si sviluppano per piccole sezioni verticali; poi variare
il dominio per scoprire dipendenze nascoste. I test negativi accompagnano
ogni sezione. Evitare mesi di infrastruttura prima del primo risultato reale.

Primo intervento concreto: tracciare documento acquisito → opportunità →
obiettivo → risultato, con app chiusa, poi ripetere con più di due opportunità
e con aggiornamento di una già esistente. Correggere il primo difetto
confermato e verificare lo stesso collegamento con un cambio calendario.

Rischi principali: troppi giudizi LLM in cascata, sintesi che perdono fatti,
fonti limitate, sovrapposizione scheduler, consigli non applicabili, costi,
false urgenze e dati obsoleti. Ogni rischio ha un controllo nei pacchetti
sopra; non risolverli aggiungendo un altro motore generale.

Stime di calendario e costo saranno formulate dopo A0: prima sarebbe falsa
precisione. Ogni pacchetto termina con evidenze, difetti aperti e un criterio
di uscita; nessun completamento per numero di file o test verdi soltanto.

## 8. Rapporto con la roadmap

V4 viene anticipata prima di V3.23 e ampliata a questo programma trasversale.
V3.23 resta sospesa; preparazione iOS conservata. V3.22 conserva le prove
rinviate per scelta del proprietario, non trasformate in PASS.
La porzione di continuità indispensabile entra ora; V5 resta l'estensione
alle commissioni lunghe e ai casi complessi. V7 resta il consolidamento
architetturale ampio, non una giustificazione per aggiungere motori oggi.
V4.1 alpha richiede sia questo programma sia i gate device e privacy,
backup/ripristino, isolamento e revoca già previsti.

Questa revisione modifica documenti di progetto soltanto: nessun nuovo
runtime implementato, nessuna migrazione, push, chiamata o deployment.
