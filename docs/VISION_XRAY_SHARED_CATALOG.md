# ORA Vision X-Ray — Catalogo condiviso che cresce con l'uso

Data: 2026-10-11
Stato: requisito di prodotto e specifica di implementazione. NON catalogo operativo, NON collaudo live superato.
Ramo: `feat/ora-vision-xray`. Nessuna modifica al ramo delle riparazioni o al deployment.

## Decisione di prodotto

Vision X-Ray deve funzionare DENTRO la fotocamera di ORA, mantenendo il video live: riconoscimento dell'oggetto, aggancio e scomposizione virtuale stilizzata, componenti selezionabili e spiegabili. Lo stile richiesto e' tecnico/HUD, wireframe e particelle con accenti azzurro/arancio. Non una sequenza di schede con icone e non una sola immagine generata.

La V1 deve partire da una banca dati di scomposizioni degli oggetti comuni. Quando manca un modello appropriato, ORA prova a costruirne uno con l'AI, impiegando piu' tempo, e conserva il risultato riutilizzabile. Gli utenti successivi possono beneficiare dello stesso lavoro, senza rigenerare ogni volta la scomposizione.

Principio: riconosci -> cerca -> riusa/adatta oppure genera -> controlla -> salva/versiona -> riusa.
La crescita del catalogo non e' addestramento automatico dei pesi dell'AI e non trasforma un'ipotesi in un fatto verificato.

## Stato reale del prototipo esaminato

Esaminato il commit `495840699fe9f181bdf4b793ab9920d2b98c3007` del ramo feature:
- `backend/vision_xray.py`: analisi di una foto con elenco di parti, `illustrative_exploded_2d`, `verified_3d_model=False`; nessuna persistenza delle scomposizioni.
- `frontend/src/vision-xray/CameraPreview.web.tsx`: acquisizione singola automatica, poi passaggio al fermo immagine. Il commento e il comportamento prevedono la chiusura dello stream.

Questi elementi sono un abbozzo, NON soddisfano la richiesta live. Questa specifica supera la precedente impostazione foto -> schema. Non considerare completato il catalogo perche' esiste questo documento.

## Tre livelli di identita', non una voce per ogni fotografia

1. Famiglia: es. telecomando tradizionale a infrarossi. Struttura tipica; non rappresenta ogni telecomando esistente.
2. Variante/modello: struttura specifica quando marca, modello e revisione sono supportati da evidenze adeguate. Non dedurre parti interne identiche solo dall'aspetto esterno.
3. Osservazione privata: l'esemplare inquadrato, la posa, l'eventuale danno e i dettagli personali. Non pubblicarli nel catalogo condiviso.

Mille scansioni compatibili possono riusare una voce. Revisioni hardware diverse non devono essere fuse automaticamente. Riconoscimento incerto -> chiedere un'altra vista o proporre una famiglia come approssimazione dichiarata, non creare una falsa identita' esatta.

L'evidenza `visible` appartiene alla singola osservazione: una parte visibile in una scansione precedente non e' automaticamente visibile nella scansione successiva.

## Comportamento in fotocamera

### Modello disponibile

Riconoscimento -> corrispondenza con una versione pubblicabile -> caricamento/cache degli asset -> allineamento alla nuova inquadratura -> animazione e selezione dei componenti. Il riuso evita la generazione, non elimina riconoscimento, tracking, caricamento o limiti del dispositivo.

### Modello simile ma non esatto

Mostrare, solo se utile, una struttura di famiglia con dicitura `Schema tipico`. Adattare le proporzioni esterne sostenute dalle immagini; non inventare dimensioni, componenti o revisione hardware. Una variante nuova diventa candidata separata, non sovrascrive la famiglia.

### Nessun modello utile

Il video resta aperto mentre un lavoro asincrono:
1. raccoglie solo le viste necessarie con autorizzazione e minimizzazione;
2. identifica famiglia e possibili varianti;
3. cerca fonti tecniche pertinenti e utilizzabili, quando disponibili;
4. costruisce la struttura delle parti e gli asset separabili;
5. esegue controlli tecnici, di contenuto e di riuso;
6. consegna un modello coerente oppure un limite esplicito.

