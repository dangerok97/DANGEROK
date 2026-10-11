# ORA Vision — primo risultato pubblicato e verificato

Data: 11 ottobre 2026. Stato: beta operativa su ORA Web, non AR nativa completa.

## Rilascio

PR #201 integrata in `staging/cloud`; codice pubblicato `c9e56ea0da17233535a35dcfa3366e5cd9520e13`.
Frontend: https://ora-web-production-fb67.up.railway.app/vision-xray
Ingresso dalla conversazione: `+` -> `Visione live` -> `Apri fotocamera`.
Backend: https://ora-backend-production-aa56.up.railway.app

Verificati con Railway i due deployment allo stato terminale SUCCESS:
- backend: `a8af4771-e7f6-4627-9b37-b25d685307cd`, aggiornato 2026-10-11T16:01:14.279Z;
- web: `2ebc832f-7fe6-4733-b01c-a2aa58e8f5e8`, aggiornato 2026-10-11T16:02:44.156Z.
Entrambi riportano il commit di rilascio. I servizi continuano a seguire `staging/cloud`; non sono bloccati a una vecchia versione. Nessuna modifica alle funzioni finanziarie, calendario o autonomia in questo intervento.

## Risultato implementato

Video della fotocamera continuo, riconoscimento AI su fotogrammi, schema esploso sovrapposto con geometrie procedurali tridimensionali proiettate su canvas, contorni azzurri, componente selezionato ambra. Selezione direttamente sulle forme oppure tramite etichette, spiegazioni, rotazione manuale e ricomposizione.

Il catalogo MongoDB salva modelli e versioni: non e' una cache solo in RAM. Cinque famiglie iniziali, con componenti principali tipici:
- telecomando IR: 8 parti;
- penna a scatto: 5;
- bottiglia con tappo: 3;
- mouse ottico: 5;
- torcia: 6.

Per una famiglia assente, un generatore AI produce una ricetta dichiarativa limitata a forme supportate; schema, dimensioni, identificatori e trasformazioni sono validati prima del salvataggio. Tutte le versioni rimangono `illustrative` / `family`. Una forma 3D valida non certifica la correttezza fisica dell'interno.

Nuove ricostruzioni private per default. L'opzione di contributo consente il catalogo condiviso. Il generatore riceve soltanto una chiave di famiglia generica, non fotografie, seriali, identita' dell'utente o contesto personale. Fotografie non persistite; video non registrato. Riconoscimento invia fotogrammi all'AI durante l'uso autorizzato. Quota delle richieste, limiti di generazione e lease Mongo impediscono lavoro illimitato o duplicato.

## Test dedicati prima della pubblicazione

Workflow `Vision catalog and live camera`: https://github.com/dangerok97/DANGEROK/actions/runs/38153313159 — SUCCESS, sul commit `527b894936939950dd35034175a583dc6c58d519`.
Evidenze scaricate e lette:
- 27 test backend superati con MongoDB reale e temporaneo: persistenza anche in un nuovo processo Python, riuso, isolamento fra utenti, condivisione autorizzata, concorrenza, lease, quote, input e rimozione metadati;
- 8 test geometria/tracking superati;
- 38 regressioni del menu allegati superate;
- controllo TypeScript dell'app e export Expo web superati;
- 8 test browser superati, 1 saltato: Chromium desktop/mobile con video di test, WebKit mobile per catalogo e permesso negato. La prova video live WebKit e' esplicitamente saltata, non conteggiata come riuscita.

I test dedicati non equivalgono alla riuscita dell'intera CI del repository. La pipeline generale ha segnalato errori nell'area di presentazione finanziaria, non risolti in questo intervento. Non dichiarare 'tutta la CI verde'.

## Collaudo del sito pubblicato con AI reale

Workflow: https://github.com/dangerok97/DANGEROK/actions/runs/38154226246 — SUCCESS.
Artefatto `vision-deployed-evidence`, ID `11707927037`, contenente `report.json` e screenshot del sito reale. Script di collaudo sul ramo separato `qa/vision-live-check-20261011`; nessun bypass di autenticazione distribuito in produzione.

