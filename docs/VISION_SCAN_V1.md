# ORA Vision — Contorno reale V1 e aggancio alla scomposizione

## Contratto di prodotto

Inquadrare un oggetto oppure una parte riconoscibile del corpo. Dopo che il modello di riconoscimento ha identificato la regione e il suo rettangolo 2D, ORA **tenta** una segmentazione rapida sul fotogramma già acquisito:

1. Legge il colore dei pixel **all'interno** e **all'esterno** del rettangolo stimato, senza altri invii all'AI.
2. Se contrasto, estensione della componente, continuità, distanza dallo sfondo e bordi sono accettabili, estrae il perimetro della componente connessa dai pixel reali. Disegna un bordo azzurro con animazione SCAN e label "contorno rilevato".
3. Se i pixel non permettono un perimetro affidabile (parete e mano con lo stesso colore, oggetto policromo, fotografia complessa, ginocchio senza contorno autonomo, forma fuori inquadratura), **nessuna sagoma preconfezionata viene inventata**: ORA usa soltanto un riquadro di aggancio "area stimata / aggancio indicativo".
4. Il contorno selezionato fornisce una bbox **più precisa** e un asse principale indicativo. L'oggetto 3D illustrativo comincia dentro quella bbox, con rotazione bidimensionale approssimata; i pezzi si separano verso lo spazio di studio.
5. L'anatomia rimane **esclusivamente BodyParts3D**, senza ritorno al vecchio omino. La mesh di riferimento viene posizionata sulla bbox della silhouette rilevata, ma **non è deformata per simulare organi interni personali**.
6. Il risultato rimane fissato dopo l'acquisizione. Non promettiamo di inseguire il movimento della camera né di ricostruire profondità, interni reali, 6DoF o occlusioni.

## Vincoli tecnici e privacy

- Primo algoritmo deliberatamente conservativo, locale al browser, su RGBA campionato e ridotto (max dimensione 192). Nessun pacchetto AI esterno, download di modelli o CPU continua sui fotogrammi.
- Il rettangolo originario proviene dall'AI già collegata a ORA, la segmentazione **non prova** di conoscere il nome dell'oggetto; usa i pixel per il contorno.
- Il frame locale è transitorio e non viene salvato nel catalogo condiviso, nella memoria personale né inviato nuovamente. L'API di riconoscimento esistente continua a ricevere la sola immagine necessaria alla classificazione, come prima.
- Su stream video una risposta del riconoscitore può essere obsoleta: si usa la validazione del tracker esistente sul frame attuale. Senza riscontro si evita la falsa sagoma e si mantiene il modello didattico indipendente.
- CSS ed SVG della scansione hanno `pointer-events:none`: chiusura, zoom e scelta dei pezzi rimangono cliccabili.

## Limiti e successivi passi

Questa V1 **non è un segmentatore universale** (es. Segment Anything) e non produce bordi corretti su qualsiasi fotografia. È pensata per primi test su **mano, volto con sfondo chiaro**, oggetti comuni ben contrastati e acquisizione da foto/video. Una V2 con modello di segmentazione vero e tracking necessita di benchmark CPU, memoria, accuratezza e consenso alla fotocamera su telefoni reali.

## Prove richieste prima della distribuzione

- Test geometrici su silhouette sintetiche non rettangolari, fondali piatti o caotici, ricalcolo cover e rinuncia ai falsi positivi.
- Browser Playwright: su persona si usa soltanto BodyParts3D e la maschera da pixel non genera `AnatomyVolume`; su oggetti sono disponibili la scomposizione e il contorno; sfondo uniforme = fallback onesto.
- Build Expo web e typecheck. Deploy Railway del commit esatto, poi controllo con un vero telefono (non sostituibile da fixture).

## SCAN V2 — profilo tecnico cinematografico (13 ottobre 2026)

- La geometria proviene **sempre dai pixel reali** del frame già riconosciuto. Campionamento locale massimo 288px sul lato lungo, pulizia conservativa del rumore di un pixel e semplificazione Ramer–Douglas–Peucker in funzione delle curvature, per evitare il tracciato seghettato senza sostituirlo con un ovale inventato.
- Overlay futuristico azzurro formato da un profilo luminoso con **passata di scansione una tantum**, texture a griglia ritagliata dentro la sagoma autentica, nove nodi distribuiti lungo il perimetro reale (solo elementi grafici, non landmark anatomici), reticolo, angoli e piccolo HUD. Nessun valore numerico di profondità, misure o precisione fittizia.
- Il modello schematico degli oggetti e il visualizzatore reale BodyParts3D entrano con una rapida transizione ottica dopo il bordo. Fotocamera e immagine personale non vengono mai nascoste.
- Se l'estrazione del contorno fallisce, resta un indicatore semplice e **esplicitamente stimato**, non una silhouette decorativa presentata come rilevamento. Non viene riabilitato il vecchio modello umano.
- Gli elementi HUD non intercettano tocchi, hanno un'entrata animata che termina e rispettano le preferenze **riduci movimento**. Il video live non viene analizzato continuamente dal nuovo motore e non vengono inviati fotogrammi a servizi aggiuntivi.
- Questo è un miglioramento sostanziale di **pulizia geometrica e qualità dell'interfaccia**; non realizza ricostruzione 3D accurata, profondità o tracking AR alla qualità del cinema. La capacità di isolare soggetti su sfondi complessi rimane limitata senza un segmentatore dedicato.
