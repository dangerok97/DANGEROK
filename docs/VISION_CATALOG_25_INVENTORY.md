# Vision — catalogo iniziale da 25 famiglie

Pacchetto `common-25-v1`, 12 ottobre 2026. Il numero totale nell'app può essere
superiore: il catalogo continua a ricevere nuovi schemi generici validati.
Questa tabella descrive i 25 seed, non una misurazione dei modelli presenti nel
database di produzione di un utente.

| Famiglia illustrativa | Categoria | Gruppi selezionabili |
|---|---|---:|
| Telecomando a infrarossi | Elettronica | 8 |
| Penna a scatto | Scrivania | 5 |
| Bottiglia con tappo | Casa | 3 |
| Mouse ottico | Elettronica | 5 |
| Torcia portatile | Piccoli utensili | 6 |
| Smartphone | Elettronica | 7 |
| Tablet | Elettronica | 6 |
| Computer portatile | Elettronica | 6 |
| Tastiera a membrana | Elettronica | 5 |
| Controller di gioco | Elettronica | 6 |
| Chiavetta USB | Elettronica | 5 |
| Auricolare wireless | Elettronica | 5 |
| Custodia di ricarica auricolari | Elettronica | 5 |
| Matita in legno | Scrivania | 3 |
| Portamine | Scrivania | 5 |
| Penna con cappuccio | Scrivania | 4 |
| Pennarello | Scrivania | 5 |
| Colla stick | Scrivania | 5 |
| Pinzatrice da scrivania | Scrivania | 5 |
| Rotolo di nastro adesivo | Scrivania | 3 |
| Molletta per bucato | Casa | 3 |
| Dispenser di sapone | Casa | 6 |
| Flacone con spruzzatore | Casa | 6 |
| Borraccia termica | Casa | 4 |
| Cacciavite manuale | Piccoli utensili | 3 |

Totale: **124 gruppi principali**. Comprendono anche regioni o strati concettuali,
come la punta di una matita e lo strato adesivo del nastro; non tutti sono parti
fisicamente separabili senza danneggiare l'oggetto. Questo limite è indicato
nelle spiegazioni. La geometria è originale e schematica, non un CAD copiato o
una ricostruzione verificata dell'interno del singolo esemplare.

## Accesso e riuso

Aprire `Catalogo`, cercare un nome o un sinonimo e selezionare una categoria.
Il riconoscimento riceve i nomi canonici disponibili e risolve i sinonimi noti.
Non vengono fuse deliberatamente varianti incompatibili: penna a scatto e con
cappuccio sono due famiglie; una tastiera meccanica non viene dichiarata a
membrana quando la variante è distinguibile.

L'installazione dei seed è idempotente. Le versioni precedenti sono conservate;
una nuova voce curata può sostituire come versione corrente solo una voce
pubblica generata ancora pubblicabile. Le vecchie voci private non diventano
pubbliche e le voci ritirate non vengono riattivate. Gli schemi condivisi non
contengono le fotografie o il contesto privato della scansione.

I percorsi `Mostrami come funziona` restano quelli scritti per i cinque seed
originali. Ai venti nuovi oggetti non viene associato un percorso inventato:
restano disponibili selezione, spiegazione, rotazione, zoom e apertura.

## Flash della fotocamera

Il comando è una **torcia continua**, non un lampo per una fotografia isolata.
Opera sulla traccia video con `getCapabilities`, `applyConstraints` e verifica
`getSettings`. Se il dispositivo/browser non espone il controllo, mostra
`Flash non disponibile`. Non usa schermo bianco o indicatori di successo finti.
Un comando ignorato o fallito non viene presentato come una luce accesa.

La X mantiene la stessa traccia video e quindi non richiede un nuovo permesso;
`Spegni`, uscita e passaggio in secondo piano rilasciano la fotocamera. Il
rilascio richiede anche lo spegnimento della torcia senza attendere che un
comando hardware bloccato si risolva.

## Due zoom distinti

- **Zoom fotocamera digitale 1–3×**: presets 1×, 2×, 3× e cursore. Prima del
  riconoscimento sono disponibili anche gesto a due dita e rotellina. Il
  fotogramma inviato all'AI usa lo stesso ritaglio visibile nella preview.
- **Zoom dello schema 3D**: conserva i suoi comandi e i gesti quando è presente
  una scomposizione. Non modifica il crop della fotocamera.

Mentre lo schema è fissato, il comando dedicato della fotocamera modifica solo
il video sottostante: non rigenera il modello e non fa ripartire l'AI. Durante
il riconoscimento, cambiare zoom invalida la risposta del ritaglio precedente.
Lo zoom digitale non è zoom ottico e non aggiunge dettaglio al sensore.

## Verifica e limiti

Prima integrazione verificata su `55f446569df25766b5a8ca561c9a8a751a43d89f`:
88 test backend/catalogo, 105 test di geometria/gesti/controlli, 43 test browser
passati e 5 prove video WebKit esplicitamente saltate; TypeScript, build web e
CI generale passati. L'ispezione visiva ha evidenziato il selettore nativo di
categoria poco leggibile su WebKit, corretto in `ebff87dfbe8ae6b97f7ed4a11a912361c34d95a2`.
La revisione finale deve essere nuovamente verificata prima della pubblicazione.

I test video/torcia usano una traccia sintetica e capacità hardware simulate;
non dimostrano il funzionamento del flash fisico di un iPhone. La verifica
browser dei pixel prova il ritaglio inviato, non la qualità ottica della camera.
Rilascio e collaudo autenticato in produzione vanno documentati separatamente.

Riferimenti del contratto browser:
- https://www.w3.org/TR/image-capture/
- https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getCapabilities
- https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getSettings
