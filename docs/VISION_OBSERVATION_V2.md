# ORA Vision — osservazione v2, seconda segnalazione del cestino

12 ottobre 2026. Base: `389f38ab21f5db61eeb5464e6e65df5c63f4a977`.
Stato iniziale: correzione implementata, CI e rilascio da verificare nella PR.

## Evidenze raccolte

L'utente ha segnalato nuovamente una foto leggibile con il messaggio «Non distinguo bene un oggetto» dopo #214. Le tracce del backend pubblicato, nella finestra 08:00–08:03 UTC, mostrano richieste vision sia 503 sia 200. Una richiesta delle 08:01:48 UTC ha tentato due volte `gemini-2.5-flash` con HTTP 404, poi `gemini-flash-lite-latest` con HTTP 402 e infine HTTP 200 su un'altra chiave. Questi stati non dimostrano quale testo abbia restituito l'AI; il contenuto della risposta non è disponibile nelle tracce. Nessuna immagine, credenziale, IP o identificativo personale viene riportato qui.

Nel codice precedente, due timeout di riconoscimento diventavano `None`, indistinguibile da un giudizio effettivo di immagine poco chiara. Inoltre, coordinate normalizzate 0..1 venivano nuovamente divise per 1000 e potevano invalidare un'identità già riconosciuta. Sono difetti verificabili del codice, non una prova che ciascuno sia stato la causa esclusiva del caso mostrato.

## Modifiche

### Provider e osservazione

- Trasporto Gemini isolato in `vision_provider.py`, con schema JSON esplicito per l'osservazione. La chiave di famiglia rimane aperta, non limitata ai nomi dei 75 seed.
- Alias predefiniti `gemini-flash-latest` e `gemini-flash-lite-latest`; `ORA_VISION_MODELS` resta configurabile. Un alias configurato non equivale a disponibilità o credito garantiti.
- Errori HTTP, quote, timeout, JSON incompleto e terminazione per limite token sono distinti dal mancato riconoscimento. Non si registrano foto, prompt, testo libero o chiavi nei log.
- Tentativi e tempo per fase restano limitati. I percorsi temporaneamente non disponibili ricevono un breve periodo di esclusione; si preferisce un percorso già riuscito.
- Il primo riconoscimento non riceve più una lunga lista di oggetti tra cui scegliere. Si osserva prima la famiglia generica, quindi si applicano alias e catalogo.
- Localizzazione distinta dall'identità: coordinate 0..1 e 0..1000 ammesse; assenza del riquadro non annulla una famiglia riconosciuta. In quel caso il modello compare al centro, senza simulare un aggancio preciso. Coordinate non finite o malformate non sono accettate.
- «Oggetto incerto» richiede due osservazioni realmente negative. Un timeout non viene chiamato foto poco chiara.

### Recupero nell'interfaccia

Dopo vera incertezza compare un nome opzionale, da confrontare con un nuovo fotogramma. Il nome non forza l'identità, non autorizza oggetti rischiosi e non va nel catalogo condiviso. La generazione riceve soltanto la famiglia generica risultante. Gli errori di servizio mostrano il motivo invece di chiedere inutilmente di avvicinarsi. Anche la foto caricata può essere riprovata o sostituita senza dover riaprire la pagina.

Il percorso riuscito resta automatico, con generazione e riuso condiviso per una famiglia assente. Non viene aggiunto un seed del cestino e non si trasforma una risposta negativa in un modello finto. Restano schema fissato, × sulla stessa fotocamera, flash, zoom e percorsi esistenti. Nessuna dipendenza runtime, modifica alle chiavi o migrazione del database.

## Prove richieste

Test del vero formato HTTP/JSON con MockTransport, non solo uno stub che restituisce l'identificazione già corretta; errori 402/429/404/503, timeout, output troncato, selezione del percorso, privacy dei log, coordinate e riquadro mancante. Test con Mongo temporaneo del percorso nome+foto → riconoscimento → famiglia nuova → generazione → salvataggio condiviso → riuso da altro utente. Il testo libero e la foto non devono essere persistiti.

Test browser dell'app esportata: recupero con nome dopo risposta negativa e immagine fresca; errore di servizio leggibile senza suggerire una foto sbagliata; controlli preesistenti di camera/catalogo/zoom ancora attivi.

Le risposte dei provider nei test sono simulate per provare i contratti e i casi di errore. NON è stato riprodotto end-to-end il riconoscimento della fotografia privata dell'utente: il runtime non ha accesso di rete per inoltrarla e non è stata pubblicata su GitHub o host pubblici. Non dichiarare un collaudo della fotocamera fisica iPhone o una garanzia sul caso reale basandosi sui test CI. Stato dei test, merge e deploy vengono registrati separatamente nella PR.

## Limiti mantenuti

La generazione resta una ricetta indicativa della famiglia, non una ricostruzione fedele del singolo esemplare né una verifica delle parti nascoste. I controlli geometrici non certificano il contenuto tecnico. Le quote attuali restano. I fallimenti nella fase di generazione mantengono il messaggio di ricostruzione non disponibile; questa patch distingue soprattutto gli errori che prima erano presentati come mancato riconoscimento della foto.

Riferimenti del contratto provider: https://ai.google.dev/gemini-api/docs/structured-output e https://ai.google.dev/gemini-api/docs/image-understanding .
