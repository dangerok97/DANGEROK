# ORA Vision: atlante anatomico approfondito, versione illustrativa

## Obiettivo e limiti

Il riconoscimento di una persona conduce a un atlante anatomico educativo e non alla
ricostruzione anatomica della persona inquadrata. Una fotocamera RGB non misura organi
interni, scheletro, sesso biologico o condizioni di salute. I tracciati della geometria
sono schematici. Non usare l'atlante per diagnosi o procedure cliniche.

## Migliorie

- Sette livelli: cute, muscoli, nervi, circolazione, organi, ossa, riproduzione.
- Ventuno nuove strutture descrittive; otto nuove reti vascolari illustrative.
- Navigazione autonoma tra sette distretti anatomici dopo la prima acquisizione,
  senza una nuova chiamata AI e senza riavvio della fotocamera.
- Ricerca locale di strutture; indicazioni contestuali con etichette di parte.
- Superfici 3D derivano da campionamento di path SVG (M/L/Q/C, campionamento bounded):
  contour-lens per forme chiuse, swept tube per rami nervosi e vascolari aperti,
  ellissoidi solo come fallback e non come certificazione anatomica.
- Separazione con distanze individuali anziché traslazione comune di tutti gli elementi.
- Selezione basata sui segmenti delle strutture sottili, isolamento, strumenti in
  pannello mobile, navigazione a tastiera, pinch a due dita.
- I fotogrammi personali non vengono salvati in un catalogo anatomico.

## Test e criteri di rilascio

- Geometria: curve SVG, contorni chiusi, tubi nervosi, selezione dei tubi e
  differenza di profondità al variare del parametro di separazione.
- Regressione atlante: componenti nominati, filtri delle zone, apparato circolatorio,
  varianti riproduttive esclusivamente su scelta esplicita.
- Browser: fotografia sintetica, instradamento atlas, navigazione senza una
  seconda scansione, ricerca, selezione, isolamento, test di zoom e screenshot.
- TypeScript, Web build, suite Vision, sicurezza backend, CI e regressioni mobile
  prima del merge; Railway con SHA coincidente prima di chiamare la funzione
  distribuita. Il browser harness NON collauda un sensore fisico iPhone.

## Verso modelli anatomici reali

Prossima fase separata: ingestione e ottimizzazione di mesh per singola struttura,
identificatori anatomici con provenienza e attributi di licenza; prova mobile GPU,
LOD/cache, controlli reali di accuratezza mediante fonti specialistiche,
fallback ai modelli illustrativi. Non etichettare le attuali mesh come anatomia
medicalmente validata.

**Fonte candidata (NON integrata in questa PR):** BodyParts3D, Database Center for
Life Science. Licenza corrente ufficiale CC BY 4.0 e attribuzione richiesta:
"BodyParts3D, © The Database Center for Life Science licensed under CC Attribution
4.0 International".
- https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html
- https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html

Per dataset combinati o versioni storiche, verificare la licenza dei singoli asset
perché le versioni storiche e altri atlanti possono usare CC BY-SA o NC. Non
scaricare né distribuire automaticamente modelli terzi privi di verifica.

## Inquadratura delle pagine esplose (13 ottobre 2026)

- Quando la separazione raggiunge il 50%, l'inquadratura segue il perimetro **dei soli componenti effettivamente presenti nella pagina** (massimo 14), includendo gli spostamenti 3D di ciascuna mesh nel tempo. Non rimane centrata sul corpo ricomposto.
- Zoom autonomo dei pezzi esplosi (1×–3×), pulsanti accessibili anche da cellulare e comando **Centra**; il ritorno da un dettaglio conserva pagina e grado di esplosione.
- Le superfici anatomiche conservano contorni tecnici azzurri e le relative fonti BodyParts3D: è una ricostruzione didattica, non un'immagine diagnostica della persona inquadrata.
- Il test di distribuzione vincola la generazione alla vera geometria BodyParts3D, al framing per pagina e ai comandi dedicati; l'uso del sensore fisico resta da collaudare sul dispositivo.
- Cambiando pagina senza muovere il cursore, l'inquadratura viene ricalcolata **dopo** aver aggiornato le trasformazioni delle mesh della nuova pagina; evita la visualizzazione dei pezzi fuori scena.

## Aggancio alla parte riconosciuta e caricamento progressivo (13 ottobre 2026)

- Una foto o il frame live forniscono un **riquadro 2D normalizzato** (x,y,larghezza,altezza). Il viewer ora usa il centro e le dimensioni di quel riquadro per inquadrare le mesh della stessa regione, non più una traslazione orizzontale CSS; dal 50% la scomposizione passa gradualmente verso il centro dell'area studio.
- Una foto con proporzioni diverse dallo schermo è convertita tramite il medesimo calcolo cover degli oggetti, mentre il frame live usa il crop visibile della fotocamera. Dopo un'espansione manuale ad altra regione, l'aggancio originale viene disattivato.
- Il canvas didattico procedurale compare **subito e in posizione**, restando una anteprima dichiarata; i veri modelli BodyParts3D arrivano in streaming senza una schermata modale o una percentuale centrale. La fotocamera resta visibile.
- All'apertura di fotocamera/foto, scaricamento best-effort anticipato di shell, indice, metadati e JS/CSS del riferimento pubblico (nessun frame personale); rispetta risparmio dati/2G. I 15 chunk anatomici vengono prioritizzati usando le mesh della regione attuale; altri chunk continuano per le espansioni successive. Cache 24h per geometry e 30 giorni per asset con hash.
- **Limite dichiarato:** aggancio approssimato bidimensionale, non ricostruzione 3D metrica, né tracking persistente 6DoF né misura di strutture interne da RGB. L'atlante resta generico, didattico e non diagnostico.

- I componenti 3D già decodificati diventano **selezionabili dopo il primo chunk**, senza attendere tutti i 15 file del riferimento. La selezione tramite canvas considera soltanto le mesh effettivamente caricate; l'eventuale catalogo di parti può mostrare parti che devono ancora arrivare. Il caricamento continua in background.

- **Ancoraggio dopo il cambio layout:** il riquadro della foto non viene proiettato una sola volta prima di nascondere i comandi. Conserviamo il riquadro nel crop sorgente e lo riproiettiamo dopo il render, ai ridimensionamenti della stage e al cambio zoom. In live il calcolo passa dall'originale frame e dal crop iniziale al nuovo crop visibile; in foto usa object-fit:cover aggiornato. Evita slittamenti di alcuni punti percentuali fra desktop e telefoni.

## Disattivazione completa del vecchio modello anatomico (13 ottobre 2026)

- Per una persona o parte del corpo riconosciuta, **l'unica geometria anatomica visibile** è il riferimento verificato BodyParts3D. Nessun rendering `AnatomyVolume`, silhouette schematica, organo fittizio o vecchio renderer di fallback.
- Durante il caricamento si vede soltanto la fotocamera e un **rettangolo di aggancio tecnico** con quattro angoli azzurri, non una figura umana, poi i componenti reali compaiono senza schermata percentuale.
- Se la fonte BodyParts3D è indisponibile o non corrisponde alla versione attesa, ORA non sostituisce il modello con figure inventate: mostra un avviso chiaro con pulsante **Riprova modello 3D**, mantenendo attiva la fotocamera e l'uscita X.
- I controlli browser e una nuova regressione statica proibiscono esplicitamente `AnatomyVolume`, `silhouettePath` e `vx-anatomy-shell` nel componente di produzione.