Stati comprensibili: `Riconosco l'oggetto`, `Cerco una scomposizione`, `Creo un nuovo modello`, `Controllo le parti`, `Pronto`. Nessuna percentuale o attesa inventata. Tempi e costi di generazione da misurare su oggetti/dispositivi reali; nessuna promessa di pochi secondi per gli oggetti sconosciuti.

Una costruzione incompleta puo' mostrare un'anteprima dichiarata, ma non deve essere pubblicata come scomposizione pronta. Se non c'e' una ricostruzione attendibile, registrare il bisogno non coperto e lasciare l'utente nella fotocamera: niente finto successo.

### Live non significa rigenerare ogni fotogramma

Separare il ciclo veloce locale (video, tracking e rendering) dalle chiamate AI meno frequenti (riconoscimento/ricostruzione). Il modello generato si aggancia all'oggetto ancora presente, non a coordinate obsolete. Se il tracking viene perso, nascondere o attenuare l'esploso e riagganciare: non farlo scivolare su un altro oggetto.

Il fermo immagine puo' essere una scelta esplicita dell'utente, non il comportamento obbligatorio spacciato per live. La simulazione sovrappone parti virtuali: l'eliminazione visiva dell'oggetto fisico dal video sarebbe un'ulteriore funzione di compositing, da verificare separatamente. Non e' necessaria per il primo overlay live.

## Cosa deve contenere una scomposizione

Una risposta testuale con sette nomi NON e' un asset riutilizzabile per la funzione richiesta.

Ogni versione comprende:
- identita' canonica, famiglia, eventuale variante/revisione e criteri di compatibilita';
- albero dei componenti con identificatori stabili e relazioni padre/figlio;
- geometria separata per le parti principali, oppure ricetta parametrica controllata che la produca;
- posizione assemblata, posizione esplosa, pivot, trasformazioni e ordine dell'animazione;
- riferimenti delle zone selezionabili e testi esplicativi;
- provenienza delle affermazioni, parti tipiche/non osservate e limiti;
- fonti, diritti di riuso, versione, controlli e motivo dell'eventuale ritiro;
- asset mobili ottimizzati e versione dello stile HUD, separata dalla struttura tecnica.

Formato candidato: glTF/GLB con nodi distinti e manifest di metadati. Nodi, mesh e animazioni sono supportati da glTF; corrispondenza semantica, picking, tracking e stile HUD devono essere implementati da ORA. Un file 3D monolitico non diventa separabile solo cambiando estensione.

Materiali, valori elettrici, misure, temperature, marche o numeri di componenti non verificati non devono essere riempiti per rendere l'HUD piu' scenografico.

## Catalogo degli oggetti e libreria delle parti

Prevedere entrambe le strutture. Corpi, coperchi, pulsanti, molle e altre parti possono essere riutilizzati come geometrie parametriche quando compatibili. Riutilizzare una geometria NON prova l'equivalenza tecnica o la compatibilita' di un ricambio.

L'AI dovrebbe prima cercare un intero modello adatto, poi moduli compatibili, e generare ex novo solo quello che manca. Non eseguire codice arbitrario prodotto dall'AI: le ricette devono usare un formato dichiarativo limitato e validato.

## Inserimento automatico senza propagare errori

Separare tre dimensioni indipendenti:
- provenienza: `seed`, `generated`, `source_based`;
- livello di evidenza: `illustrative`, `source_supported`, `model_verified`;
- ciclo di pubblicazione: `candidate`, `checking`, `published`, `quarantined`, `retired`.

Generato non significa sbagliato; pubblicato non significa verificato. Una ricostruzione AI puo' diventare riutilizzabile come `illustrative` dopo i controlli, con tale stato sempre visibile. La promozione a `model_verified` richiede evidenze riferite al modello/revisione, non l'autovalutazione di un altro LLM o il numero di utenti che l'hanno visualizzata.

