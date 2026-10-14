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
- I controlli accessibili **Vista studio/Sulla foto · indicativo** e **−/＋** permettono di scegliere tra ingrandimento educativo e posizione 2D approssimativa. I pezzi anatomici reali possono essere selezionati, isolati, ingranditi e spiegati senza ricomporre l'intero distretto; l'esploso volumetrico mantiene il paginatore di 14 pezzi.
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

## Affinamento successivo — 14 ottobre 2026

- Camera per oggetti: **nessun prefetch anticipato dell'atlante BodyParts3D**. I file pubblici vengono richiesti soltanto dopo il riconoscimento di una regione anatomica. Rimangono le normali chiamate AI di classificazione e gli schemi salvati.
- Eliminati gli ultimi quattro angoli fluorescenti sovrapposti alla fotocamera in attesa del riconoscimento.
- Nella spiegazione del pezzo ingrandito sono disponibili comandi **Precedente / Successivo**. La navigazione continua a mostrare una sola struttura in primo piano senza costringere l'utente a toccare pezzetti minuscoli sullo schermo. Comandi accessibili tramite mouse/touch e con etichette screen-reader.
- Nell'atlante le pagine dei componenti esplosi mostrano **8 mesh su smartphone, 10 su tablet/schermi intermedi e 12 su desktop**: stessi ID BodyParts3D, nessuna geometria inventata. Il numero di pezzi visibili cambia con la larghezza reale del visualizzatore.
- La fotocamera viene mantenuta solo per il riconoscimento; l'atlante anatomico educativo e la vista oggetto restano separati dallo SCAN rimosso.
- Gate: test UI desktop/mobile/WebKit, navigazione tra pezzi ingranditi, nessuna richiesta a `/bodyparts3d/` durante una scansione di oggetto, build originale dell'atlante e regressioni su 160 modelli.