Usati account sintetici di collaudo registrati tramite API reale; nessun account o dato personale dell'utente. Token e password non inclusi negli artefatti.

Risultati letti dal report:
1. Catalogo senza autenticazione: HTTP 401.
2. Due account distinti recuperano il medesimo seed telecomando, 8 parti, versione `vxv_e2de4b1f9d7138deef4c6eb50f5f`.
3. Riconoscimento reale della fotografia di telecomando: HTTP 200, famiglia `remote_control`, `cache_hit=true`, `generation_used=false`, 1,73 secondi nell'ultima esecuzione.
4. Frontend realmente pubblicato: 8 parti disegnate, scheda elettronica selezionata e spiegata, video ancora attivo; il tempo video avanza di 0,8 secondi durante la prova. Il comando Spegni termina tutte le tracce.
5. Pinzatrice inizialmente assente: AI reale genera una ricetta a 5 parti e la salva privatamente, `cache_hit=false`, `generation_used=true`, 6,18 secondi.
6. Nuovo login e nuova scansione della pinzatrice: `cache_hit=true`, `generation_used=false`, stessa versione `vxv_4e4040b72c679f6eca1ce6304bb7`, 1,58 secondi.
7. Un altro account non puo' leggere la pinzatrice privata: HTTP 404.

I tempi sono osservazioni di una singola esecuzione, NON una promessa di latenza per qualunque oggetto, rete o telefono. Il test della pinzatrice dimostra generazione, validazione strutturale, persistenza e riuso; non e' una certificazione dell'esattezza delle sue parti interne o della resa artistica.

Il test browser utilizza una fotografia pubblica riprodotta in un MediaStream sintetico; backend, autenticazione e provider AI NON sono simulati. E' prova dell'applicazione sul sito pubblicato e del ciclo video/rendering, NON di una fotocamera fisica iPhone, del comportamento del sensore o della precisione AR in movimento.

## Screenshot ed attribuzione del materiale di test

`ora-vision-deployed-mobile.png` e `ora-vision-deployed-desktop.png` sono screenshot della schermata distribuita, non concept generati. Lo screenshot desktop e' l'anteprima catalogo, indicata come tale.

Foto di telecomando: Webwires, pubblico dominio, https://commons.wikimedia.org/wiki/File:First_Generation_Remote_Control.JPG
Foto di pinzatrice: Juseppi, pubblico dominio, https://commons.wikimedia.org/wiki/File:StaplerKM.jpg
I download pubblici di test hanno usato un cache/proxy perche' l'origine negava richieste dal runner. Nessuna fotografia privata dell'app viene inviata a tale proxy.

## Limiti aperti e prossimo lavoro

- Non e' lo smontaggio fisico dell'oggetto: il modello virtuale viene sovrapposto al video, non rimuove l'oggetto dalla scena.
- Tracking locale 2D iniziale con controllo di perdita; non pose 6DoF, orientamento esatto, profondita' o ricostruzione AR del singolo esemplare. Il modello puo' avere orientamento/proporzioni diversi dall'oggetto. Il telefono reale deve ancora essere collaudato.
- Stile wireframe funzionante ma molto piu' semplice del riferimento cinematografico approvato. Le geometrie iniziali sono schematiche.
- App nativa: fotocamera non ancora implementata, solo passaggio esplicito alla versione web.
- Generazione limitata a oggetti quotidiani appropriati e alle primitive supportate; non universale. Nessuna marca/revisione verificata. Nessun catalogo di 30-50 famiglie gia' pronto.
- Condivisione e isolamento collaudati con Mongo reale nei test; il collaudo AI di produzione ha deliberatamente creato solo una versione privata per non popolare il catalogo comune con oggetti di QA.
- Migliorare matching di varianti, controlli semantici e revisione, forme riutilizzabili piu' ricche, tracking/orientamento, prestazioni sul dispositivo, amministrazione del ciclo di versione e copertura.

Questo documento aggiorna lo stato di rilascio rispetto alla precedente specifica `VISION_XRAY_SHARED_CATALOG.md`: il primo percorso e' ora operativo e collaudato entro i limiti descritti, non soltanto pianificato.