Automatizzare controlli di schema, integrita' degli asset, identificatori e collegamenti, trasformazioni finite, dimensioni/rendering, selezione delle parti, coerenza fra testi e geometrie, deduplicazione e presenza dei diritti necessari. Questi controlli tecnici non certificano la verita' dell'interno. Difetti, contraddizioni, fonti insufficienti, diritti incerti o contesti rischiosi impediscono la promozione automatica e possono richiedere revisione dedicata.

L'esito della prima generazione va conservato come candidato solo nel perimetro autorizzato. Il catalogo servito a tutti deve risolvere esclusivamente versioni pubblicabili. Le versioni errate si possono ritirare; le cache devono recepire il ritiro. Le segnalazioni degli utenti propongono correzioni, non modificano direttamente il modello comune.

## Privacy e contributi

L'autorizzazione alla fotocamera non equivale al consenso a condividere immagini o ad addestrare modelli. Rendere esplicito l'eventuale contributo al catalogo; l'analisi personale deve restare utilizzabile anche senza contributo condiviso.

Per default non salvare nel catalogo comune foto originali, stanze, volti, nomi, posizione, seriali, testo privato, texture fotografiche o descrittori direttamente derivati da fotografie personali. La voce comune deve essere uno schema generalizzato privo di contenuti personali. Solo i contributi autorizzati e filtrati possono alimentarla. Le caratteristiche di riconoscimento comuni vanno costruite da asset e fonti utilizzabili, non riciclando indiscriminatamente le scansioni private.

Eventuali immagini temporanee necessarie a un lavoro asincrono: storage privato, accesso limitato, scadenza breve documentata, cancellazione, nessun log dei byte. Aggiornare la comunicazione attuale `non salva gli scatti sul server` se l'implementazione introduce storage temporaneo: non mantenere una promessa non piu' vera.

Asset e manuali esterni richiedono provenienza e diritti compatibili con il riuso previsto. Essere reperibile online non e' autorizzazione a redistribuire. Questa e' una regola di progetto, non una verifica legale gia' svolta.

## Architettura da implementare

Mantenere Expo/React Native e FastAPI/MongoDB; non sostituire lo stack. Isolare il catalogo condiviso dalla memoria personale di ORA.

Entita' proposte:
- `vision_catalog_models`: identita', ambito di corrispondenza e versione pubblicata;
- `vision_catalog_versions`: manifest immutabili, evidenze, diritti e risultati dei controlli;
- `vision_catalog_parts`: geometrie/ricette riutilizzabili;
- `vision_build_jobs`: lavori durevoli, stato, lease, scadenza e contesto privato minimo;
- `vision_catalog_feedback`: segnalazioni e richieste di revisione.

Asset binari in object storage, non nel documento Mongo; distribuzione/cache solo per le versioni pubblicabili. Il client non decide se un modello e' verificato e non puo' scrivere direttamente nel catalogo comune.

Un servizio di risoluzione restituisce `exact`, `family`, `building` oppure `unknown`, con versione, livello di evidenza e limiti. Indici univoci e identificatori canonici evitano una voce per ogni scansione. Lock/lease durevoli con scadenza e controlli di versione impediscono generazioni duplicate o completamenti tardivi che sovrascrivono lavori nuovi. Nessun accorpamento fra contesti privati non autorizzati.

Limiti per utente e globali, budget dei lavori, scadenze, cancellazione e recupero dopo riavvio fanno parte della V1. Senza budget disponibile: continuare con un modello pubblicato compatibile o dichiarare il limite, non lanciare lavori costosi senza fine.

## Popolamento V1

Proposta di dimensionamento iniziale: 30-50 famiglie frequenti, da approvare in base a qualita' degli asset, fonti disponibili e prove. Non sono gia' presenti nel codice.

