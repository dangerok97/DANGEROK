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
