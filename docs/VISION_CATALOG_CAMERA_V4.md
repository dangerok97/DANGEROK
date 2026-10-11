# Vision — catalogo e comandi fotocamera


## Vision catalog 25 + fotocamera (2026-10-12)

Catalogo iniziale ampliato a 25 famiglie / 124 gruppi separabili. Nuovi seed in
`backend/vision_seed_library.py`; nomi canonici e sinonimi condivisi con il
riconoscimento. Ricerca per testo e categoria. Modelli illustrativi, non interni
verificati. I 20 nuovi modelli non ricevono un percorso didattico inventato.
Le cinque famiglie precedenti mantengono il proprio percorso.

Flash/torcia tramite getCapabilities/applyConstraints/getSettings della traccia.
Indicatore acceso solo dopo conferma; indisponibilità esplicita; rilascio della
traccia e richiesta di spegnimento all'uscita. Zoom FOTOCAMERA digitale 1–3x
indipendente dallo zoom 3D: stesso ritaglio per preview, fotogramma AI e
conferma della posizione. Zoom durante riconoscimento invalida risposte vecchie;
zoom mentre si esplora non riavvia l'AI. Nessuna registrazione video.

Installazione seed idempotente: aggiunge versioni e promuove tramite confronto
della versione solo precedenti modelli generati pubblici. Mantiene versioni
vecchie, voci private e modelli ritirati. Nessuna nuova dipendenza runtime.
Test aggiunti per 25 famiglie, sinonimi, riuso, migrazione non distruttiva, flash
supportato/non supportato/ignorato, crop dei pixel e indipendenza dei due zoom.
I dispositivi nei test browser sono simulati; il flash fisico su iPhone deve
ancora essere verificato. Non dichiarare supporto del flash universale.

Riferimenti API: https://www.w3.org/TR/image-capture/ e
https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getCapabilities
Lo zoom qui è digitale, non un comando hardware o zoom ottico. Le sorgenti
generali per i seed sono elencate nel modulo; nessun CAD o immagine è copiato.