Esempi: telecomando, mouse, tastiera, controller, penna a scatto, matita portamine, forbici, pinzatrice, bottiglia con tappo, borraccia, pompa manuale, torcia, ventilatore. Distinguere famiglie e varianti significative; non presentare una struttura generica di smartphone come modello esatto di qualunque telefono.

Per ciascun seed: struttura sensata, asset effettivamente separabili, parti selezionabili, spiegazioni controllate, diritti definiti e prova nella fotocamera. Per gli oggetti rischiosi la visualizzazione e' educativa, non guida operativa allo smontaggio.

## Criteri di accettazione obbligatori

1. Un oggetto comune usa un vero asset prepopolato: nessuna chiamata alla generazione dell'esploso in caso di hit.
2. Due utenti autorizzati che richiedono lo stesso nuovo modello producono una sola versione comune pubblicabile, senza condividere foto o contesto privato.
3. Un modello generato viene salvato, sopravvive al riavvio e viene riusato da una nuova sessione; una risposta mantenuta solo in RAM non basta.
4. Un esito incompleto o errato non e' servito globalmente come pronto. Un modello illustrativo mantiene l'etichetta anche dopo cento riusi.
5. Il video resta live durante ricerca, generazione e animazione. Una foto con overlay o una galleria separata non supera il test.
6. Lo spostamento dell'oggetto aggiorna l'aggancio; cambio oggetto, occlusione e tracking perso non trascinano l'esploso su un bersaglio sbagliato.
7. Toccando ogni parte realmente disegnata si apre la spiegazione corrispondente; nessuna lista di icone presentata come scomposizione dell'oggetto.
8. Chi rifiuta il contributo puo' usare l'analisi personale senza pubblicare dati. Contesti privati sono isolati fra utenti.
9. Versioni ritirate vengono escluse da risoluzione e cache; revisioni hardware incompatibili non sono fuse.
10. Misurare latenza p50/p95 di riconoscimento, risoluzione, primo rendering e generazione; stabilita' del tracking, costo per nuova versione accettata e tasso di riuso. Nessun obiettivo numerico e' dichiarato raggiunto senza misure.

## Misura della crescita

La metrica principale e' la quota di richieste reali servite correttamente da modelli gia' disponibili, separando corrispondenze esatte e schemi di famiglia. Aggiungere il tasso di errore/ritiro e la copertura delle famiglie. Un milione di copie dello stesso telecomando non e' un milione di oggetti coperti.

La copertura della maggior parte degli oggetti quotidiani e' un obiettivo di lungo periodo, non una scadenza garantita: dipende da uso, diversita' delle richieste, qualita', disponibilita' di fonti e budget.

## Sequenza di realizzazione

Prima tranche: contratto dati/versioni + storage + piccolo seed con vere parti separabili + test di riuso dopo riavvio.
Seconda tranche: video continuo + tracking + renderer HUD + selezione, partendo da un telecomando e una penna in prove reali.
Terza tranche: generazione dei mancanti + validazione + contributi autorizzati + pubblicazione automatica delle versioni ammissibili + riuso fra sessioni e utenti.
Successivamente: espansione seed, varianti, piu' fonti, miglioramento asset e misure di copertura. Nessun deploy produzione implicito in questa specifica.

## Riferimenti tecnici consultati

- Khronos glTF: https://www.khronos.org/gltf/ — scene, nodi, mesh e animazioni; non un motore di ricostruzione.
- Khronos animation tutorial: https://github.khronos.org/glTF-Tutorials/gltfTutorial/gltfTutorial_006_SimpleAnimation.html
- Google Gemini image understanding: https://ai.google.dev/gemini-api/docs/image-understanding — rilevamento e segmentazione; non prova dell'interno di un oggetto.
- PartCrafter, articolo originale: https://arxiv.org/abs/2506.05573 e pagina degli autori https://wgsxm.github.io/projects/partcrafter/ — dimostra generazione di mesh distinte da immagini, non universalita', esattezza hardware o tempi live garantiti per ORA. Eventuale integrazione da valutare e collaudare, non gia' effettuata.
