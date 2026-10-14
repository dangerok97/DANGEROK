# ORA Vision — Studio 3D senza scanner

Decisione del prodotto (13 ottobre 2026): nessun bordo SCAN, griglia pixel, fascio luminoso, contorno ricostruito o parsing di immagini aggiuntivo per la sovrimpressione.

## Percorso oggetti

- Il riconoscimento remoto esistente cerca la famiglia di oggetti, eventualmente restituisce un rettangolo 2D indicativo. Non viene più eseguita la segmentazione locale del frame.
- Lo schema 3D dell'oggetto si apre automaticamente e si scompone nello spazio di studio.
- La selezione di un componente lo **ingrandisce fino a ~72% dell'area utile**, con il resto dello schema attenuato e ancora navigabile. Restano rotazione, zoom, vista d'insieme, spiegazione di ciascun pezzo, pulsante X e la foto/video originale.
- La forma e le parti interne di un oggetto sono una **ricostruzione didattica tipica**, non un esame dei componenti effettivamente presenti nell'esemplare inquadrato.

## Percorso anatomia

- Corpo, volto, mano, braccio, avambraccio, ginocchio, piede e altre zone sono riconosciute e aprono **solo il riferimento BodyParts3D 4.0 verificato** (2.234 mesh originali).
- L'apertura privilegia una **vista studio ingrandita**, che inquadra i mesh nel campo tra i comandi superiori e il cursore inferiore. **Non simula un allineamento esatto** alla mano ripresa dalla fotocamera.
- I controlli accessibili **Vista studio/Sulla foto · indicativo** e **−/＋** permettono di scegliere tra ingrandimento educativo e posizione 2D approssimativa. I pezzi anatomici reali possono essere selezionati, isolati, ingranditi e spiegati senza ricomporre l'intero distretto; l'esploso volumetrico usa pagine responsive di 8, 10 o 12 mesh alla volta.
- Il selettore delle parti e il cursore Scomponi restano raggiungibili. L'avviso di caricamento si sposta sopra, lontano dal cursore.
- Non sono rappresentati organi, ossa o strutture personali dedotte dalla sola fotocamera. Il riferimento è anatomia educativa, non radiografia e non diagnosi.

## Prestazioni

- Rimossi **pixelContour.ts, ScanOutline.web.tsx, scanCinematicStyle.ts**, i rispettivi test scanner e il codice frontend che campionava un secondo frame e tracciava una maschera.
- Nessun nuovo modello, servizio esterno o libreria è necessario: riutilizza il catalogo e l'atlante BodyParts3D già pubblicati.
- La fotocamera acquisisce soltanto per il riconoscimento e si ferma una volta fissato il modello, come prima. Non salva le foto dell'utente nel catalogo.
- Viewport responsive e rispetto di riduci movimento.

## Gate

- TypeScript + test geometria su 160 famiglie, incluso component focus senza clipping.
- Playwright desktop/mobile/WebKit su riconoscimento umano e oggetti **senza overlay SCAN**, modello accessibile, cursori e X funzionanti.
- Build di BodyParts3D verificata e staging Railway sul commit corretto. Il collaudo fisico mobile resta separato e non è certificato dai test browser simulati.


## Aggiornamento: navigazione componenti 14 ottobre 2026

- Nell'esploso degli oggetti compare **Studia i pezzi**. Attiva la vista ingrandita del primo componente senza modificare la geometria o la memoria dell'oggetto.
- I pulsanti precedente/successivo nella spiegazione fanno avanzare ordinatamente tra i componenti reali del catalogo, mantenendo le parti selezionabili e lo zoom. Nessun nuovo modello AI o elaborazione immagini.
- Per mano, polso, avambraccio, gomito, ginocchio e piede la vista anatomica apre **prima le ossa verificate BodyParts3D**; Muscoli e altri sistemi rimangono disponibili dai comandi esistenti.
- Le strutture anatomiche isolate si aprono con un ingrandimento iniziale del 112% e la vista studio può essere ampliata manualmente fino a 2,5×. I pezzi grandi possono quindi essere analizzati uno alla volta senza ridurre l'intero corpo a un modello minuscolo.
- Il layout riserva più spazio verticale ai mesh e conserva cursori, zoom, X, pannelli e stato chiaro anche su telefono. Rimossi anche i vecchi CSS SCAN rimasti inattivi.

## Affinamenti tecnici, 14 ottobre 2026

La fotocamera di un oggetto comune non scarica più i file anatomici. BodyParts3D viene precaricato solo dopo il riconoscimento positivo di una zona del corpo; sono stati tolti anche i quattro angoli grafici residui in fase di acquisizione.

L'esploso anatomico mostra meno mesh per pagina in base alla larghezza: 8 sotto 650px, 10 sotto 1000px e 12 sui desktop. Selezione di una struttura e pagina precedente vengono mantenute come stato di navigazione.

Per gli arti laterali un filtro sulle denominazioni originali BodyParts3D esclude mesh esplicitamente appartenenti al lato opposto, anche quando ricadono nello stesso volume 3D. I nomi anatomici FMA frequenti della mano ricevono una traduzione italiana revisionata. La validazione della build verifica separatamente destra/sinistra e un campione di termini italiani.

Questi miglioramenti non introducono nuovi modelli AI, non ricostruiscono l'anatomia personale e non riattivano scanner, HUD o segmentazione.
