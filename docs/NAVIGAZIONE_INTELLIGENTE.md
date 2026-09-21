# Navigazione intelligente — censimento, disegno, e perché oggi è bloccata

**Stato: `INTELLIGENT NAVIGATION REAL DATA — BLOCKED BY ROUTING PROVIDER`**
Aggiornato: 21 settembre 2026 (V3.21.3a)

> Questo documento esiste perché il comportamento attuale — «Non posso
> confrontare i tempi di percorrenza» più i link alle app di mappe — è un
> ripiego accettabile e **non** il traguardo. Qui c'è cosa esiste già, cosa
> manca, e che cosa serve esattamente per accenderlo.

---

## 1 · Che cosa esiste già, davvero

| Pezzo | Dove | Che cosa fa oggi |
|---|---|---|
| Capacità `open_navigation` | `backend/places/caps.py` | Risolve il luogo, prepara i link alle app di mappe, e — se ci sono tempi — costruisce il confronto fra i modi. |
| Confronto fra i modi | `places/caps.py::_how_to_get_there` | Per auto / mezzi / bici / a piedi chiede al provider durata e distanza, e segna quale tiene conto del traffico. Consiglia il più veloce. |
| Consiglio di partenza | `places/caps.py::_when_to_leave` | Prende il **primo impegno di oggi** dal riepilogo giornaliero e calcola l'orario di partenza: `inizio − durata − 10 minuti di margine`. Frase: «Ti consiglio di partire entro le 08:12 per arrivare con un po' di margine a {impegno} delle 08:45». |
| Adattatore del routing | `backend/places/routing.py` | Un'unica porta: `get_route(origin, destination, travel_mode)`. Modi: `drive`, `walk`, `bicycle`, `transit`. |
| Dichiarazione di capacità | `places/routing.py::capabilities()` | Dice se c'è un provider, quale, e **se quel provider conosce il traffico vero** (`live_traffic` per `google_routes` e `here`). |
| Motivo dell'assenza | `places/caps.py::_routing_note` | Porta in superficie `why_unavailable` invece di far sparire la funzione. |
| Disegno in chat | `frontend/src/components/ora/OraJourney.tsx` | «Le migliori opzioni per te»: una colonna per modo, durata grande, badge «Consigliato», pallino «Tiene conto del traffico», e «Avvia navigazione». Senza tempi, il modulo **non** compare: al suo posto una riga che dice perché. |
| Luoghi e presenza | `backend/places/` | Luoghi salvati, coordinate, `entered` / `exited` / `returned`. |

**La regola che regge tutto** (`places/routing.py`, in testa al file): *un tragitto
osservato non è un ETA*. «Di solito ci metti mezz'ora» è un fatto sul passato di
una persona; «adesso ce ne vogliono 37 minuti» è un fatto su una strada in
questo momento, e nessuna riga di questo repository può saperlo senza chiedere a
un servizio di routing. Per questo, senza provider, **non si risponde con lo
storico travestito da traffico**.

---

## 2 · Perché oggi è bloccata

`ROUTING_PROVIDER` e `ROUTING_API_KEY` non sono configurate in questo ambiente.
Quindi `capabilities()` risponde `available: false` con
`nessun servizio di routing configurato`, `_how_to_get_there` torna una lista
vuota, e la chat mostra la riga onesta al posto dei numeri.

**Non è un difetto del codice**: è una dipendenza esterna assente. Il codice che
usa quei dati esiste, è collegato, ed è coperto dalle prove. Manca la fonte.

Non attivo un servizio a pagamento senza autorizzazione — è una delle tue
condizioni, e vale anche per le prove.

---

## 3 · Il disegno iOS-first (quando si accende)

L'obiettivo non è un link: è **la risposta**.

> Auto: 22 min · Arrivo: 08:47 · Ti consiglio di partire entro le 08:12.

### 3.1 Che cosa deve dire una risposta completa

1. **Destinazione riconosciuta** — «Ufficio», non un indirizzo grezzo.
2. **Tempo per modo**, con il traffico dichiarato quando c'è.
3. **Orario di arrivo**, non solo la durata: è quello che una persona confronta
   con l'ora dell'appuntamento.
4. **Alternative**, ordinate, con la differenza («i mezzi ci mettono 9 minuti in
   più, ma non devi parcheggiare»).
5. **Quando partire**, legato all'impegno vero del calendario.
6. **Che cosa fare adesso**: «Avvia navigazione» apre l'app scelta.

### 3.2 Su iPhone, in ordine di preferenza

| Via | Che cosa dà | Costo | Note |
|---|---|---|---|
| **MapKit / `MKDirections`** (app nativa) | Durata, distanza, ETA con traffico per auto; percorsi a piedi; mezzi come handoff a Mappe | **Nessuno** dentro un'app iOS firmata | È la strada giusta per l'app iOS: niente chiave server, niente fatturazione a chiamata. Richiede che la richiesta parta dal dispositivo. |
| Apple Maps Server API | Le stesse risposte, lato server | Quota gratuita generosa, poi a pagamento | Serve una chiave del team Apple Developer. |
| Google Routes API | ETA con traffico, mezzi molto buoni in Italia | A consumo | `ROUTING_PROVIDER=google_routes`. |
| HERE Routing | ETA con traffico | A consumo | `ROUTING_PROVIDER=here`. |

**La scelta consigliata**: MapKit sul telefono. La navigazione è una domanda che
si fa quando si sta per uscire, e il telefono è già lì: chiedere al dispositivo
evita una chiave server, una fattura, e un giro di rete in più.

### 3.3 Che cosa serve all'integrazione iOS, in concreto

1. Un modulo nativo che esponga `MKDirections` a React Native, con una funzione
   sola: `route(origin, destination, mode) → {duration_seconds, distance_meters,
   reflects_current_traffic}`. La stessa forma che `places/routing.py` già usa,
   così nulla cambia sopra.
2. Un ramo nell'adattatore: quando la richiesta arriva dal telefono, i tempi
   li chiede il telefono; quando arriva dal web, serve un provider server.
3. `NSLocationWhenInUseUsageDescription` nel `Info.plist` e il permesso chiesto
   nel momento in cui serve, non all'avvio.
4. Il resto — confronto, consiglio di partenza, disegno in chat — **è già
   scritto e collegato**: riceve i tempi e funziona.

### 3.4 Che cosa non va fatto

- Nessuna stima da distanza in linea d'aria: un numero plausibile è peggio di
  nessun numero, perché qualcuno ci esce di casa.
- Nessun ETA dallo storico presentato come traffico.
- Nessun servizio a pagamento acceso senza il tuo via libera.

---

## 4 · Come si verifica quando si accende

Il gate resta quello del V3.21.3: *«Portami a lavoro»* deve produrre una
risposta con **auto / mezzi / bici a confronto**, il consiglio del più veloce, e
la frase «Ti consiglio di partire entro le …» costruita sul primo impegno vero
del calendario. Finché una di queste tre cose manca, lo stato resta
**BLOCKED**, e la chat continua a dire perché invece di inventare.
