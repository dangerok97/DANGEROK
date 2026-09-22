## 2026-09-22 — Esito verifiche cloud V3.21.4

Codice `85ca21c`: sei test mirati passati; sul cloud upload/download sintetico riuscito, accesso da secondo utente 404, token dopo logout 401, nuovo login riuscito. Dopo redeploy il token resta revocato. Health DB 200 e capability telefonia pronte (non prova di chiamata reale).

**Storage NON chiuso:** prova dopo redeploy fallita con 410. Volume `7178fc0e-083e-4690-a8c6-889e37995808` creato ma risulta scollegato; due applicazioni del mount tramite connettore non hanno prodotto un mount effettivo (`hasVolume=false`). Non dichiarare i documenti persistenti. Percorso runtime mantenuto temporaneamente `/tmp/ora-documents`; passare a `/data/documents` solo con mount verificato, poi ripetere upload/redeploy/download. Richiesto intervento tramite pannello Railway; nessun documento personale usato nelle prove.

Repository pubblico confermato; tree corrente senza `backend/data` tracciato. Audit completo di cronologia/esposizione, revoca di tutte le sessioni, backup/restore e gate PC spento restano aperti. V3.21.3e chiusa su conferma dell’utente; V3.21.4 resta in corso.

## 2026-09-22 — Cloud Foundation: sessioni e persistenza

Vita V3.21.3e confermata funzionante dall’utente. Audit Railway: documenti su filesystem temporaneo, directory vuota al controllo; volume dedicato `/data/documents` predisposto. Logout ora revoca il singolo bearer tramite digest SHA-256 in Mongo, indice TTL e JWT nuovi con jti univoco; nessuna rotazione o logout globale. Health risponde 503 se Mongo non risponde entro tre secondi. Quattro test mirati passati; verifica live e persistenza dopo redeploy ancora da completare. Nessun file `backend/data` tracciato nel tree corrente; audit storia/pubblicazione repository ancora aperto.

## 2026-09-22 — Roadmap riallineata

Decisione: Cloud Foundation V3.21.4, iPhone reale V3.23, alpha 3–5 persone V4.1; beta privata V11 e pubblica/RC V12. Recovery, privacy e affidabilità essenziali precedono l’alpha; maturità completa in V5/V9/V10. Nessun nuovo engine nel percorso immediato. Google Login confermato, Vita e integrazioni sul profilo reale ancora da verificare. Questa revisione è documentale, non una nuova prova funzionale. Criteri completi in `ROADMAP.md`; priorità derivate in `BACKLOG.md`.

## 2026-09-22 — Cloud sync and device location

Google Calendar and Gmail perform a bounded first read after OAuth and enqueue a durable retry. Continuous polling discovers new sources even for existing owners; partial calendar failures remain retryable. Home refreshes while active. Settings and Weather request actual browser geolocation and save a successful fix; already consented location refreshes while Home is active. Railway requires AMBIENT_RUNTIME=1. Browser denial is explained with recovery instructions. Provider availability and browser permission still govern freshness.

# ORA — Development State

## 2026-09-22 — Ripristino configurazione integrazioni cloud

Railway ora-backend: configurati OAuth Calendar/Gmail con callback HTTPS cloud,
TOKEN_VAULT_BACKEND=fernet (chiave cloud esistente preservata), modalità real,
Tavily/ricerca e fallback supportati Gemini2, Groq, Mistral e OpenAI.
Ripristinati i flag locali di contesto, riepilogo giornaliero e profilo comportamentale.
Non importati percorsi Windows, Mongo/JWT locali, NVIDIA/Cerebras senza adattatore,
o Deepgram nel runtime telefonico gemini_live.

Verifica HTTP autenticata con account sintetico: Calendar provider_ready=true,
nessun requisito mancante; Gmail client e callback configurati. Reverse geocode
cloud di un punto pubblico a Roma restituisce Roma. La posizione del dispositivo
richiede comunque consenso del browser dell'utente sul dominio Railway.

Docker frontend ora accetta EXPO_PUBLIC_MAPS_WEB_KEY prima dell'export Expo.
Il riepilogo di un luogo ottenuto dal dispositivo non lo attribuisce più alla
selezione manuale sulla mappa. TypeScript, export Expo e 10 test configurazione Google passati.
Restano esterni: registrazione dei due callback nella console Google, consenso
utente Calendar/Gmail e chiavi Maps JavaScript/Places/Routes non fornite.
Console Google non accessibile dal browser di questa sessione. Non dichiarare
sync Google o mappe interattive verificate finché questi passi non sono completati.
Nessuna nuova dipendenza o migrazione DB; creato solo account di verifica sintetico.

## 2026-09-22 — V3.21.3e, recupero nel branch cloud

La patch locale di Claude viene integrata in `staging/cloud`. Selezione e
avanzamento sono distinti: `selected` evidenzia l'area; `in_progress` richiede
un questionario attivo. `POST /life-profile/setup/go-to-area` accetta
`start_question` (default false); un `ref` esplicito avvia una domanda precisa.
La sessione conserva `guided_question_active`; il frontend segue questo stato
anche dopo un reload. Un'area completa non propone continua/rimanda.
Il backend calcola la prossima area con motivo esplicito, escludendo quelle
senza domande aperte. I rifiuti storici e guidati sono letti insieme.

Verifica locale: 97 test backend isolati, TypeScript, guardie Vita 3c/3d/3e
ed export Expo web passati. Anche il test Playwright del contratto UI passa
con profilo sintetico e API intercettate (selezione, continua, reload e
aree complete/rifiutate). Suite Vita aggiunte alla CI. Gli screenshot
forniti sono del lavoro locale precedente; verifica finale sul profilo
Railway ancora da confermare. Nessuna nuova dipendenza o migrazione DB.


> **La roadmap canonica sta in `docs/ROADMAP.md`.** Versione corrente,
> prossimo sprint, dipendenze e criteri di uscita si leggono lì. Questo
> documento è il registro tecnico sprint per sprint, il più recente in alto,
> e non ripete la roadmap.
>
> **Versione corrente: V3.15.1a — COMPLETATA · Prossimo: V3.15.2.**

---

## V3.15.1a — REPO HYGIENE — CLOSED

**Due artefatti che non dovevano restare nel repo.**

    UNA PROVA CHE GIRA SU UNA MACCHINA SOLA NON È UNA PROVA.

`test_the_enum_says_out_loud_which_reading_is_the_cheap_one` leggeva le
dichiarazioni degli strumenti dal banco del PoC, che vive fuori dal repo in
una cartella temporanea con dentro un nome utente e un UUID di sessione.
Ovunque tranne che lì saltava con `pytest.skip`. Adesso legge
`telephone.live.THE_SIX` — l'elenco che il runtime manda davvero a Gemini a
ogni chiamata. Niente percorso, niente skip, **nessun file nuovo**, e più
copertura di prima: teneva ferma una copia, adesso tiene ferma l'originale.

    E UN NUMERO VERO IN UNA FIXTURE È UN NUMERO VERO SU GITHUB.

Sette occorrenze del numero personale usato per le prove reali — un commento
in `service.py`, quattro fixture, un'asserzione, una riga di changelog —
sostituite con `393000000000`. Nessuna era un default di produzione:
`_national()` è pura logica di formato e non contiene numeri. Il prefisso 300
non è assegnato a nessun operatore, ma la forma resta valida e attraversa le
stesse tre scritture che il commento descrive.

**Verificato:** zero path utente, zero numeri reali, zero skip dovuti alla
macchina, 240 prove verdi, typecheck frontend pulito.

---

## V3.15.1 — REAL POST-CALL APPLICATION GATE — PASS

**La prova sul vero: 16:00 → 18:00, su Google, per davvero.**

    UNA TELEFONATA RIUSCITA NON ERA ANCORA UN CALENDARIO AGGIORNATO.

Evento vero creato dalla porta canonica e spinto su Google
(`masv27f7ade0067ab9j73v1oa4`, «Dentista test», 16:00–16:45, `Europe/Rome`).
Legame creato prima di comporre il numero. Telefonata reale di 50 secondi,
voce Kore, runtime a missione.

**Il gate ha retto in linea.** Alla disponibilità — «sì, sì, è possibile alle
18:00» — ORA **non ha chiuso**: ha chiesto «mi conferma che l'appuntamento è
stato spostato alle 18:00?». Solo dopo «sì, confermo» ha completato.

**Timeline** (t₀ = risposta umana)

| | Δ t₀ |
|---|---|
| runtime a missione pronto | +3,3 s |
| disponibilità — **nessuna scrittura** | +38,3 s |
| conferma della controparte | +43,3 s |
| `session.close()` → applicazione avviata | +50,4 s |
| Google ha scritto | +51,9 s |
| record `applied` · `PhoneCall.wrote` | +52,5 s |

Applicazione completa in **~2,1 s**, di cui ~1,6 s di andata e ritorno con
Google. Il `completed` del carrier è arrivato **prima** dell'applicazione e non
l'ha innescata: il trigger è il `finally` del socket.

**I nove criteri, tutti verificati** — evento reale alle 16 · conferma alle 18 ·
stesso `google_event_id` alle 18:00–18:45 con durata conservata · nessun
doppione (un solo `confirmed` sul 14/09) · `application_status = applied` ·
`wrote` valorizzato · history coerente · secondo apply senza scritture
(`sync_version` 2 → 2) · `needs_user` che non tocca niente.

**Quattro fonti che concordano:** `CallMissionOutcome`,
`CallMissionApplication`, `PhoneCall.wrote`, Google Calendar.

---

## V3.15 — POST-CALL APPLICATION LAYER V1 — CLOSED

**Da «hanno confermato» a «è spostato», una volta sola.**

    CHI HA PARLATO NON SCRIVE NIENTE NEL MONDO.
    «ALLE 18 ABBIAMO POSTO» NON È «L'HO SPOSTATO ALLE 18».

L'audit aveva trovato il punto: `confirmed_changes` conteneva `new_time:
"18:00"` e **non conteneva quale evento**. La risposta non è cercarlo dopo.

| Pezzo | File | Sa una cosa sola |
|------|------|------|
| `MissionTarget` · `CallMissionBinding` | `telephone/binding.py` | a che cosa è attaccata questa telefonata |
| `CallMissionApplication` | `telephone/application.py` | che cosa è stato fatto nel mondo |
| `adapter_for` | `telephone/domains/__init__.py` | chi sa ricevere un esito |
| adattatore calendario | `telephone/domains/calendar.py` | tradurre e scrivere, o dire perché no |

**L'oggetto si decide prima.** `prepare_a_phone_call` accetta `calendar_ref`:
al momento del preparativo, quando c'è ancora qualcuno a cui chiedere «quale
appuntamento?». Il legame porta *quando* è l'appuntamento — che serve a
parlare — e *quale* è, che non serve e resta sul server. Provato:
`for_the_model()` non contiene l'`entity_id`, come non contiene il numero.

**L'idempotenza non è un `if`.** La chiave `missione|operazione|oggetto` è
l'`_id` del documento. Il record nasce `pending` *prima* della scrittura: un
secondo tentativo non arriva nemmeno all'adattatore.

**Tre controlli prima di toccare qualsiasi cosa** — autorità (chiavi dentro un
insieme chiuso; una telefonata per spostare non cambia l'indirizzo) · identità
(stessa partenza del legame, stessa ora detta dalla controparte) · traduzione
(fuso dell'evento, durata conservata, cambio d'ora attraversato).

**Un quinto stato, `conflict`.** Fallito vuol dire riprova; in conflitto vuol
dire vai a guardare. Due frasi diverse da dire a una persona.

**Se l'applicazione fallisce, la telefonata resta riuscita.** Nessuno riscrive
`metrics.outcome`: la controparte *ha* confermato, ed è vero anche se Google
non ha risposto. Quello che cambia è la frase sulla scheda — «Hanno confermato
lo spostamento alle 18:00, ma non sono riuscita ad aggiornare il calendario».

**Il cancello del consenso**, che la specifica non chiedeva: il sì alla
telefonata e il permesso con cui il calendario è collegato sono due autorità da
due momenti diversi. Ogni altra scrittura in calendario ci passa.

**34 prove**, A–L più la matematica pura della traduzione.

---

## V3.14 — CALL HISTORY V1 — CLOSED

**Il resoconto di una commissione, non una console.**

    QUESTA NON È UNA CONSOLE. È IL RESOCONTO DI UNA COMMISSIONE.

Dall'altra parte non c'è chi ha scritto il runtime: c'è qualcuno che ha chiesto
di spostare un appuntamento e vuole sapere com'è andata.

**Tre insiemi di stati, non uno** — `call_status` (com'è finita la linea),
`mission_status` (com'è finita la missione), `presentation_status` (come si
dice a una persona: `in_corso`, `completata`, `serve_una_decisione`,
`nessuna_risposta`, `occupato`, `segreteria`, `non_riuscita`, `interrotta`).
Si legge **prima la linea, poi la missione**: se non ha risposto nessuno non
c'è nessuna missione da raccontare.

**`history.py` non tocca il database.** Il riassunto nasce dall'esito già
validato dal backend, mai da una lettura a posteriori del calendario.

**Superfici** — elenco (tabella ≥860px, righe impilate sotto), dettaglio,
trascrizione a richiesta («mostra», non «genera»: il testo c'era già, l'audio
non c'è mai stato). Chiamate vive nella sidebar desktop fra ORA e Attività,
`railOnly`: la barra del telefono era piena, e una sesta voce su 375px
tronca la prima etichetta.

**Debito dichiarato** — paginazione sospesa; `segreteria` mai emesso (nessun
segnale affidabile, `machine_detection` non cablato).

---

## V3.13 — REAL CALL HARDENING — CLOSED

**Sei difetti trovati dall'orecchio di una persona, nessuno dai test.**

Otto telefonate reali. Ogni difetto trovato parlando, non provando.

| Difetto | Risposta |
|---|---|
| la voce andava a tratti | cuscino di 200 ms prima di aprire bocca |
| non riagganciava | contratto di commiato con nudge limitati |
| riagganciava dopo una domanda | `CHI FA UNA DOMANDA ASPETTA LA RISPOSTA` |
| silenzio sul primo «pronto» | prewarm delle orecchie, apertura proattiva |
| gate aggirato sulla disponibilità | seconda regola, temporale, nel ledger |
| audio a raffica | barriera a scadenza monotona |

    UN SEGNALE SI PERDE. UN CREDITO SI ACCUMULA.

`asyncio.Event` perdeva 207 battiti su 1.280 in una chiamata vera. Sostituito
con `BeatCredits`: un frame in ingresso è un credito, i crediti si accumulano.
Il metronomo non è nostro, è della linea — misurato 49,1–49,4 frame/s su
chiamate di 47–71 s, `inbound_gap_p50 = 19,8 ms`.

    IL CALCOLO ERA GIUSTO. IL TIMER NO.

`asyncio.sleep(0.020)` su questo host ne dorme 31,2; `asyncio.sleep(0.008)`
ne dorme 0,3. Il timer sbaglia in **entrambe** le direzioni. La barriera
chiede una volta e, se il timer mente, smette di chiederglielo.

**Esiti sul vero** — `hangup_while_human_speaking = 0` su chiamate 5–8 ·
`longest_burst_run = 0` · apertura da 7,7 s a 1,5 s · p50 primo audio 1,4–1,6 s.

**Debito dichiarato** — p90/p95 regrediti sulla chiamata 8 (23,4→29,9 e
26,8→34,1 ms con 112.394 cessioni cooperative); buchi a monte di Gemini fino a
837 ms contro un cuscino di 200; deriva di lingua nella trascrizione d'ingresso.

---

## V3.13 — GEMINI LIVE + VONAGE CALL MISSION RUNTIME — CLOSED

**Un esecutore con una missione sola, accanto a ORA intera.**

    ORA SA TUTTO. CHI TELEFONA SA UNA COSA.
    MINIMA DIVULGAZIONE: SI PORTA LA MISSIONE, NON LA PERSONA.
    NON SONO FRANCESCO. SONO L'ASSISTENTE DI FRANCESCO.

`wss://generativelanguage.googleapis.com/…BidiGenerateContent`, modello
`gemini-3.1-flash-live-preview`, voce **Kore**, uscita a 24 kHz ricampionata a
16 per il filo Vonage.

| Pezzo | File | Sa una cosa sola |
|------|------|------|
| `MissionVoiceSession` | `telephone/live.py` | condurre **questa** missione |
| `CallMissionPacket` | `telephone/mission.py` | che cosa serve per parlare |
| `MissionLedger` | `telephone/mission.py` | a che punto è la trattativa |
| `Introduction` | `telephone/introduction.py` | il contratto dell'apertura |
| `the_voice_for` | `telephone/runtime.py` | **l'unico punto** in cui si sceglie |

**Il packet pesa ~280 token** contro i 18.650 del prompt di ORA. Non contiene
il numero di telefono, e da V3.15 non contiene l'identificativo dell'evento.

**Sei strumenti, non trentanove** — `get_call_context`,
`get_allowed_alternatives`, `request_user_confirmation`, `record_call_fact`,
`complete_mission`, `fail_mission`. **Nessuno tocca un dominio.**

**Il confirmation gate è backend-side.** Due regole, entrambe temporali,
nessuna lettura di frasi: una conferma non può stare nello stesso respiro della
disponibilità, e una missione che cambia il mondo non si chiude al primo turno.
Nessun classificatore LLM, nessun secondo di latenza aggiunto.

**Il contratto di presentazione** verifica di aver consegnato due contenuti
obbligatori — di chi siamo l'assistente, e perché chiamiamo — e riconosce
l'impersonificazione.

**Il classico resta il valore di riposo.** Manca la chiave, manca il modello,
manca la missione: si torna al classico e chi è dall'altra parte non se ne
accorge.

---

## V3.13 — SPRINT 3.2 — REAL-TIME TELEPHONE SPEECH RUNTIME — CLOSED

**La voce che va e quella che torna, dentro la stessa telefonata.**

    VOICE IS NOT A SEPARATE ASSISTANT.
    L'AUDIO È UN FIUME, NON UN ARCHIVIO.
    PRIMA DEL COMMIT È UN'IPOTESI.

Lo Sprint 3.1 aveva portato il filo: pacchetti di voce umana dentro il
backend, e niente che ne restasse. Qui quei pacchetti diventano parole,
attraversano **la stessa ORA** dell'app, e tornano indietro come voce.

**Il giro, per intero**

    telefono → Vonage → WS binario → AudioIngress → StreamingSpeechInput
             → TurnManager (commit semantico) → SameORAAdapter
             → SpeechChunker → StreamingSpeechOutput → PlaybackController
             → WS binario → Vonage → telefono

| Pezzo | File | Sa una cosa sola |
|------|------|------|
| `RealtimeVoiceSession` | `telephone/bridge.py` | tenere insieme il giro |
| `AudioIngress` | `bridge.hear()` | far passare il PCM e dimenticarlo |
| `StreamingSpeechInputProvider` | `telephone/providers.py` | il contratto di chi ascolta |
| `StreamingSpeechOutputProvider` | `telephone/providers.py` | il contratto di chi parla |
| `Listening` · `Speaking` | `telephone/deepgram.py` | l'unico file che nomina un fornitore |
| `TurnManager` | `telephone/turn.py` | di chi è il turno |
| `SameORAAdapter` | `telephone/same_ora.py` | la porta verso `AICoreOrchestrator` |
| `SpeechChunker` | `telephone/chunker.py` | dove si può tagliare una frase |
| `PlaybackController` | `telephone/playback.py` | versare l'audio al ritmo di chi ascolta |
| `BargeInController` | `bridge._barge_in()` | tre gesti, in ordine |
| `VoiceLatencyMetrics` | `turn.Timing` | i numeri, mai le parole |
| `TelephoneCallDossier` | `telephone/dossier.py` | cosa preparare mentre squilla |

**Fornitori e frequenze.** Deepgram per tutti e due i versi, endpoint europeo
`api.eu.deepgram.com`. Ascolto: **Nova-3**, italiano, `linear16` a **16 kHz**,
`interim_results`, `vad_events`, `utterance_end_ms=1000`. Voce: **Aura-2**
italiano, `linear16` a **16 kHz**. È la stessa frequenza del filo Vonage:
**nessun ricampionamento in nessuno dei due versi** — il piano dello Sprint
3.1 ne prevedeva uno perché il vecchio modello voleva 24 kHz, e sceglierne
uno che parla già a 16 lo ha fatto sparire invece di ottimizzarlo.

**I fornitori si aprono all'apertura della linea, non al primo turno.**
Misurato: la stretta di mano costa 336 e 289 ms. Pagarli mentre una persona
aspetta sarebbe stato un decimo del tempo di risposta buttato in un saluto fra
macchine.

### Il commit semantico

    `speech_final` NON È LA FINE DEL TURNO.

Misurato su voce vera: su «Ciao ORA, dimmi che giorno è oggi» il trascrittore
dichiara la frase finita dopo 2,4 secondi su 4,7 — cioè sulla pausa dopo
«Ciao, ORA», mentre la persona sta ancora parlando. Un runtime che risponde lì
interrompe la gente a metà frase, e sembra sordo.

Il commit combina quello che si sa: chi ha cominciato a parlare (VAD), cosa ha
detto finora (definitivi accumulati), dove ha fatto pause (**indizio**), quanto
silenzio è passato (`UtteranceEnd`), quanto ha parlato in tutto, se la frase
sta in piedi da sola, dove eravamo un attimo fa.

    UN TIMER CHE BATTE QUELLO DI CHI ASCOLTA È UN TIMER INUTILE.

Due strade sono state costruite e **tolte**, tutte e due dopo una prova con
voce vera:

1. «1,6 secondi senza eventi → commetti». I definitivi arrivano a gruppi, e
   fra un gruppo e l'altro passano secondi in cui *noi* non sentiamo niente e
   la persona sta parlando benissimo. Ha chiuso il turno su «Ciao, ora».
2. «pausa dichiarata + 800 ms di silenzio + frase che sta in piedi». Il
   trascrittore dichiara il silenzio a 1.000 ms: aspettarne 800 e decidere da
   soli vuol dire arrivare sempre primi, e quindi non chiedergli mai niente.
   Ha chiuso il turno su «Ciao, ORA.» — che *sembra* finita perché il
   trascrittore mette il punto a ogni pezzo.

Resta `UtteranceEnd` — chi guarda i tempi delle parole invece dell'orologio — e
sotto una rete a **4 secondi** che chiede comunque se la frase sta in piedi
(`_stands_on_its_own`: punteggiatura finale, nessuna parola sospesa, almeno
tre parole). La rete è per il guasto, non per il ritmo.

### Nessun audio prima che ORA abbia deciso

Il core non produce testo: produce una **decisione**, e `ora_text` è un campo
dentro quella decisione. Finché non è completa non si sa nemmeno se questo
turno è una risposta — potrebbe essere uno strumento, una richiesta di
autorità, un blocco. Quindi si aspetta la decisione intera e si guarda `mode`:
solo `answer`, `compare`, `finish` e `ask` diventano voce. `tool`, `act`,
`context`, `research` sono passi interni, e un passo interno detto ad alta voce
è ORA che pensa nell'orecchio di qualcuno.

**Niente riempitivi.** Se non c'è niente da dire non si dice niente: inventare
un «un attimo…» sarebbe mettere in bocca a ORA una frase che ORA non ha deciso.

### L'interruzione

    CHI RICOMINCIA A PARLARE NON CHIEDE IL PERMESSO.

Tre gesti, in quest'ordine: `Clear` al fornitore perché smetta di generare, la
coda nostra buttata, e il trasporto avvisato. Il segnale è `SpeechStarted`, non
la prima trascrizione: aspettare le parole vuol dire parlare sopra a qualcuno
per un secondo intero.

**Un limite vero, detto e non nascosto:** sul filo Vonage non esiste un comando
per richiamare indietro l'audio già consegnato. Si smette di mandarne, e quello
che ha già lasciato il server — al massimo un pacchetto, venti millisecondi — la
persona lo sente comunque.

### Mentre squilla

    FRA «SQUILLA» E «PRONTO» NON STA ASPETTANDO NESSUNO.

Sono gli unici secondi gratis della telefonata. Si prepara il fascicolo e si
sveglia la catena dei modelli. **È infrastruttura, non cognizione**: non entra
nella Conversation Engine, non crea messaggi, non crea memoria, non tocca il
Personal Life Model, non attiva strumenti, non consuma autorità, non produce
niente che qualcuno leggerà. Se fallisce, il primo turno costa quello che
sarebbe costato comunque.

### I numeri, misurati sulla pipeline intera

Prova a secco del 13 settembre: Deepgram vero, ORA vera, trasporto vero, finto
solo il filo telefonico.

| Tratto | Turno 1 | Turno 2 | Turno 3 |
|------|------|------|------|
| fine parlato → commit | 1.595 ms | 1.637 ms | 1.600 ms |
| commit → decisione di ORA | 5.886 ms | 6.858 ms | 7.200 ms |
| decisione → primo audio | 203 ms | 230 ms | 206 ms |
| **fine parlato → voce** | **7.684 ms** | **8.725 ms** | **9.006 ms** |

Interruzione: rilevata a 16.583 ms, voce ferma a 16.599 ms — **16 ms** — e
**zero byte** di coda dopo «Aspetta».

    IL COLLO DI BOTTIGLIA NON È IL TELEFONO.

Trasporto e voce costano 1,8 secondi su 8; il resto è il core che decide. Due
strade sono state **misurate e scartate**: streammare il core guadagnerebbe
~150 ms su 3.000, e Groq ha un tetto di 7.000 token al minuto contro i 13.310
del prompt di ORA. **Il target di 1,2 secondi resta un obiettivo futuro
dipendente dal TTFT del core, non un numero raggiunto.**

### La latenza, misurata e ridotta

    IL COLLO DI BOTTIGLIA NON ERA IL TELEFONO, ED È STATO MISURATO.

Sulla telefonata vera l'attesa fra la fine del parlato e la voce di ORA era di
**9.397 millisecondi**. Trasporto e voce ne costavano 1.800; tutto il resto
era il core che decideva. Smontato voce per voce:

| Voce | Costo | Che cos'era |
|------|------|------|
| lavoro prima del modello | 36 ms | contesto, life os, strumenti: niente |
| provider esaurito tentato per primo | ~1.600 ms | `gemini` in quota, `gemini2` dietro |
| un passo del modello | 2.300-2.600 ms | 25.000 token in ingresso |
| secondo passo, solo calendario | +2.500 ms | «chiama get_calendar_events», poi rispondi |

E il pavimento, misurato togliendo tutto: **~1.900 ms** di sola generazione.
Spostare l'elenco degli strumenti dentro il prompt di sistema per farlo
prendere da una cache di prefisso è stato **provato e scartato**: 2.616 ms
contro 2.821 ms, cioè rumore.

**Il catalogo degli strumenti, scritto in un modo che costa meno.** Trentanove
strumenti pesavano 30.818 caratteri — il settantanove per cento del payload —
e viaggiavano così a ogni chiamata, su ogni canale, a ogni passo. Il
trentasette per cento erano le descrizioni, cioè l'unica parte che serve; il
resto era struttura JSON e sette nomi di chiave ripetuti trentanove volte.
Scritti a una riga per strumento pesano **18.061 caratteri**, e non manca né
un nome, né un argomento, né un valore ammesso, né una descrizione: una prova
li confronta uno per uno. Payload da **38.950 a 21.843 caratteri**.

**Le prossime quarantotto ore, già in mano.** «Che impegni ho domani?» costava
due passi: il primo per dire «chiamate `get_calendar_events`», il secondo per
rispondere. Adesso quelle ore arrivano insieme al contesto, lette **dallo
stesso handler dello strumento** — nessun secondo calendario, nessun secondo
controllo di consenso. Il blocco dichiara la propria finestra, e fuori di lì
ORA chiede ancora: verificato, «la settimana prossima» continua a produrre
una chiamata allo strumento. Sul calendario vero nove eventi erano due:
i duplicati si uniscono, se no ORA direbbe che domani hai cinque impegni.

**Che giorno è oggi.** Il payload portava `today: "2026-09-13"` e lasciava al
modello il compito di dedurre «domenica». Chiedendolo sei volte con la stessa
data: ministral-14b ha risposto martedì, martedì, lunedì; ministral-8b
mercoledì, mercoledì, martedì; gemini2 domenica. Sei risposte sicure, un
giorno diverso quasi ogni volta, sulla domanda più frequente che esista al
telefono. Adesso `today_weekday` lo calcola il codice — in `day_names.py`, con
i nomi scritti a mano e non da `strftime`, che seguirebbe il locale del
processo. Con quel campo, **ministral-8b risponde «domenica»**.

| | prima | dopo |
|---|---|---|
| payload | 38.950 car | **21.843 car** |
| ingresso totale | ~97.400 car | **~80.300 car** (18.650 token) |
| «impegni domani» | 2 passi | **1 passo** |
| turno semplice, gemini2 | ~2.500 ms | **2.381 ms** (p50, 7 casi) |

### Al telefono si aspetta meno, perché si aspetta ad alta voce

    IL BUDGET STRETTO VALE PER IL PRIMO CAVALLO, NON PER L'ULTIMO.

Venticinque secondi sono la protezione giusta contro un provider morto, e
un'eternità per chi ha appena finito di parlare e sente silenzio. Quando la
frase entra da `phone` o da `voice`, il **primo** provider ha dieci secondi;
poi si passa al successivo.

Dieci è 3,3 volte il peggior turno sano mai misurato sul primario (2.989 ms):
largo abbastanza da non tagliare mai una risposta vera, e da reggere un degrado
di tre volte senza mandare ogni turno alla riserva — che costa 5-7 s comunque,
e a quel punto non si guadagnerebbe niente.

**Tre regole, e la seconda è la più importante:**

1. vale solo per il **primo** tentativo; i successivi tengono i 25 s globali,
   perché la riserva è più lenta del primario (peggiore sano misurato: 7.514 ms)
2. **non si applica mai all'ultimo provider disponibile** — abbandonare l'unico
   rimasto non è protezione, è silenzio al telefono
3. può soltanto **stringere**: un chiamante non può chiedere più della
   protezione globale

**Dove vive.** Un parametro facoltativo su `mgr.chat(..., latency_budget_s=None)`
e una tabella pura in `loop.py` che legge `sess.meta["entry_point"]` — la stessa
forma di `spoken_out_loud`: la provenienza governa la forma e l'attesa, mai il
contenuto. **Dieci siti di chiamata su undici non sono stati toccati.** Dentro
`telephone/` non compare una sola durata, e una prova strutturale lo verifica:
se comparisse, sarebbe nato un percorso cognitivo del telefono.

**Vale per tentativo, non per turno.** Un turno a due passi paga due budget, e
va bene così: un tetto sul turno intero vorrebbe dire interrompere un
ragionamento a metà, cioè decidere di non rispondere — e quella è una decisione
di ORA, non dell'infrastruttura.

| Primario impantanato a 34 s | Prima (25 s) | Dopo (10 s) |
|---|---|---|
| tempo al fallback | 30,0 s | **15,0 s** |
| primo turno | 30.020 ms | **15.019 ms** |
| secondo turno | 30.019 ms | **15.013 ms** |
| due turni | 60.039 ms | **30.032 ms** |
| task pendenti | 1 → 1 | 1 → 1 |

---

### Chi ha appena detto di no non si richiama

    UN PROVIDER ESAURITO PER OGGI NON TORNA FRA SESSANTA SECONDI.
    UN PROVIDER LENTISSIMO È PEGGIO DI UN PROVIDER MORTO.

Due modifiche al `ProviderManager`, e nessuna delle due tocca il cervello di
ORA: cambia **quando** si chiede a chi, non che cosa si chiede né cosa si
decide. Stesso prompt, stesso payload, stesso schema, stessa autorità, stessi
strumenti, stesso ordine della catena — e una prova che verifica che a chiunque
risponda arrivi la stessa identica domanda.

**Il cooldown ha memoria.** `_RuntimeState` porta `consecutive_failures`, e
l'attesa cresce finché la causa resta la stessa. Prima ogni fallimento
sostituiva lo stato con uno nuovo, quindi un account in quota veniva richiamato
**una volta al minuto per tutta la giornata**, e ogni richiamo costava fra 698
e 2.900 millisecondi a una persona che stava aspettando.

| Causa | Attesa | Perché |
|------|------|------|
| `quota` | 60 s → 4 min → 16 min → 1 h → **2 h** | esaurita per la giornata: non torna fra un minuto |
| `authentication` · `configuration` | 300 s → 10 min → **1 h** | una chiave sbagliata non si aggiusta da sola |
| `model_unavailable` | 60 s → 2 min → **15 min** | idem, ma un modello può tornare |
| `timeout` · `network` | 5 s → 10 → 20 → 40 → **60 s** | chi è lento adesso lo è anche fra cinque secondi |
| `rate_limit` | **4 s, fisso** | vedi sotto |
| `invalid_response` | **5 s, fisso** | può essere colpa nostra |

Un rifiuto **diverso** fa ripartire il conto da uno: un provider che era in
quota e adesso va in timeout sta descrivendo un altro guasto, e merita di
essere creduto da capo. E un successo azzera tutto.

    IL RATE LIMIT NON SALE, ED È UNA LEZIONE GIÀ PAGATA DUE VOLTE.

Il primo tentativo lo faceva crescere come gli altri, e ha rotto
`test_a_short_wait_is_taken_rather_than_failing_the_turn` — la prova che
custodisce una lezione dello Sprint V3.4: un turno di ragionamento è molte
chiamate, quindi i piani gratuiti limitano la catena intera tutta insieme, e
per questo esiste un'attesa di grazia di sei secondi. Facendo crescere il rate
limit, la seconda panchina finiva oltre quella finestra e **la conversazione
moriva per un'attesa che stava per scadere** — esattamente il difetto per cui
la finestra era stata scritta. `invalid_response` resta fisso per una ragione
diversa: una risposta vuota o bloccata dipende spesso dal payload che abbiamo
mandato noi, e panchinare un provider sano per un nostro errore è punire
l'innocente.

**Un tentativo ha una scadenza.** `_within_deadline` avvolge ogni chiamata a un
provider — nel giro della conversazione e in `analyze_document` /
`ask_document`, che prima erano scoperti. Il tempo scaduto diventa un
`timeout` come un altro, così cooldown e passaggio al successivo funzionano
senza sapere niente di nuovo.

**Venticinque secondi, e il numero viene dalle misure.** Un turno sano costa
2,4 s sul primario e 5 sulla riserva; il peggiore mai misurato fra i provider
in catena è 6,2 s. Venticinque è quattro volte il peggiore: largo abbastanza da
non tagliare mai un caso complesso, stretto abbastanza da non regalare un
minuto a chi non risponderà comunque — l'adattatore Gemini si arrende a 60.
Si configura con `LLM_ATTEMPT_DEADLINE_S`, e **sotto i cinque secondi il valore
viene rifiutato**: non sarebbe una protezione, sarebbe un guasto che ci diamo
da soli. `asyncio.wait_for` aspetta che l'annullamento sia completato, quindi i
gestori di contesto dell'adattatore si chiudono e non resta niente appeso —
verificato su venti turni consecutivi.

**Misurato, prima e dopo**, sul manager vero con provider finti che costano
quanto costano quelli veri (quota 1,6 s · sano 2,4 s · riserva 5 s ·
impantanato 34 s):

| Scenario | Prima | Dopo |
|------|------|------|
| primario sano | 2.406 ms · 0 tentativi buttati | **2.405 ms** · 0 — nessuna regressione |
| primario in quota, 5 turni | 4.021 ms mediana · **5 tentativi buttati** · 20.104 ms | **2.415 ms** mediana · **2** · **15.290 ms** |
| primario impantanato, 2 turni | 34.007 ms · 68.013 ms in tutto | **2.410 ms** al secondo turno · **29.815 ms** in tutto |

Nello scenario in quota i primi due turni pagano ancora il tentativo
condannato — è il prezzo per sapere che il no è davvero persistente — e dal
terzo in poi si risparmiano **1.606 ms per turno**. Nello scenario
impantanato cambia anche *chi* risponde: si preferisce una risposta giusta e
veloce dalla riserva a una lentissima dal primario. È la stessa ORA, con lo
stesso prompt: cambia solo chi lo legge.

---

### La riserva

    UNA RISERVA CHE NON RISPONDE MAI NON È UNA RISERVA.

`mistral` era già quarto nella catena, e configurato su `mistral-small-latest`
— che oggi risolve a `mistral-small-2603`: **ventimila token al minuto**. Il
prompt di ORA ne porta 18.654, quindi una chiamata sola satura il minuto e la
seconda prende 429. Misurato: 429 su ogni tentativo, anche su una richiesta da
quattro token.

Provati tre modelli sullo stesso identico carico, rispettando i tetti di
richieste al secondo dichiarati dall'account:

| | ministral-14b-2512 | ministral-8b-2512 | mistral-large-2512 |
|---|---|---|---|
| prompt accettato | sì | sì | **no — 403, fuori abbonamento** |
| TTFT p50 | 2.392 ms | **1.480 ms** | — |
| totale p50 / p95 | 8.790 / **23.310** ms | **5.018 / 6.169 ms** | — |
| JSON · modo · strumento | 7/7 · 7/7 · 7/7 | 7/7 · 7/7 · 7/7 | — |
| 429 | 0 | 0 | — |

**`ministral-8b-2512`**, quindi: stesse identiche scelte di `ministral-14b` in
metà tempo, sei volte le richieste al secondo, e nessun caso oltre i sette
secondi contro un p95 a ventitré. Resta **dietro**, dove deve stare: la catena
è `gemini → gemini2 → groq → mistral`, e il manager ci arriva da solo quando i
primi sono in quota o in cooldown. Verificato con i primi tre messi in
cooldown: risponde `mistral/ministral-8b-2512`, JSON valido, modo giusto,
`get_calendar_events` e `prepare_a_phone_call` scelti giusti.

Sulla riserva un turno costa **5.733 ms** (p50 su cinque), che al telefono
diventano circa 7,4 secondi. È una rete, non un posto dove stare.

---

### Privacy

| Cosa | Dove finisce |
|------|------|
| PCM dal telefono | passa a chi ascolta, **non esiste più** |
| PCM verso il telefono | versato sul filo, **non esiste più** |
| testo di quello che si è detto | `PhoneCall.turns`, come una conversazione |
| tempi e conteggi | `PhoneCall.metrics` — solo numeri e nomi di stati |
| chiavi | solo `.env` e un file fuori dal repo |

Nessun buffer che cresce, nessun file, nessun base64, nessun campo binario.
Verificato sul documento rimasto: **3.346 caratteri, zero campi con byte
grezzi**. Ci sono prove che guardano il codice e falliscono se compaiono
`open(`, `write(`, `b"".join`, `wave`, `BytesIO`, `base64`.

### Come rompe

| Guasto | Cosa succede |
|------|------|
| fornitori non disponibili | la linea non si apre, la telefonata non comincia a mentire |
| chi ascolta cade a metà | il giro non chiude la linea; si torna ad ascoltare |
| il core tarda oltre 45 s | si lascia perdere il turno, senza riempitivi |
| la voce non finisce | l'inciampo resta nei numeri, la linea regge |
| la persona riaggancia | tutto lasciato andare in ordine, nessun task appeso |

### Difetti trovati dalle prove vere, non dai test

- **Il turno si chiudeva su «Ciao, ORA»** — due volte, per due ragioni
  diverse: vedi sopra. Nessun test avrebbe potuto trovarle, perché richiedono
  di sapere *quando* un trascrittore vero consegna i pezzi.
- **L'ultimo turno spariva dai numeri.** Il trasporto leggeva i tempi *prima*
  di chiudere, e il turno ancora in corso non era ancora stato archiviato: il
  conteggio diceva uno quando i turni erano due. Un difetto di misura è
  peggio di un difetto visibile, perché fa sembrare sano quello che non lo è.
  Adesso c'è una prova che lo tiene fermo, e una seconda che controlla
  l'ordine nel trasporto.

### Debito residuo

- Il core non streamma: primo token e decisione completa coincidono. I due
  campi restano distinti perché il giorno che cambierà si vedrà la differenza
  senza toccare niente.
- I pezzi da dire arrivano tutti insieme (`_pieces_as_stream`): il giorno che
  arriveranno a goccia, quella funzione sparisce e il resto non se ne accorge.
- L'audio già consegnato al trasporto non è richiamabile: 20 ms di coda.
- `1,2 s` di attesa percepita: non raggiunto, e dipende dal core.

### Il reality gate

**Chiuso sul vero.** Le tre condizioni sono state verificate su telefonate
reali: due turni risposti nella stessa chiamata, interruzione con «Aspetta»
onorata, zero byte di audio persistito.

    QUESTO RUNTIME NON È PIÙ L'UNICO, ED È UNA COSA VOLUTA.

Il runtime descritto qui sopra — Deepgram in entrambi i versi, ORA intera a
condurre — è il **runtime classico**, e resta il valore di riposo di
`ORA_VOICE_RUNTIME`. Accanto gli è nato il **runtime a missione** su Gemini
Live, per le telefonate che sono una trattativa scritta prima. La scelta fra i
due sta in un punto solo, `telephone/runtime.py`, e il trasporto non sa quale
dei due sta conducendo. Vedi le sezioni V3.13 — GEMINI LIVE e successive, in
testa a questo documento.

---

## V3.13 — SPRINT 3.1 — REAL TELEPHONE TRANSPORT FOUNDATION — CLOSED

**Il filo, non ancora la voce.**

    IL TRASPORTO TELEFONICO NON È UNA VOCE. È UN ATTUATORE.
    NIENTE DI QUELLO CHE PASSA DI LÌ RESTA LÌ.

Operatore: **Vonage Voice API**. Nessuna libreria del fornitore — bastano
`httpx` e `PyJWT`, che il prodotto ha già.

| Porta | Dove | Chi la chiama |
|------|------|------|
| `GET /vonage/answer` | **fuori da `/api`** | l'operatore, per il copione |
| `POST /vonage/event` | **fuori da `/api`** | l'operatore, per gli stati |
| `GET /vonage/fallback` | **fuori da `/api`** | l'operatore, quando il resto tace |
| `WS /vonage/socket` | **fuori da `/api`** | l'operatore, per l'audio |
| `/api/telephone/prepare · place · hangup · {id}` | sotto `/api` | la persona, autenticata |

**Perché fuori da `/api`** — gli indirizzi sono già nel pannello di Vonage, e
quelle rotte non hanno una sessione: le chiama un operatore telefonico, non un
browser. **La protezione è strutturale**: agiscono solo su una telefonata che
ORA ha composto e sta aspettando.

**Riuso, non duplicazione**

| Cosa | Da dove |
|------|------|
| autorità | `agent/authority.py` — `phone.call`, `_NEVER_AUTONOMOUS` |
| capacità | `agent/capabilities.py` — `writes`, `reaches_third_party`, `hardly` |
| conversazione | `conversation_engine/ai_core/orchestrator.py` via `same_ora.py` |
| mandato, esito, fascicolo | `telephone/` dallo Sprint 3, invariati |
| voce nell'app | **non toccata** — microfono e Live Voice restano come sono |

**Sessione effimera** — `PhoneCall` collega uuid dell'operatore, `owner_id`,
riferimento di sessione, stato, mandato. Più tre numeri sull'audio:
`audio_frames`, `audio_bytes`, `first_audio_ms`. Nessun campo per il suono.

| Punto | Stato |
|------|------|
| Le tre porte rispondono sul backend vivo | **verificato** |
| Copione che apre il websocket | **verificato** |
| `answered` → `talking` | **verificato** |
| Websocket accetta frame binari PCM L16 16 kHz | **verificato** (25 frame, 16.000 byte) |
| Nessun audio persistito | **verificato** (documento: 584 caratteri) |
| Chiave privata fuori da repo, log e Mongo | **verificato** |
| Nessuna chiamata senza sì esplicito | **verificato** |
| Tunnel che punta al backend | **verificato** |
| La chiamata parte davvero dal backend | **verificato** — Vonage accetta e assegna un UUID |
| Vonage raggiunge il nostro webhook | **verificato** — POST da un suo IP, 200 OK |
| **Vonage apre davvero il websocket** | **verificato** |
| **Audio di una voce umana dentro ORA** | **verificato** — 556 frame, 11,1 secondi |

**Il reality gate, passato.** 12 settembre, 19:43. `prepare` → 200. `place`
senza conferma → **428**, l'autorità tiene. `place` con conferma → 200, e il
telefono squilla davvero:

    started → ringing → answered → completed

`GET /vonage/answer` raggiunto da un IP Vonage con l'uuid della chiamata; il
copione ha aperto il websocket; **556 frame di PCM lineare a 16 kHz**, 355.840
byte, **11,1 secondi di voce umana vera**, primo frame a **354 ms**. La persona
ha riagganciato e il documento rimasto pesa **767 caratteri**: nessun campo
contiene audio, e la chiave non compare in nessun log.

Il caller ID è la cosa che ha sbloccato tutto: con `123456789` la rete
rispondeva `rejected/restricted` su ogni variante — payload completo, payload
minimo, endpoint europeo, `from` registrato. Sei chiamate, sei rifiuti
identici: il payload non era mai stato la causa.

**I tentativi precedenti.** `prepare` → 200. `place` senza conferma
→ **428**, l'autorità ha tenuto. `place` con conferma → **200 in 650 ms**, e
Vonage ha assegnato l'UUID `61bc0968-…`. Poi un evento solo, dal suo IP:

    stato=rejected  motivo=restricted

La rete non ha lasciato passare la chiamata — prima che il telefono
squillasse. È una cosa del pannello Vonage, non del codice: su un account di
prova la destinazione dev'essere fra i numeri di test, e l'API accetta la
richiesta (200 + UUID) prima che il rifiuto arrivi come evento.

**Un difetto trovato dalla telefonata vera, e non dai test:** il router
leggeva `user["id"]` mentre in tutto il prodotto la chiave è `user["user_id"]`.
Ogni richiesta autenticata moriva con un 500. Nessuna prova se n'era accorta
perché parlavano tutte al servizio, non alla porta — adesso ce n'è una che
bussa con un JWT vero.

**E un secondo:** `rejected` era tradotto in «non ha risposto nessuno», cioè
in una frase che dà la colpa alla persona chiamata per qualcosa successo prima
che il suo telefono squillasse. Adesso è `failed`, e il motivo dell'operatore
viaggia con l'evento.

**Sprint 3.2** — STT e voce in linea. `telephone/bridge.py` esiste e non è
collegato: porta il modello che ascolta e risponde, ma il suo audio viaggia in
base64 dentro JSON — la forma di un altro operatore. Vonage porta PCM binario
a 16 kHz e il modello ne vuole 24: servono la lettura dei frame binari e un
ricampionamento. Il resto di quel file — turni, interruzione, fascicolo,
latenza — resta valido.

## V3.13 — SPRINT 2 — MULTIMODAL LIFE UNDERSTANDING — CLOSED

**Quello che si mostra è una fonte della vita, non un allegato da archiviare.**

    HO VISTO != SO.
    PLAUSIBILE != VERIFICATO.
    STESSA CONTROPARTE != STESSO EVENTO.

| Cosa arriva | Che strada fa |
|------|------|
| immagine con testo | si legge — nessuno paga per guardarla |
| immagine senza testo leggibile | si guarda: `look_at_image` |
| PDF con testo dentro | si legge |
| PDF scansionato | si disegna la prima pagina e si guarda |

**Il «+»** apre un menu — foto e file · foto · fotocamera · documenti — e la
fotocamera c'è solo dove `capture` apre davvero l'obiettivo. Esc chiude, il
tocco fuori chiude, il focus torna sul pulsante, il popover sta sopra il campo
e non lo copre.

**Il contratto** è `VisualObservation`: cosa vedo, quanto riesco a leggere
(`readable · partially_readable · unreadable · ambiguous`), cosa non ho letto,
cosa non so, e zero o più `LifeTie` — ognuno con la ragione che lo lega a
*quella* parte di vita, la forza delle prove e la frase che quella forza
consente.

| Forza | Cosa si può dire |
|------|------|
| `observed` | si afferma |
| `supported` | si dice, dicendo su cosa si regge |
| `plausible` | si propone, e si dice cosa servirebbe per esserne certi |
| `unknown` | si dice che non si sa |

A **ogni** livello, `observed` incluso: non si può dire che questo è lo stesso
evento di un impegno in calendario. Un legame porta a una pratica, non a un
appuntamento.

**Correzioni entrate con questo sprint**

| Difetto | Stato |
|------|------|
| una foto senza testo era un file «failed» | si guarda |
| dodici caratteri di rumore contavano come lettura | serve una parola o una cifra |
| importo preso dall'immagine sbagliata | ogni domanda alla sua immagine |
| `get_calendar_events` esplodeva su un giorno intero | gli istanti si confrontano, e la prova sopravvive all'ornamento |
| lettura fallita detta come certezza | una lettura fallita è la risposta |
| l'immagine si guardava nel vuoto | arrivano denaro e impegni che stanno in piedi |
| un solo modello per guardare | catena di modelli |
| la più vecchia invece della più recente | la più recente |
| nessuna fonte di contesto per il denaro | c'è, con i gradi intatti |
| domanda in italiano che non agganciava il denaro | l'area la nomina chi ragiona |
| filtro che non trova → «non so niente» | torna quello che sa, e dice che la parola ha mancato |
| scansione senza testo irraggiungibile | prima pagina disegnata |
| `plausible` detto come certezza | esce la frase, non l'etichetta |

| Punto | Stato |
|------|------|
| Comprensione visiva reale | **verificata** su immagini vere |
| Confronto con vita e calendario | **verificato** |
| Guardia epistemica | **0/5 overclaim** su cinque esecuzioni reali |
| `PENSO` → `SO` | **mai** senza governance |
| `FinancialFact` duplicati | **nessuno** (0 righe, prima e dopo) |
| QA fisico su iPhone | **da fare** — vale anche per lo Sprint 1 |
| Autonomia a partire da un visivo | giudizio sì, scrittura no: passa dall'Action Engine |
| Barge-in a voce, streaming TTS | debito dichiarato dallo Sprint 1 |
| Prodotto target | **iOS**. Nessun lavoro specifico Android |

## V3.13 — SPRINT 1 — VOICE INTERFACE — CLOSED

**La voce come modo di entrare, non come posto dove andare.**

    VOICE IS NOT A SEPARATE ASSISTANT.
    STESSO SIGNIFICATO, ALTRA FORMA.

| Controllo | Cosa fa |
|------|------|
| microfono | detta un messaggio; ORA risponde per iscritto |
| quattro barre | conversazione parlata: voce ↔ voce, ritorno automatico all'ascolto |

**Cosa condividono** — sessione, Personal Life Model, agente, capacità,
autorità, Life Search. Le parole dette passano da `sendWords`, la stessa
funzione del testo; da lì in poi il percorso è uno solo.

**Chi parla**

| Livello | Chi | Quando |
|------|------|------|
| 1 | Gemini TTS, voce **Kore** | sempre che si possa |
| 2 | `speechSynthesis` del browser | quando la prima non c'è o non ce la fa |
| 3 | solo testo | quando non parla nessuno |

Il contratto è `SpeechOutputProvider` (`speak`, `stop`, `is_available`).
Nessuna schermata conosce il nome del fornitore, e un test lo verifica.

**Correzioni entrate con questo sprint**

| Difetto | Stato |
|------|------|
| la conversazione non raggiungeva la ricerca della Vita | `search_my_life` |
| orizzonte temporale fisso a 7 giorni | lo decide la domanda |
| impegni annullati e letture superate nella ricerca | filtrati |
| ore rese in UTC | fuso della persona |
| stesso impegno chiesto due volte → due eventi | uno, e lo dice |
| «ho aggiunto» per una cosa già in agenda | `created_now: false` |
| voce che guardava un solo account | catena di chiavi |
| risposte in ritardo che riaprivano l'ascolto | ogni giro ha il suo numero |

| Punto | Stato |
|------|------|
| Percorso vocale su PC | **verificato** (microfono e altoparlante reali) |
| Voce Kore | **ascoltata e confermata** |
| QA fisico su iPhone | **da fare** — non blocca lo Sprint 1 |
| Barge-in a voce (interrompere parlandole sopra) | debito dichiarato |
| Streaming TTS | non verificato |
| Prodotto target | **iOS**. Nessun lavoro specifico Android |

**Prossimo: V3.13 Sprint 2.**


## AUTONOMY REALITY GATE — V3.2 / V3.7 / V3.8 / V3.9 — REALITY-TESTED & HARDENED

**Non una versione nuova: quattro versioni già chiuse, provate su una vita
vera e riparate dove si sono rotte.**

    CODE RETRIEVES AND ENFORCES. AI UNDERSTANDS AND DECIDES.
    NOT URGENT != NOT USEFUL.
    NEVER ASK SOMEBODY TO DO INFORMATION WORK ORA CAN DO ITSELF.

| Anello | Cosa si è rotto sull'account vero | Stato |
|------|------|------|
| segnale → comprensione | `interpret` moriva su un `datetime` senza fuso | riparato |
| comprensione | il giro leggeva e non capiva mai | riparato |
| fatti → giudizio | agenda di appuntamenti annullati, niente situazioni, niente denaro, niente disaccordi | riparato |
| disaccordi | query che prendeva le righe nulle; riferimenti non citabili | riparato |
| giudizio | «non è urgente» usato come ragione per tacere | riscritto |
| iniziativa | nessuna scala: o silenzio o niente | `inform…blocked` |
| domanda | chiedeva prima di guardare | prova, poi chiede |
| riga ambient | «tutto tranquillo» sopra un'iniziativa aperta | stesso stato della card |

**Cosa il codice possiede** — raccogliere i fatti veri (vivi, deduplicati, con
la loro storia), tenere l'identità di una preoccupazione, imporre che ogni
affermazione punti a un fatto esistente, portare il gradino scelto a valle,
non far mai diventare `unavailable` un `silence`. **Cosa decide l'AI** — se
qualcosa merita attenzione, quanto, fin dove spingersi, se una domanda serve
ancora dopo aver guardato, e cosa scrivere.

**Nessuna soglia di dominio.** Due guardie strutturali leggono l'albero dei
file che decidono e falliscono se compare un numero che stabilisce se
qualcosa conta, o una parola della vita di qualcuno.

| Punto | Stato |
|------|------|
| Ciclo zero-prompt | gira dentro l'ambient runtime che c'era già |
| Iniziative su vita reale | 2 nate, 1 ritirata da sola, 3 domini in silenzio |
| Goal spam | nessuno: `recommend` resta una frase |
| Autorità | leggere e preparare no; toccare il mondo sì |
| Verifica interna | prima della domanda, sempre |
| Prodotto target | **iOS**. Nessun lavoro specifico Android |

**Prossimo: V3.13.**


## V3.12 — LIFE MAP & UNIVERSAL SEARCH — CLOSED

**Il modello della vita, reso visibile, navigabile e interrogabile.**

    LA RELAZIONE CONTA PIU' DELLA PAROLA.

Nessun secondo modello: la ricerca legge quello che c'è — situazioni, memorie
governate, fatti finanziari, segnali, documenti, messaggi — e l'unica cosa che
scrive sono le *relazioni*, nella collezione di collegamenti che il Connected
Life usava già.

**Come si trova una cosa**, in ordine di quanto vale:

| Modo | Che cos'è |
|------|--------|
| explicit | la persona ha nominato proprio quella cosa — o la sua cifra |
| governed | una relazione passata dalla governance (`about_refs`) |
| situation | una relazione registrata: documento→casa, mail→situazione, fonte↔fonte |
| provenance | la catena da dove viene: fatto → movimento → conto |
| semantic | il giudizio dice che la domanda parla di quella parte della vita |
| lexical | l'ultima risorsa, e si sa che è l'ultima |

**Chi fa cosa.** L'AI capisce, collega, giudica la pertinenza e sintetizza; il
codice recupera, delimita, valida, persiste le relazioni permesse, deduplica e
tiene ferme provenienza e storia. Due guardie leggono i file e falliscono se
uno dei due invade il campo dell'altro.

| Punto | Stato |
|------|--------|
| Sprint 1 — ricerca, relazioni, gruppi, conflitti | chiuso |
| Sprint 2 — documenti collegati, cache, dedupe, sintesi | chiuso |
| Sprint 3 — comunicazioni collegate, rumore, manutenzione automatica | chiuso |
| Schede | sempre cinque: la ricerca entra dalla Vita |
| Costo | 1 chiamata per domanda semplice, 2 per una sintesi, 0 se ripetuta |
| Manutenzione | dentro il giro che c'era già, solo sul nuovo, idempotente |
| Corpo delle email | letto solo su richiesta del giudizio, mai conservato |
| In schermata | nessun id, nessun punteggio, nessun «trovato per parola» |
| Prodotto target | **iOS**. Nessun lavoro specifico Android |

**Prossimo: V3.13.**

**Roadmap futura (registrata, non pianificata):** agente vocale/telefonico
nazionale capace di fare telefonate reali previa autorizzazione esplicita
della persona.


## V3.11 — FINANCIAL INTELLIGENCE — CLOSED

**Un conto vero, letto come sensore, che diventa contesto di vita.**

    UNA TRANSAZIONE È UN'OSSERVAZIONE. IL SIGNIFICATO VIENE DOPO.

Enable Banking Sandbox collegato per intero, con consenso vero: ASPSP →
consenso → callback → sessione → conti → saldo → movimenti → osservazioni →
interpretazione → governance → modello della vita → «Conti e denaro». Poi
scollegato davvero, e ricollegato davvero.

**Il percorso, e cosa lo tiene onesto.**

| Passaggio | Chi decide |
|------|--------|
| Trasporto e normalizzazione | il codice: importo, segno, data, descrizione, controparte |
| Categoria del provider | prova, mai significato — viaggia dentro `provenance` |
| Raggruppamento in pattern | aritmetica: quante volte, ogni quanti giorni, quanto è cambiato |
| Cosa significa | il giudizio, una volta per gruppo, guardando questa vita |
| Cosa merita di durare | la governance: PROMOTE · SUPERSEDE · CLARIFY · REJECT |
| Come si dice | SO · PENSO · HO VISTO · DA CAPIRE, distinti fino in schermata |

**Stato della fonte, in un posto solo.** `financial/observed.py` risponde a
«posso leggere adesso?», e da lì dipendono il tempo verbale della schermata,
quello della conversazione, e il diritto di parlare di un saldo. Collegato:
l'ultimo saldo letto con la sua ora. Scollegato: non lo si conosce, e si può
dire soltanto quale risultava. Ricollegato: corrente di nuovo, ma solo dopo
una lettura vera.

| Punto | Stato |
|------|--------|
| Sprint 1-4 — modello, governance, orizzonte, comprensione | chiusi |
| Sprint 5 — banca come sensore, «Conti e denaro» | chiuso |
| Sprint 6 — provider reale (Enable Banking), consenso, tetti di chiamata | chiuso |
| Gate finale — disconnect, riconnessione, risposte | chiuso su conto reale |
| Attuatori | nessuno: la banca si legge e basta, guardie strutturali incluse |
| Chiave privata e credenziali | fuori dal repository, lette da env, mai persistite né loggate |
| IBAN | mai conservato per intero: solo le ultime quattro cifre |
| Cadenza | sei ore, e un tetto imposto dalla banca vince sulla nostra cadenza |
| Costo | una chiamata per pattern, zero per una spesa isolata senza contesto |
| Prodotto target | **iOS**. Nessun lavoro specifico Android |

**Prossimo: V3.12.** *(chiusa il 10 settembre 2026)*

**Roadmap futura (registrata, non pianificata):** agente vocale/telefonico
nazionale capace di fare telefonate reali previa autorizzazione esplicita
della persona.


## V3.10 — CONNECTED LIFE — SPRINT 3 CLOSED (phase open)

**Sprint 3 closing — the provider is real, and nobody presses anything.**

    THE USER DOES NOT SYNCHRONISE THEIR LIFE. ORA DOES.

Gmail now speaks to Google. A real mailbox is connected through the OAuth
flow built earlier, and a real reading advanced Google's own `historyId`
(4474116 → 4474225), wrote `last_sync_at`, produced 23 signals, and kept no
body, no address and no token anywhere — checked field by field rather than
asserted.

**Auto-sync, inside the loop that already existed.** `connected/polling.py`
decides *when* to look — a cadence per instrument (mail 5 min, calendar 15,
the document shelf 30), doubling on failure to a one-hour ceiling, skipping
anything not readable — and the ambient runtime calls it once per tick,
before draining wakes so that what just arrived is handled in the same pass.
No second scheduler, no second thing to start and stop, and nothing in that
path reaches a model: deciding when to look is arithmetic.

**Two defects in the connectors, both found by making sync automatic.** The
calendar asked Google for `orderBy=startTime` on its first listing, and
Google refuses to return a `nextSyncToken` for an ordered request — so no
token was ever stored and every sync re-read the whole window. It had been
invisible because syncs only happened when somebody pressed a button; at one
every fifteen minutes it is a different thing. Removing the ordering (nothing
downstream needs it) produced real sync tokens for both calendars, and the
next read ingested nothing. The Gmail sync, separately, never wrote
`last_sync_at` — so the screen would have said "mai sincronizzato" under a
mailbox read a minute earlier.

**The button is gone.** Neither Google Calendar nor Gmail offers "Sincronizza"
anywhere — not as a secondary action, not in overflow, not on mobile — and a
guard walks every screen to keep it that way. What the card shows instead is
the distinction that was being hidden: *connected* and *up to date* are two
facts, so a card says «Aggiornato automaticamente · 7 minuti fa», or
«Connesso · ultimo aggiornamento ieri», or «Connesso · non riesco ad
aggiornarlo in questo momento». Apple Calendar keeps an action, because the
backend cannot poll an iPhone — but it is no longer called synchronising.

**Sprint 3 — communications as a sensor, and several sources as one life.**
Email becomes the third instrument, and the point of the sprint is not the
mailbox: it is that a calendar, a message and a document can be three
readings of one afternoon.

    EMAIL IS NOT A FEATURE. IT IS A SENSOR OF THE LIFE.
    MULTIPLE SOURCES CAN REFER TO THE SAME THING IN A PERSON'S LIFE.
    NO LINK IS EVER MADE BY A STRING MATCH.
    CODE DOES NOT CHOOSE THE TRUE SOURCE.

**The audit changed the plan again, and this time it found a hole under the
last two sprints.** There was no Gmail connector — only a registry stub — but
the more important finding was about the calendar. Sprint 1's sensor filtered
ingestion rows on `source_type == "calendar"` and read each field as a plain
string. Real rows carry the connector's own id in that field
(`calendar_google`) and each value wrapped in a `NormalizedField` envelope, so
the sensor matched nothing a real sync had ever written, and would have read
every connected calendar as an empty world. Every Sprint 1 and 2 test passed
because every one of them wrote its own fixture in the shape its own sensor
expected. Both halves are fixed — read by `source_record_type`, unwrap the
envelope once — the fixtures now use the real row shape, and a new test builds
its row with the actual normalizer and repository so the two cannot drift
again.

**The mailbox.** `connectors/gmail/` is a read-only connector: profile,
history, list, message metadata, and one deliberately awkward `body_of`. No
send, no reply, no labels, no delete — asserted structurally, not promised.
Gmail's `historyId` is the cursor; its expiry after about a week is answered
with a bounded resync rather than an error or an empty inbox, and the cursor
moves only after a reading that finished. Rows are minimised at the door: who
it is from as a *relationship*, what it is about, when, whether anything was
attached — never the body, never an address.

**A thread is one conversation.** Three replies in one pass fold into one
signal that says how many messages it covers, for the same reason a recurring
series folds. A message read twice is not a conversation moving on.

**Cross-source linking — the core.** `connected/situations.py` gathers
candidates (appointments near in time, documents recently filed, situations
the Life Object engine already holds) as facts with no scores, and
`reasoning.decide_link` decides the relationship: same situation, related,
new, irrelevant, or uncertain. There is deliberately no fallback that picks
the closest candidate, and a target the model invents is refused. Where two
readings say different things, both statements travel with when each was
observed and how directly each knows — and nothing in code resolves them.
Recording a link is a row with its evidence, never a merge and never a write
to the Life Model: durable belief still goes through governance, which for
these observations has been answering CLARIFY rather than writing.

**Actuators: still none.** `calendar.write` from V3.9 remains the only wired
write; `mail.send` stays in the catalogue, unwired, and permanently
non-autonomous. An email that says "send us the form by Friday" produces a
fact, not an authority — proven by running the whole pass and checking the
authority model is untouched.

**Two more defects found and fixed on the way.** The Sprint 2 re-ask read the
judgement before anything checked one had arrived, so the first provider
outage would have crashed a pass instead of leaving signals pending. And the
wake booked one think per signal, because the wake's identity included the
signal id — so three messages in a minute woke the agent three times, while
the comment above it claimed coalescing. Both are fixed and both now have a
test.

**What is proven.** 56 new tests across four suites (152 in the connected
package and its neighbours), 23/23 mutations caught on the first run, 297
targeted regressions green. Seven sanitised traces and five live calls, split
in the report between what was demonstrated live and what is a recorded
artefact.

**Live evidence, stated precisely.** Five live calls. The pipeline ran
end-to-end live on three scenarios; the model answered `noise` on a
week-old reminder and on a newsletter, and `uncertain` on a first
same-situation attempt whose message did not say which appointment it meant —
its reason was sound. A fifth call on a message that named the practice
returned `same_situation` with the right target, confidence 0.85, and a
human-safe reason. Conflict handling was exercised live only as far as the
model choosing not to link; the disagreement representation itself is proven
by tests, not live.

**Accepted debt, after Sprint 3.** Auto-sync is implemented and proven but
**not switched on**: `AMBIENT_RUNTIME` is unset in this environment, so the
loop that would run it does not start. Turning it on means ORA reads a real
mailbox on a timer and sends message subjects to a model provider — a
decision about somebody's personal mail, not a deployment detail, and left
to the CPO. The live cross-source gate on *real* mail is unproven for the
same reason it cannot be faked: it needs QA messages in the connected
mailbox, and the connected mailbox is personal. Attachments are observed,
never downloaded. The link decision is recorded but no surface shows it, and
nothing writes a link into a Life Object. Polling is bounded per tick across
all owners, so a very large number of connected accounts would be served in
round-robin over several ticks — fair enough at this size, not a fairness
algorithm. `tests/test_action_engine.py` is still red and was red before this
sprint.

Next: V3.10 Sprint 4 — not proposed, not authorised.


## V3.10 — CONNECTED LIFE — SPRINT 2 CLOSED

**Sprint 2 — from sensing to knowing.** Sprint 1 closed with four debts
written down honestly, and this sprint is those four and nothing else. No new
provider, no new sensor, no new actuator: the foundation closing its own gaps.

    WITHHELD IS NOT UNREACHABLE. IT IS UNKEPT.
    A REPLACED DOCUMENT IS NOT A SECOND ARRIVAL.
    ONE CHANGE IS ONE SIGNAL, HOWEVER MANY ROWS THE PROVIDER SENT.
    AN APPOINTMENT SOMEBODY WAS INVITED TO IS SOMEBODY ELSE'S DECISION.

**Content, transiently.** A judgement that genuinely cannot decide without a
withheld note may now say so — `needs_content`, with its reason — and is asked
again, once, with the content in front of it. `connected/content.py` reads it
from ORA's own ingestion row, bounds it, and hands back a value that reaches
exactly one prompt. Nothing stores it: the audit row in
`connected_content_reads` says whose, which fields, when and why, and has
nowhere to put what was read. Attendees still arrive as "2 persone" and the
organiser as "qualcun altro" — other people's addresses answer no question
about this person's afternoon. The re-ask happens at most once, guarded in
two places: the service asks once and then decides, and an answer assembled
after the content was shown may not ask for it again.

**A shelf with a memory.** `connected/seen.py` keeps one row per object: the
last observed value of each field a person could notice, with private ones
kept as a digest. That is what a source rewriting in place needs in order to
have a past, and it turns the documents sensor into `document.added |
updated | removed` — a replaced file is one `updated`, not a second arrival,
and a document already filed before ORA ever saw it is nothing at all.

**A series is one thing.** `_fold_series` folds occurrences into their master
when what changed on them is a subset of what changed on it. Arithmetic on
sets rather than a preference for masters: an occurrence that moved on its
own survives as its own news, and so does a lesson newly added to a series
that also changed. `covers` says how many occurrences the one signal stands
for, and it is part of the fingerprint.

**Whose it is, read at last.** Sprint 1 recorded `relationship` and nothing
looked at it. Now `for_ai()` carries it to the judgement, and
`connected/ownership.py` answers the authority question: an instruction to
move an appointment somebody else called resolves to `external_party`, which
puts it back behind an explicit confirmation exactly as adding a guest does.
An event never observed answers `unknown`, never `own`.

**Actuators: none added, deliberately.** Connected Life senses. The only
wired write capability is still `calendar.write` from V3.9, behind the
authority ceiling that phase built, and a test asserts it rather than a
comment promising it.

**What is proven.** 17 new tests (47 in the package), 16/16 Sprint 2
mutations caught, 194 targeted regressions green across nine suites. Three
of the sixteen mutations initially survived and each exposed a real hole:
one test that could not observe the leak it claimed to guard, a constant
(`_OBSERVABLE` in the documents sensor) that nothing consulted, and a rule
with no test at all. Fixed, then re-killed.

**Live evidence, stated precisely.** The gate was re-run on a new scenario —
an appointment where only the private note changed. Five live calls in total
across three runs: one where the model decided without asking, and two runs
of two calls where it asked, was shown the note once, and judged
`worth_knowing`. The note appeared in the second prompt and in no collection,
no signal, no seen-state and no audit row. The first of those runs was
scored FAILED by a leak detector of mine that searched for a stopword; the
detector was wrong, was fixed to search for phrases that exist only inside
the note, and the run was repeated. That is a passed gate on that scenario,
not a general demonstration that judgement is correct.

**Accepted debt, after Sprint 2.** The documents sensor still reports the
record, not the extraction: "its facts changed" remains known to the
documents pipeline and not to this one. No webhooks — incremental polling on
the existing queue. Ownership is read from the last observation, so an event
ORA has never seen answers `unknown` and the caller decides without it.
Transient content is calendar notes and document annotations only; nothing
reads a file's text. `tests/test_action_engine.py` is red and was red before
this sprint — unrelated code, untouched here.

Sprint 2 closed. Its own debts are addressed in Sprint 3, above.


## V3.10 — CONNECTED LIFE — SPRINT 1 CLOSED

The outside world becomes something ORA can sense. Sources are instruments
rather than features, and what they report is an observation rather than a
fact about somebody's life — the distance between those two is the whole
sprint.

    INTEGRATIONS ARE NOT FEATURES.
    THEY ARE SENSORS AND ACTUATORS OF THE PERSONAL LIFE MODEL.

    CODE KNOWS WHAT CHANGED. THE AI DECIDES WHETHER IT MATTERS.
    CONNECTED DOES NOT MEAN INTERRUPTING.
    A FAILED READING IS NOT AN EMPTY WORLD.
    ORA MUST RECOGNISE ITS OWN FOOTPRINTS.

**Sprint 1 — Life Signals & Connected Context Foundation.** The audit came
first and changed the plan: half the pipeline already existed and was joined
to nothing. The connector had incremental sync with a per-calendar token,
ingestion had normalisation and hash dedupe with a `supersedes` link, V3.7 had
a `MeaningfulChange` intake that already declared `calendar` and `documents`
as sources it would accept — and nobody had ever spoken to it. What was
missing was a translator, the truth about the instrument, and the recognition
of ORA's own writes.

So `backend/connected/` adds three things and reuses everything else.
`ConnectedSource` is a derived view — account, scopes and cursor stay where
they were always kept — and the only thing persisted is what nobody held:
how the last attempt went. `ConnectedSignal` is one observation, deliberately
anaemic, with no field in which importance could be recorded. And the join is
a translation into vocabularies that already exist: `MeaningfulChange` (V3.7)
→ `AmbientWake` (V3.8) → the agent loop (V3.9). No second reviewer, no second
scheduler, no second delivery, and nowhere that a goal can be created by an
`if`.

**Sprint 1 boundary correction.** The first cut of the calendar sensor
returned one delta chosen by a hard-coded order — cancellation, then time,
then location — and dropped attendee and description changes entirely on the
grounds that "nobody would notice". Both are semantic judgements about a
person's life, made in a comparison function that has never seen one. They
were removed. An update is now `calendar.event.changed` carrying every
human-observable difference in `changed_fields`; `created` and `cancelled`
survive because they are structural rather than evaluative. The only filter
left is provider bookkeeping — an etag, a sequence, the provider's own
timestamp — which is arithmetic about a record, not a judgement about a life.

**Data minimisation without losing the fact.** Notes, attendees and organiser
travel as `content_withheld`: somebody's private note and other people's
addresses do not belong in a stored signal, and "the note changed" is still a
fact the judgement is entitled to. Protecting the content by pretending
nothing happened would be protecting it by lying.

**What is proven.** Composite delta, per-field minimisation, provider-noise
filtering, dedupe on the whole delta, supersede when the same thing moves
again, self-originated writes recognised from ORA's own receipts before any
judgement is paid for, honest source health and freshness, and no goal ever
created by code. 30 tests, 14/14 mutations caught, 351 targeted regressions.
Five sanitised traces and six screenshots in `ORA-QA-V310-S1`.

**Live evidence, stated precisely.** One live call was made, on one scenario:
an appointment that changed both time and location. The judgement used both
facts — which the previous code made impossible, because the location delta
never reached the model. That is a passed boundary gate on that scenario, not
a general demonstration that interpretation is correct: the traces for the
other scenarios carry recorded judgements and say so line by line.

**Accepted debt.** The content of notes, attendees and organiser is not
carried; a transient minimised retrieval for judgements that genuinely need
content is designed for and neither implemented nor demonstrated. The
documents sensor sees arrival only — "its extracted facts changed" is known
to the documents pipeline and not to this one, and claiming it here would be
inventing a certainty. Recurring events are watched as occurrences, which is
what moves; a change to a series' rule is not yet represented. Ownership
(`own` vs `shared`) is recorded and not yet read by any judgement. No
webhooks: incremental polling on the existing queue. One wired write
capability remains `calendar.write` from V3.9 — Sprint 1 added no actuators.

Sprint 1 closed. Its four declared debts are addressed in Sprint 2, above.


## V3.9 — PERSONAL AGENT / ACTION ENGINE — CLOSED

ORA does not only work out what should happen. It makes it happen, inside an
authority somebody actually gave, and it checks afterwards whether the world
agrees.

    ORA DOES NOT JUST KNOW WHAT TO DO. ORA CAN DO IT.
    THE USER DOES NOT MANAGE THE AGENT. THE AGENT MANAGES THE WORK.
    AUTONOMY MEANS FEWER QUESTIONS, NOT FEWER SAFEGUARDS.
    AI DECIDES WHAT SHOULD BE DONE. CODE ENFORCES THE AUTHORITY CEILING.
    EXECUTED != VERIFIED. PROVIDER ACCEPTED != OUTCOME ACHIEVED.

**Sprint 1 — Autonomous Goal Foundation.** `AutonomousGoal` is an outcome with
criteria anybody could check, never a task; `NO_GOAL` is the ordinary answer
and stays comfortable. A plan is state rather than a script: steps name a
capability, never a function, and code resolves that to something that exists
and that this person allowed. `ActionIntent` is written before anything
happens, carrying an idempotency key derived from what the effect *is*.
`AuthorityAssessment` keeps the model's reading and code's decision apart,
because they disagree and the disagreement is what an audit needs.

**Sprint 2 — Real Capability Execution.** Capabilities read real collections
and report finding nothing as a result. `ResultProvenance` makes `simulated`
structurally unusable as evidence, and a goal cannot complete on it. The loop
chooses what is worth doing next from what it has learned rather than walking
a list. `OutcomeVisibility` separates "is this worth showing" from V3.8's "is
this worth interrupting", so useful work stops disappearing into silence, and
`CommunicationNeed` lets a blocked agent be reached without inventing an
Opportunity to carry it.

**Sprint 3 — Autonomous Authority & Real-World Action.** The first real write:
`calendar.write`, chosen because it is reversible, costs nothing, commits
nobody, reaches nobody else and — the property that decided it — can be read
back. Authority is scoped by `ActionEffect` and bound to it by `effect_hash`,
so a yes stops applying when the act changes. Grants are scoped, revocable and
never wider than what was approved; matching them is arithmetic and is never
asked of a model. Authority is rechecked in the last moment before the
provider, claimed atomically, receipted, and read back — and a goal closes on
what the calendar said, not on what the request hoped.

**Micro-fix — explicit command authority.** Somebody who writes «segnami un
evento domani alle 10» is not asked whether they want an event tomorrow at
ten. Their own instruction is the authority for that one act: bound by hash,
spent once, and only ever for effects that reach nobody, cost nothing and
destroy nothing. The model must quote their words; code looks the quote up in
the message that actually arrived.

**Final gate — a permission somebody can give and take back.** «Puoi farlo da
sola anche in futuro» sits quieter and apart from the two answers to "shall
I", because it is a different question. It produces one grant, scoped to the
effect that was on screen, described in a sentence with its limits in it, and
it is offered only for acts small enough to decide in two seconds. Permissions
are listed and revoked in Permessi e accessi, in the words that were agreed
to. Revocation is forwards only and is rechecked where the effect happens.

**Defects this phase found in code that was already shipped.** The agent asked
the permission registry about a connector called `calendar`, which has never
existed — so every real person resolved as not permitted to write to a
calendar they had connected, invisibly, because the only fixture exercising it
granted the same wrong name. `build_google_event_body` sent `end = start` for
any event without an explicit end, producing zero-length entries that the
provider accepted and the read-back confirmed. A one-time consent was never
spent when a standing permission was what the executor acted on, so revoking
the permission left a forgotten yes that authorised the same act again.

**Accepted debt.** The one wired write is `calendar.write`; nothing sends,
pays, publishes or deletes. Cancelling an event always proposes first. There
is no way to widen a grant from the UI, by design, and no screen for granting
one outside the moment ORA asks. Device QA remains deferred with V3.8.

Next: V3.10 — Connected Life. Sprints 1, 2 and 3 closed (above); phase open.


## V3.8 — AMBIENT PRESENCE & INTELLIGENT DELIVERY — CLOSED

ORA works when nobody is looking, and can say so without pretending. It wakes
itself, re-examines what it decided, and reaches somebody outside the app only
when a judgement — made again at that moment — says the interruption is worth
what it costs them.

    ORA SHOULD FEEL ALIVE BECAUSE IT IS WORKING, NOT BECAUSE IT PRETENDS TO BE.
    INTERRUPTION MUST BE EARNED.
    A PUSH MUST HAVE A REAL REASON TO OPEN ORA.
    WAKE != NOTIFY.
    PRESENCE IS CONTEXT, NOT A TRIGGER.
    TIMING IS AN AI JUDGMENT.

**Sprint 1 — Alive Presence Foundation.** `AmbientActivity` records work that
really ran, and is the only thing that entitles a surface to say anything: no
record, no line, checked by a test. The Delivery Judgment is AI-first and
four-way — `silence | quiet_presence | in_app | push` — four decisions rather
than four rungs, so nothing derives a push from a card. `DeliveryPlan` is an
intention, never a promise: it is re-examined before anything leaves, and a
concern that closes cancels it. The notification channel sits behind a
`NotificationProvider` boundary the reasoner cannot reach.

**Sprint 2 — Ambient Runtime.** `AmbientWake` is an alarm with no opinion:
reasons are technical (`state_changed`, `delivery_recheck`,
`opportunity_revisit`, `ambient_review`, `retry`) and none names a domain. A
small loop claims exactly one wake at a time through an atomic
`find_one_and_update`, so two backend processes racing produce one winner and
a dead worker's lease expires rather than stranding the work. Wakes are both
event-driven and time-driven, and reaching one sends nothing — the plan is
re-judged first. `expo-notifications@~0.32.17` is configured through the config
plugin with no native folders in the repo; push endpoints, token lifecycle and
per-device failure handling are implemented behind the same boundary. Retries,
backoff and startup recovery are code's, never asked of a model.

**Sprint 3 — Reliability & Notification Policy.** A fallback catches what the
event path drops without becoming a cron AI: eligibility is answered with
indexed counts, has no way to reach a model, and produces a wake rather than a
conclusion. An empty life costs nothing. The sweep is protected by a database
lease and is rare per person, with the sweep cadence and the per-person
interval as two separate settings. After downtime, leases are released and
stale plans expired — every survivor is re-examined under the ordinary rate
limits, so a restart is not a burst. People can say how much they want to be
interrupted and set quiet hours; both travel to the judgement as facts, and no
branch anywhere maps a level to an outcome. Delivery history is qualitative
counts — never a rate, never an engagement score — and the history of one
concern is kept apart from notifications at large. "Non notificarmi per questa
cosa" is a veto enforced by code and deliberately distinct from dismissing the
concern, which goes on living wherever it was. `opened` is a moment we know;
"not opened" is never called "dismissed". `what_decided_the_mode` records why
one channel beat the alternatives, so a delivered notification can be
explained afterwards.

**Accepted debt.** Notification preference semantic influence is structurally implemented but not yet empirically demonstrated. The user's interruption preference is available to the Delivery Judgment and is explicitly instructed to materially influence genuinely borderline delivery choices. Current live QA did not demonstrate a mode change or explicit preference contribution. No deterministic mapping was introduced. Revalidate during broader Production Behavioral QA.

**STRUCTURALLY READY != DEVICE VERIFIED.** No phone, no EAS build, no real
push token, nothing proven to reach a device. `extra.eas.projectId` is still
absent. Production Device QA remains deferred to the final phase.

Next: V3.9 — Personal Agent / Action Engine. Closed (above).


## V3.7 — PROACTIVE OPPORTUNITY INTELLIGENCE — CLOSED

ORA decides for itself whether anything in a life is worth saying, and
separately whether this is the moment to say it. Both are model judgements.
Code holds identity, arithmetic, bounds and persistence, and nothing else.

Principles this phase is built on, to be preserved:

    PROACTIVITY IS AN AI JUDGMENT, NOT A RULE TRIGGER.
    A CHANGE EARNS A REVIEW, NOT ATTENTION.
    OPPORTUNITY != WORK != NOTIFICATION != ACTION.
    SILENCE IS A VALID DECISION.

**Sprint 1 — AI-First Opportunity Foundation.** `OpportunityCandidate` →
`Opportunity` → `OpportunityDecision`. Judgements are words a person could
argue with (`low|medium|high`, `none|soon|urgent`, `weak|reasonable|strong`),
never numbers. Every claim must cite a fact that was actually supplied;
anything else is dropped. Identity is a unique index, so the same concern
noticed twice updates instead of arriving twice. Silence writes nothing, and
an unreachable model is reported as an outage rather than recorded as a
judgement that there was nothing to say.

**Sprint 2 — Continuous Discovery & Quiet Surfacing.** Domains record a
`MeaningfulChange` — facts only, with no field for saying that something
matters — and that earns a review, never a card. Admission is mechanical:
duplicates, coalescing, staleness, a cooldown and a snapshot fingerprint, all
of which answer "would the model be asked the same question twice?" and none
of which has an opinion about importance. The review runs on the existing
Continuous Life Reasoning wake-up; there is no second orchestrator. What
survives is then put to a second, separate judgement — surface, hold or
retire — and what a person sees is a quiet line inside Home →
Aggiornamenti, at most two, in human words. No tab, no push, no toast.

**Final micro-fix — contextual defer.** "Più tardi" no longer means six
hours. How long later lasts depends on what the thing is waiting on, so the
model decides and its reason is kept. When the model cannot be reached the
card is held briefly and that hold is recorded as `technical_retry_hold` —
explicitly not a judgement — so a later pass can tell an unanswered tap from
a considered one. A revisit time is eligibility for quiet in-app surfacing;
nothing is scheduled and nobody is notified.

Verified structurally: no domain trigger rules (guarded by walking the AST of
the discovery path for any branch on a domain name), no numeric scoring, no
work created, no notifications, no actions, evidence fail-closed, dedupe and
suppression, code-made expiry as the only automatic transition, Home capped at
two, provider failure fail-closed on both judgements. Verified live: silence
on a change with no consequence, a grounded opportunity, its surfacing
decision, dismissal not re-raised, and resolution removing the card.

Next: V3.8 — Ambient Presence & Intelligent Delivery. Closed; see above.


## V3.6 — CLOSED

Verified live: Google Routes (live ETA, traffic-aware), Places API New
(autocomplete + resolution), Maps JavaScript API (picker with manual
override). Verified structurally: presence zones, hysteresis, dwell, sessions,
time-at-place, transitions, observed commute, routines, state sync,
user-confirmed presence, native runtime, event dedupe, geofence sync, privacy
controls.

**Native background implementation complete. Real-device validation deferred
to final ORA Production Device QA.** No production-native claim is made until
that QA runs; the checklist is in ARCHITECTURE.md.

Next: V3.7 — Proactive Opportunity Intelligence. Closed; see above.

## V3.6 Final — Native Presence & Live Routing

Shipped: `expo-location@~19` + `expo-task-manager@~14` installed and configured
through the config plugin, `presenceTask.ts` (module-scope tasks, decides
nothing), `presenceBuffer.ts` (offline queue, ordered flush), `presenceRuntime.
ts` (two-step permissions, region sync, reconciliation, shutdown), `event_id`
idempotency end to end, Presence Intelligence toggle in Profilo → Permessi,
`eas.json` with a development profile.

BLOCKED, and deliberately not worked around:
- Native device QA. No EAS project (`extra.eas.projectId` absent), no eas-cli
  login, no device, no emulator, no Android SDK. `eas init` + `eas build
  --profile development` on a real phone is the remaining step.
- Live routing. `ROUTING_PROVIDER` / `ROUTING_API_KEY` are not set, so the live
  ETA path is unexercised. The honest-refusal path is tested.

## V3.6 Sprint 3 — Routines, Time at Places & Commute

Shipped: `places/analytics.py` (window clipping, open sessions, visits,
transitions, median/percentile journey stats, day shape), `places/routing.py`
(provider abstraction + Google Routes v2 adapter, off unless configured),
`ObservedRoutine` read by the model and stored as candidate, five capabilities
(`get_current_place`, `get_time_at_place`, `get_journeys_between_places`,
`get_day_patterns`, `get_route`), presence in the Context Broker under its own
category, weekly summary in Vita and in the place detail.

Debt, named: no routing provider is configured in this environment, so live ETA
is unexercised in QA — the abstraction and the honest-refusal path are tested,
the live path is not. `expo-location` / `expo-task-manager` still not installed
(Sprint 2 recipe stands). Routine acceptance (candidate → accepted) has no UI
yet.

## V3.6 Sprint 2 — Presence Zones & Enter/Exit

Shipped: `PresenceZone` (two radii, exit > entry enforced at construction),
`places/presence.py` (pure, synchronous state machine: outside / pending_enter
/ present / pending_exit), `PresenceSession` with one-open-per-place
idempotency, ambiguity for overlapping zones, accuracy judged against the zone
it is used against, presence primitives (current, last entered, last exited,
current duration, total in a bounded window), place detail screen, per-place
and global history erasure, `suppressed` candidates that survive forgetting.

Not built: routine prediction, weekly analytics, commute prediction, proactive
notifications, in-app turn-by-turn, automatic home/work inference.

Native: `expo-location` / `expo-task-manager` are NOT installed. The exact
recipe is in ARCHITECTURE.md; it is compatible with this managed/CNG setup but
needs a native build to verify, so it was left as a decision rather than an
unverifiable dependency.

## V3.6 Sprint 1 — Places Foundation

Shipped: `places/` (models, geometry, repository, service, reasoning,
navigation, caps, router), five capabilities, `Vita → Luoghi`, place questions
on the V3.1 open-question engine, deep-link handoff to Google / Apple / Waze.

Deliberately not built yet: routine analytics, time-at-home, commute
prediction, proactive location notifications, background location, in-app
turn-by-turn, a full map. Sprint 1 is the foundation those need.

Known gap, named rather than hidden: there is no travel-time or route
capability, so "quanto ci metto ad arrivare a lavoro?" resolves the place and
then says plainly that it cannot compute the journey. That is the honest answer
until a routing capability exists; it is not a silent failure.

Stack limit: no `expo-location`. Background presence, geofencing and OS dwell
events need a native build and are not simulated on web.

## V3.3 — Work admission (ingestion creates no work)

- `backend/home/work_admission.py`: `WORK_REASONS`, `KNOWLEDGE_SOURCES`,
  `ATTENTION_HORIZON_HOURS`, `reason_to_act()`, `admit()`.
- `backend/home/service.py`: `admit()` applied in `build_home` right after
  `gather_all`.
- `backend/home/adapters/document_uncertainty.py`: `blocking_uncertainty()` —
  the only producer of a document question, and it names the field.
- `backend/home/adapters/documents.py`: the review card is gone; a question
  replaces it when there is one, titled with the question. Admin items declare
  `work_reason="deadline"`.
- `backend/home/adapters/event_candidates.py`: candidates declare `consent`
  (or `confirmation_required` when uncertain); the horizon decides when.
- `backend/home/adapters/document_actions.py`: `_ORA_BOOKKEEPING`
  (`create_reminder`, `needs_review`) never becomes a Home item.
- `backend/documents/intelligence/analyzer.py`: the deadline label no longer
  appends a currency the amount already carries ("512,40 EUR EUR").
- Tests: `backend/tests/test_work_admission_v33.py` (17), run against real
  documents in Mongo through the real `build_home`. Seven mutations proven.

## V3.5 — Comparison & Recommendation

- `backend/comparison/models.py`: `ComparisonNeed`, `Alternative`, `Attribute`,
  `ComparisonCriterion`, `Constraint`, `Computation`, `ConstraintCheck`,
  `AlternativeAssessment`, `TradeOff`, `ConditionalChoice`, `Recommendation`,
  `ComparisonRun`.
- `backend/comparison/reasoning.py`: `frame_decision`, `assess_alternatives`,
  `recommend`, `explain_change` — model calls, structured output, validated.
- `backend/comparison/arithmetic.py`: six generic operations; a missing input
  is never zero.
- `backend/comparison/constraints.py`: stated relation against stated value;
  unknown is not breached; a unit mismatch is not a comparison.
- `backend/comparison/service.py`: the order of operations, guardrails,
  research integration, persistence, revision.
- `backend/comparison/repository.py`: `comparison_runs`, owner-scoped reads.
- `conversation_engine/ai_core/`: `ComparisonNeed`, `response_mode="compare"`,
  `reasoning_status="needs_comparison"`, governance, the loop branch.
- Tests: `backend/tests/test_comparison_v35.py` (31).

## V3.4 — Accepted debt

1. **Conflict UX never captured in a real screenshot.** The `conflicted` path
   is covered by tests; live, the assessor reached `insufficient` instead —
   three rounds, each rejecting a source as the wrong kind for the claim, and
   no citations because nothing was grounded. Prudent behaviour, and the same
   family of honesty; the visual proof of a declared conflict is still owed.
2. **A window with a hard upper limit is not fully distinguished downstream.**
   "Entro il 20 novembre" keeps its `latest`, but Home and Attention do not yet
   treat a deadline-shaped window differently from an open one. Not corrected
   here. No exact date is invented in either case.
3. **Free-tier Groq/Mistral rate-limit an intensive Research loop.** One turn
   is many calls in a few seconds. `Retry-After`, cooldowns and a bounded
   pacing wait handle it; capacity is still the limit under QA load.
4. **Cross-suite event-loop contamination in very large pytest batches.**
   Pre-existing, A/B-verified against HEAD; every suite passes alone and in
   pairs.

## V3.4 — Provider chain

- `backend/llm/providers/groq_provider.py`: wired in; default model
  `qwen/qwen3.8-27b`; typed failures on both the SDK and httpx paths.
- `backend/llm/providers/mistral_provider.py`: new, same shape; default model
  `mistral-small-latest`.
- `backend/llm/providers/__init__.py`, `backend/llm/manager.py`:
  `DEFAULT_PRIORITY = (gemini, groq, mistral, openai, ollama, emergent)`;
  `COOLDOWN_SECONDS["rate_limit"] = 4.0`.
- Keys read from the environment only — never persisted, never logged, never
  in the repo.
- Tests: `backend/tests/test_provider_failover_v34.py` (19).

## V3.4 — Universal Research Intelligence

- `backend/research/models.py`: `ResearchNeed`, `ResearchPlan`,
  `ResearchQuestion`, `EvidenceSource`, `EvidenceClaim`, `ResearchConflict`,
  `ResearchAssessment`, `ResearchSynthesis`, `ResearchRun`.
- `backend/research/reasoning.py`: `plan_research`, `assess_evidence`,
  `synthesize`, `consider_reuse` — four model calls, structured output,
  validated and trimmed to the contract, never replaced by a fallback.
- `backend/research/service.py`: the loop and the guardrails
  (`MAX_ITERATIONS=3`, `MAX_QUERIES=8`, `MAX_SOURCES=24`, dedupe, one retry).
- `backend/research/repository.py`: `research_runs`, owner-scoped reads.
- `conversation_engine/ai_core/models.py`: `ResearchNeed`,
  `response_mode="research"`, `reasoning_status="needs_research"`.
- `conversation_engine/ai_core/governance.py`: the mode is legal and requires a
  need; without one it degrades to `answer`.
- `conversation_engine/ai_core/loop.py`: the research branch — budget, work
  refs carried through, citable sources into `public_sources`,
  `memory_eligible: False`.
- `conversation_engine/ai_core/tools/registry.py`: `web_search` hidden from
  cognition, still executable.
- `backend/life_os/models.py`: `TemporalTarget`, `LifeOsPlan.target`.
- `backend/life_os/service.py`: `_temporal_target`; `target_date` filled only
  from `exact_day`.
- `backend/home/adapters/conversation_adapter.py`: a session is work only when
  it left a plan, a guided flow or a V3.1 open question.
- `backend/home/adapters/life_os_plan.py`: `goal_target_said` /
  `goal_target_precision`; no `due_at` from a window.
- `backend/research/models.py`: `ClaimScope`, `EvidenceClaim.person_evidence_used`,
  `ResearchQuestion.source_fitness`.
- Tests: `test_research_v34.py` (40), `test_conversation_work_v34.py` (10),
  `test_temporal_precision_v34.py` (13).

## V3.3 — Post-setup attention continuity

- `backend/ai_life_strategist/models.py`: `BenefitDescriptor.grounded_by`.
- `backend/ai_life_strategist/benefit_engine.py`: `active_benefits()` skips a
  benefit whose `grounded_by` keys are all unknown; eleven catalogue entries
  declare their grounding (every claim whose Home copy promises to follow,
  watch or remind).
- `backend/home/adapters/life_setup.py`: benefit items are `priority="later"`
  with `meta.knowledge_only = True`.
- `backend/home/service.py`: `_focus_eligible()` rejects `knowledge_only`, and
  the focus fallback draws from a pool filtered the same way.
- `backend/home/ranking.py`: `GENERIC_ENTRY`; a declared non-generic route
  survives ranking as the primary action.
- `backend/action_engine/service.py`: `_intent_declared_by_card_type` +
  `_CARD_TYPES_THAT_NAME_AN_ARTIFACT` (`needs_review`, `verify`), consulted in
  `_intent_from_body` before the text classifier.
- `backend/life_profile/guided.py`: the non-ownership branches of
  `casa.situazione` write `casa.owned: False`.
- Tests: `backend/tests/test_post_setup_attention_v33.py` (9), plus two guards
  in `test_life_profile_v33.py` for branch recording and for branches that
  would leave an objective nothing can ask again.
- Known and accepted: `studio.esame`, `salute.visita` and `animali.pet` are not
  asked by the guided setup, so those areas cap below 100% until a conversation
  or a document fills them. Deliberate — a first setup is not the place for a
  date that changes every term.

## V3.3 — Guided Life Setup (first access rebuild)

- `backend/life_profile/guided.py`: declarative catalogue — objective, question,
  control type, options, what each option `sets` and what it marks
  `not_applicable`, dependencies, weight, sensitivity, document alternative.
  All business logic; the frontend renders.
- `backend/life_profile/setup.py`: the sequencer. One current area, next
  objective derived from known facts + declined + not-applicable +
  dependencies, explicit transitions between areas, `finish` ends the first run
  (and marks the session terminal so the gate lets the person through).
- Endpoints: `GET /life-profile/setup`, `POST /life-profile/setup/answer`
  (`answer` | `skip` | `decline`), `/setup/skip-area`, `/setup/go-to-area`,
  `/setup/finish`.
- `frontend/src/life-setup/GuidedSetupScreen.tsx` replaces the conversational
  screen at `/life-setup`: nav rail, title, Profilo Vita, PERCORSO list,
  current-area card with step progress, option cards, "Altro", privacy note,
  "Salta questa area" / "Avanti", right rail with every area's state, "Salta
  per ora", and the "ORA cresce con te" banner. One column below 1000px.
- Ten areas in the agreed order: Casa · Lavoro · Studio · Mobilità · Famiglia e
  relazioni · Patrimonio · Finanze · Assicurazioni · Utenze e servizi · Salute.
  Studio is now its own area.
- Identity: asked once before the areas, only when the account has no usable
  name, written to `db.users.name` — the identity Home, the rail and the
  profile all read.
- The conversational `LifeSetupConversationScreen` stays in the tree: it owns
  the document flow and the resume path, and a rollback should not need a
  rewrite.
- Tests: `backend/tests/test_life_profile_v33.py` — 42.
  `frontend/.../lifeProfile33.test.ts` (`npm run test:v33`).

## V3.3 — Progressive Life Setup & Life Profile

- New module `backend/life_profile/`: `areas.py` (8 areas over existing gap
  domains), `objectives.py` (five states + latent/conditional resolution),
  `completeness.py` (weighted arithmetic, no model calls), `service.py` (read
  model), `router.py` (`GET /life-profile`, `GET /life-profile/areas/{id}`,
  `POST /life-profile/not-applicable`).
- Knowledge objectives are read from `ai_life_strategist.knowledge_gap.
  DOMAIN_GAPS` (weights + `when` dependencies) and `minimum_life_context.
  NUCLEUS_EVIDENCE_KEYS` (foundations). No second catalogue, no second store.
- States: known · inferred · declined · not_applicable · unknown. Skipping is
  not a state — it leaves the objective unknown. **Only `not_applicable` leaves
  the denominator**; a declined objective stays counted as missing and is never
  asked again. Latent objectives (gate unanswered) are not counted until they
  apply — unless ORA already knows them, which evidently makes them apply.
- Nine areas: Casa · Lavoro · Mobilità · Famiglia e relazioni · Finanze ·
  Patrimonio · Assicurazioni · Utenze e servizi · Salute. Patrimonio is new
  (other property, loans, savings) over a new `patrimonio` gap domain.
- `LifeSetupSurface` wraps the first conversation: welcome, promise, profile,
  current area with its open objectives as chips, other areas, privacy note,
  leave. Two columns past 900px, one below. Nothing typable except the composer.
- Objectives can be satisfied under alternative names (`satisfied_by`): the MLC
  nuclei for the foundations, and document keys (`doc.bolletta`,
  `doc.polizza_*`) for what a document answers.
- `life_setup` already distinguished `refused_keys` (declined) from
  `postponed_keys` (skipped); V3.3 consumes both rather than adding a third.
- Frontend: `src/components/life-profile/LifeProfileProgress.tsx` in the first
  run (refreshed after every turn) and in Vita (tap an area to resume);
  `api.lifeProfileCompleteness` / `api.lifeProfileNotApplicable`.
- Gate: `isFirstRunOver` (completed | skipped | cancelled | interrupted) lets a
  person into the app. Skipping everything no longer loops back to onboarding.
- Extractor fixes found live: negated mentions ("senza mutuo", "non ho la
  macchina") are recorded as `False` instead of `True`; "la casa è di mia
  proprietà" is now recognised.
- Not built here: Opportunity Engine, Connected Life, new connectors, cron,
  notifications, research. The profile models the facts those will need.
- Tests: `backend/tests/test_life_profile_v33.py` — 28.
  `frontend/src/components/life-profile/lifeProfile33.test.ts` (`npm run
  test:v33`).

## V3.2 — Life Guidance Intelligence

- New module `backend/guidance/`: `models.py` (GoalState, Milestone, Variable,
  NextStep, Sufficiency), `resolution.py` (know before asking), `questioning.py`
  (bundling), `service.py` (reconstruct / assess / evaluate), `bridge.py`
  (MissingInformation ↔ Variable, and the V3.1 ask payload).
- Four capabilities: **State Reconstruction** (`GoalState`, residual path only),
  **Dynamic Path Planning** (milestones bound to existing `plan_item_id`s; no
  second plan), **Information Sufficiency** (only `required` + unknown blocks),
  **Next Best Step / Minimum Necessary Questioning** (one bundle, ≤ 7, least
  sensitive first).
- Cognitive contract additions: `MissingInformation.necessity | label |
  blocks_step`, `CognitiveDecision.goal_state`. `necessity` defaults to `None`
  so "unstated" stays distinguishable from an explicit `useful`.
- `governance.validate_decision` validates and forwards `goal_state`; it rebuilds
  the decision from an allowlist, so an unnamed field would be dropped.
- Loop gate in `ai_core/loop.py` before the ask is appended: resolve, then either
  feed `INFORMATION_ALREADY_KNOWN` back to the model and re-decide, or emit a
  bundled ask. Guidance failing never costs a turn — the model's own question
  is asked.
- AI-Core state: `guidance_state` (the reconstruction, carried across turns) and
  `resolved_refs` (what this turn resolved). Not `clarification_history`, which
  is the loop's attempt counter.
- V3.1 integration: `OpenQuestion.requested_variables` (so a partial answer is
  readable), `blocking_ask.avoided` (observability only, never shown), and
  `WaitingService.resolve_by_knowledge`, which supersedes an open question only
  when *all* of its refs became known.
- Domain neutrality is a test, not a convention: an AST walk fails on any
  domain-named symbol, and the same engine is proven on an unrelated goal.
- Not built here: web search, crawling, offer engines, comparators, commercial
  providers. V3.2 reasons over what ORA already holds.
- Fixed during live QA, each with a regression test: resolution required only
  partial token overlap (naming a thing resolved its value) and ignored Italian
  elision; ORA's own situation/plan records counted as evidence; a blocked
  `act` discarded the reasoning's question for a generic apology; a composed
  question grafted the reasoning's prose into a template.
- Product behaviour gate: `guidance/wording.py` (meta-choice + language checks),
  a loop nudge that hands the step back to ORA when it hands it to the person or
  asks for something it marked non-required, "Domande per te" reduced to real
  `OpenQuestion`s on both surfaces (`activity/presentation.py`,
  `app/(tabs)/index.tsx`) with one count behind every number, and the attention
  headline written in the user's language.
- Execution invariant: GUIDANCE MUST EITHER ADVANCE THE WORK OR ASK FOR WHAT
  BLOCKS ADVANCEMENT. Five dead ends are detected and corrected in-turn
  (described plan · premature conclusion · non-required ask · blocked from
  re-asking · action refused without a question), at most two corrections per
  turn. The composed question also replaces the visible one when guidance
  rejected or narrowed what the model wrote.
- Turn/question consistency: the thread text and the stored `OpenQuestion` are
  one sentence; the ask carries `step_title` / `milestone_ref` /
  `plan_item_id` from the guidance decision, so `context_label` and
  `WorkRefs.plan_item_id` cannot drift to the focused plan item; every turn on
  live work is classified as `guidance_outcome` (ask · act · complete ·
  continue · limbo) and exposed in the public trace.
- Tests: `backend/tests/test_guidance_v32.py` — 58, covering scenarios A–J, the
  V3.1 bridge, sensitive-value redaction, domain neutrality, a no-network guard,
  5 loop-integration tests and the four live findings above.

## V3.1 — Conversation Resume Intelligence (WAITING_USER)

- New module `backend/waiting/`: `OpenQuestion` (models), `open_questions`
  collection (repository), lifecycle + continuation (service), HTTP surface
  (router). Registered in `ALL_ROUTERS`; indexes built at startup.
- Question lifecycle: `open → answered | cancelled | superseded`. Continuation
  is a second axis (`pending | running | done | failed`) so an accepted answer
  is never lost to a failed resume.
- Created from `conversation_engine/ai_core/orchestrator.py` when a turn ends on
  a question the reasoning marked blocking (`CognitiveTurnResult.blocking_ask`).
  Soft-failing: a question that cannot be persisted never costs the user a turn.
- Endpoints: `GET /questions/open`, `POST /questions/{id}/answer`,
  `POST /questions/{id}/retry`, `POST /questions/{id}/cancel`.
- `HomeResponse.open_questions` and Activity's `questions` rows
  (`kind: "question"`) are projections of the same entity — no second store.
- Frontend: Home and Activity route "Rispondi" through
  `buildOraConversationHref({ sessionId, questionId, entryPoint: 'question' })`;
  the ORA composer sends that first message through `api.answerQuestion` rather
  than the generic turn, then re-reads the thread from the server.
- Not built here (V3.2): state reconstruction, dynamic path planning, an
  information-sufficiency engine, any research capability. V3.1 is the
  continuity those need.

## V2.8.3a — Provider Reliability & Error Taxonomy

- Provider order remains Gemini → OpenAI → Ollama → Emergent.
- `LLMNotConfigured` now means only that no provider is enabled/configured;
  exhaustion of a configured chain raises `LLMProviderUnavailable` with
  bounded sanitized attempt kinds.
- External quota/rate/timeout/network/auth/model/protocol failures are typed
  and fail over. Unknown internal ORA/adapter errors fail fast and cannot be
  hidden by another provider.
- Recent failures drive an in-memory, per-process cooldown. There is no Redis,
  polling, blocking sleep or additional provider call. Status is a passive
  snapshot (`unknown`, `healthy`, `degraded`, `cooldown`, `disabled`).

## V2.8.3 — Memory Proposal & Governed Learning

Final provider-real gate: explicit Memory authorization now remains authoritative after
an empty bounded lookup; correction/forget must retrieve the governed Memory ref and reuse
its canonical `identity_key`. A terminal runtime guard blocks unpersisted Memory claims if
the model exhausts its reasoning budget. Provider-real PROMOTE, temporary/inference
isolation, cross-session correction/supersession and targeted Forget are green.

| Item | Stato |
|------|--------|
| `MemoryCandidate` AI-owned, optional, bounded | **implemented** |
| Governance PROMOTE/CLARIFY/REJECT/SUPERSEDE/FORGET | **implemented** |
| Temporary Situation → no durable Memory | **enforced** |
| Tentative/inferred/device evidence → no silent promotion | **enforced** |
| User-scoped correction, history, revision, logical forget | **implemented** |
| Same-turn idempotency / cross-turn learning | **implemented** |
| Context Broker cross-session read of promoted Memory | **implemented** |
| Stage A Memory existence index / Stage B governed target metadata | **implemented, bounded** |
| Persist-before-claim and post-write result consistency | **enforced** |
| Second LLM / domain router / new dependency | **none** |
| Live gate on canonical local backend `:8000` | **passed** |

Last updated: 2026-08-18 (V2.8.3a provider reliability)

## V2.8.2 — Context Broker V3

| Item | Stato |
|------|--------|
| `ContextNeed` AI-owned e backward-compatible | **implemented** |
| Life Context source registry | **implemented** |
| Profile / Memory / Situation / Life OS / Goals / file / calendar | **bounded adapters** |
| Presence automatica | **forbidden; capability required** |
| Authority, provenance, conflicts, diversity, budget | **preserved/enforced** |
| Stage A minimized + Situation detail signal | **implemented** |
| Source failure honesty + safe observability | **implemented** |
| Second LLM/domain router/new dependency | **none** |
| Deterministic core regression | **246 passed** |
| Real-provider generality/conflict eval | **4 passed** |
| Final product QA | **passed in integrated browser** |

Last updated: 2026-08-17 (Google Login V2 multipiattaforma — uncommitted)

## Google Login V2 — GIS web + native SDK (this batch)

| Item | Stato |
|------|--------|
| Web Google Identity Services lazy/popup | **implemented** |
| iOS/Android `@react-native-google-signin/google-signin` | **implemented; device not tested** |
| Login missing config → no crash; Email/Register available | **covered by regression test** |
| Settings link/unlink via same adapter | **implemented** |
| JWT persistence atomic before user/routing | **implemented** |
| Explicit backend audience allowlist + documented legacy fallback | **implemented** |
| JWKS temporary failure → controlled 503 | **implemented/tested** |
| Google Login ≠ Google Calendar OAuth | **enforced/documented** |
| Frontend auth regression | **8 passed** |
| Backend social auth | **20 passed** |
| V2.7.1 Home handoff + location regression | **52 passed** |
| TypeScript / lint / Expo web export | **ok** (lint: 42 pre-existing warnings) |
| Real GIS / native OAuth | **not completed** — browser runtime unavailable; native build absent |
| Commit / push | **NO** |
| stash@{0} | **untouched** |

## Prompt V2.7.1 — Home → ORA first-turn handoff (this batch)

| Item | Stato |
|------|--------|
| Root cause: start response discarded; mount ignored pending client_actions | **fixed** |
| Generic `pending_turn` on GET (not location-specific) | **yes** |
| Mount fulfills awaiting_client once → client-resume | **yes** |
| message_id identity; no text-only history dedupe | **yes** |
| Home Ask ≡ in-ORA send (one user turn) | **yes** (unit) |
| Live Home → Dove sono / Come mi chiamo | **pending CPO** |
| Handoff + location tests | **52 passed** |
| V1→V2.6.2 focused | **45 passed** |
| TypeScript | **ok** |
| stash@{0} | **untouched** |
| Commit / push | **NO** |

## Prompt V2.7.1 — STALE → fresh foreground refresh (prior)

| Item | Stato |
|------|--------|
| Root cause: STALE `needs_client` without usable `client_action` / loop pause | **fixed** |
| STALE + while_using → `request_foreground_location` (`refresh`) | **yes** |
| Browser granted + ORA while_using → direct `getCurrentPosition` (no sheet) | **yes** |
| `maximumAge: 0` on refresh; default 60s otherwise | **yes** |
| timeout / denied / unavailable / POST failure distinct | **yes** |
| pending_client_capability generic retry (no hardcoding “prova ora”) | **yes** |
| Place-label resolver | **unchanged** this batch |
| Unit tests location v271 | **46 passed** |
| V1→V2.6.2 focused (core + life_os + context_change) | **45 passed** |
| TypeScript `tsc --noEmit` | **ok** |
| Live Chrome re-QA | **partial** — location OK on 2nd in-ORA send; Home first turn blocked until handoff fix |
| Prompt 7.x stash@{0} | **untouched** |
| Commit / push | **NO** — STOP for CPO |

## Prompt V2.7.1 — Foreground location + PresenceContext (prior)

| Item | Stato |
|------|--------|
| LocationSignal short-lived (TTL **2h**) user-scoped | **yes** |
| PresenceContext CURRENT/RECENT/STALE/UNKNOWN | **yes** |
| Web `navigator.geolocation` foreground bridge via `client_actions` | **yes** |
| AI caps: get_current_location / get_current_presence / get_recent_presence_context | **yes** |
| Context Broker minimized presence (≠ residence) | **yes** |
| Settings: Disattivata / Durante l'uso — background **not available** | **yes** |
| Quiet Premium permission sheet (no silent launch request) | **yes** |
| Native foreground (`expo-location`) | **unsupported** (not installed) |
| Background tracking / geofencing / proactive / routines | **NOT implemented** |
| MeaningfulPlace / home-work inference / TravelFlow | **NOT this slice** |
| Device must not overwrite residence | **enforced** |
| Raw GPS → Life Memory / Life Map | **never** |
| Unit tests `test_ai_native_location_v271.py` | **pass** |
| V1→V2.6.2 focused regression | **180 passed** (`-n0`) |
| Live browser QA (Dove sono / vivo / deny / stale) | **fix 2026-08-16** — false `disabled_by_user` skipped consent/geo; requires_consent + location nudge |
| Live re-QA after consent fix | **partial** — label Vibo Marina OK; STALE refresh blocked until this batch |
| Place-label precision (locality vs municipality) | **fixed 2026-08-16** — generic resolver; provider supports Vibo Marina at zoom≥14 |
| Prompt 7.x stash@{0} | **untouched** |
| Commit / push | **NO** — STOP for CPO / architecture review |

## Prompt V2.6.2 — Context change & persistent replanning (prior)

| Item | Stato |
|------|--------|
| Root cause: session-persisted `tool_signatures` banned cross-turn `update_*` | **fixed** |
| Turn-scoped reasoning epoch + same-turn duplicate reuse | **yes** |
| Duplicate UX leak ("Sto evitando di ripetere…") removed | **yes** |
| Prompt: new conversational facts ≠ duplicate execution | **yes** |
| `user_fact_summary` → USER_PROVIDED_CONTENT / user_conversation | **yes** |
| Conversational evidence must not supersede user_file | **yes** |
| Live `lop_93e3f8760a2c4e`: 12→5 item reconciled; obj rev 2→3 | **yes** (scripted) |
| Unscripted live LLM proof | **not claimed** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.6.1 — Source-grounded reconciliation (prior)

| Item | Stato |
|------|--------|
| Root cause: `update_plan` only `add_items` (append) — no replace | **fixed** |
| `replace_items` + `reconciliation_mode` + remove_item_ids | **yes** |
| Same plan/object identity; target_date/session preserved | **yes** (live) |
| PlanItem `origin` provenance | **yes** |
| Evidence status active/superseded + public_sources | **yes** |
| Workspace Fonti human labels (no lcf_/doc_) | **yes** |
| GenerativeObjectRenderer uses `useTheme` (light readable) | **yes** |
| Live Matematica: 8 mixed items → 5 official modules; obj rev 8→9 | **yes** |
| Non-study move + quote reconciliation | **yes** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.6 — Files / evidence / context (prior)

| Item | Stato |
|------|--------|
| ContextFile model + Documents V2 storage reuse | **yes** |
| `POST /api/conversation/ai-core/files/upload` (auth, ownership) | **yes** |
| OraComposer real attach (chip, upload, remove, multi, file-only) | **yes** — shared composer |
| AI Core caps: list/get context/content/link | **yes** — no domain handlers |
| Context Broker `session_files` + staged chunks | **yes** |
| Capability honesty + untrusted-file prompt rules | **yes** |
| Evidence refs `USER_PROVIDED_CONTENT` / `user_file` | **yes** |
| Workspace quiet Fonti | **yes** |
| Live scripted QA: same plan `lop_0aecb72a15cf49`, object `lgo_44b1f457f1c247` rev 7→8 | **yes** |
| Live unscripted multi-turn LLM exam PDF in browser | **partial** — needs bearer session; plumbing proven scripted |
| Image multimodal understanding | **unavailable** (OCR text only if extracted; honesty in caps) |
| Orphan upload GC / full Files product UI | **not in scope** — deferred |
| Production object storage (S3/GCS) | **migration path** — still Documents V2 local abstraction |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.5.1 — Blank Home runtime fix (prior)

| Item | Stato |
|------|--------|
| Metro `Unable to resolve "./nav"` / `@/src/ora/nav` | **fixed** — module renamed `oraNav.ts` |
| Blank white `/` from failed bundle | **fixed** |
| Home OraInput still → `/ora` (not `/ora-ai`) | **yes** |
| Cognitive / ranking / Life OS semantics | **unchanged** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.5 — Production ORA surface (prior)

| Item | Stato |
|------|--------|
| Canonical `/ora` + `/ora/{sessionId}` on AI Core | **yes** |
| Home OraInput → AI Core (not CE→AE) | **yes** |
| Ambient ORA tab → AI Core fresh thread | **yes** |
| Goal Workspace Continua → `/ora` + session-focus | **yes** |
| Object “Continua con ORA” binds active_object | **yes** |
| `/ora-ai` DEV-only, shared components | **yes** |
| Quiet Premium Goal Workspace | **yes** (presentation) |
| Nav helpers opaque ids only | **yes** |
| Attachment pipeline in composer | **superseded by V2.6** — real ContextFile path |
| Live Home/ORA/Workspace LLM QA | **partial** — browser often missing bearer; automated ownership/route tests green |
| Home ranking / AI Core loop / Context Broker | **unchanged** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4.3 — GenerativeObject card/reveal fix (prior)

| Item | Stato |
|------|--------|
| Live object `lgo_44b1f457f1c247` audited (rev 7): `card` with empty `front`/`back`, content only in `title` | **yes** |
| Root cause: A+B+D (malformed card + validator allowed empty reveal + FE ignored `title`, always showed “Tocca per rivelare”) | **fixed** |
| Canonical revealable item `{front, back, revealable}` + small alias normalize | **yes** |
| `card_deck` validation rejects missing front/back after normalize | **yes** |
| Single `card` may be static (`revealable: false`) when only title/front exists | **yes** |
| API `GenerativeObject.public()` display-normalize for older shapes | **yes** |
| FE `CardDeck`: no reveal affordance without back; never blank; nav resets reveal; event `reveal` | **yes** |
| Browser Goal Workspace live click | **blocked** — missing bearer token in browser session |
| Live public() QA: title → front, `revealable: false` (no blank reveal) | **yes** |
| Home / AI Core cognition / Context Broker | **unchanged** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4.2 — Persistent GenerativeObject adaptation (prior)

| Item | Stato |
|------|--------|
| Root cause: chat-only answer, no `update_object`, empty object refs in AI payload | **fixed** |
| `active_object_ref` / `recent_object_refs` / `current_plan_item_ref` in session | **yes** |
| Life OS AI payload includes lightweight object previews | **yes** |
| Prompt: durable adapt → `update_object`; conversational-only OK | **yes** (AI decides) |
| Persist-before-claim for “ho semplificato / aggiornato…” | **yes** |
| `update_object`: content/spec/append/remove + revision + evidence preserve | **yes** |
| Workspace interact / Continua → session focus bind | **yes** |
| Live Matematica object `lgo_44b1f457f1c247` rev 1→3 via adaptation path | **yes** (scripted decision_fn on real DB) |
| Live unscripted LLM always calls `update_object` | **partial** — depends on model; nudge + context in place |
| Home ranking | **unchanged** this prompt |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4.1 — Canonical Home ownership (prior)

| Item | Stato |
|------|--------|
| Root cause: past plan deadlines scored as overdue (+Goal boosts) | **fixed** |
| Temporal states ACTIVE / UPCOMING / EXPIRED_* / SUPERSEDED | **yes** (`home/temporal.py`) |
| Ranking `home-rank-1.4` — canonical_active + stale penalties | **yes** |
| Daily Focus prefers actionable LifeOsPlan over expired legacy | **yes** (live QA) |
| Horizon skips EXPIRED_STALE / past dates | **yes** |
| Life OS Home routes → `/goal-workspace/{planId}` | **yes** |
| Continue prefers Life OS resume | **yes** |
| Contesti hides exam-day/past study with no session | **yes** (presentation) |
| DEV rank trace `HOME_RANK_TRACE` / `dev_rank_trace` | **yes** |
| DEV QA cleanup utility (provenance-gated) | **yes** (no auto-wipe) |
| Persistent `update_object` after “spiegamelo più semplice” | **no** — session has no `update_object` tool call |
| Object `revision` bump on update | **yes** (code path; live object never updated) |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.4 — AI-native Generative Workspaces (prior)

| Item | Stato |
|------|--------|
| Closed flashcards/quiz/map artifact cognition removed from AI Core | **yes** |
| `GenerativeObject` + declarative UI primitives | **yes** |
| Capabilities `create_object` / `update_object` / `get_object` / `list_goal_objects` | **yes** |
| Generic FE `GenerativeObjectRenderer` + `/goal-workspace/[planId]` | **yes** |
| Life OS actions never open legacy `/action` | **yes** |
| Stale historical goal demotion (ambiguous exam) | **yes** |
| `generate_artifact` / type-specific generators | **deprecated / removed from registry** |
| Legacy `life_os_artifacts` | **read-only compat** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt V2.3 — Generic Life OS execution (prior; artifact catalog superseded)

| Item | Stato |
|------|--------|
| `life_os` plans/artifacts collections | **yes** |
| Capabilities create/update plan, actions, artifacts | **yes** |
| Evidence calibration (general vs target-specific) | **yes** |
| Home adapter + Continue `/ora-ai` | **yes** |
| Focus Horizon via `due_at` / `goal_target_date` | **yes** |
| Life Map situations | **yes** |
| Staged artifact generation budgets | **yes** |
| Rich text harness `/ora-ai` | **yes** |
| Tests V2.3 A–Z | **yes** |
| Persist-before-claim (Life OS writes) | **yes** (soft re-entry; note_intention insufficient) |
| Live exam → Home + artifacts | **yes** (local Mongo + `/home`) |
| Resume prefers life_os over chat-only | **partial** — plan/actions on Home; resume_item may still be conversation_session |
| Evidence wording always calibrated | **partial** — governance + prompt; model may still overclaim without TARGET_SPECIFIC |
| StudyFlow / domain wizards | **not added** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt 7 V2.2 — General tool use & grounded external knowledge (prior)

| Item | Stato |
|------|--------|
| Tool Registry V2 (capability metadata) | **yes** |
| `web_search` capability | **yes** |
| Provider failover Tavily→Brave→Gemini Search | **yes** (config-dependent) |
| ExternalObservation re-entry | **yes** |
| Tool-before-claim governance | **yes** (prompt + policy) |
| Autonomous READ_ONLY tools | **yes** |
| CONSEQUENTIAL_WRITE blocked | **yes** |
| Query minimization | **yes** |
| `current_facts` temporal scope | **yes** |
| Tests A–J `test_ai_native_tools_v22.py` | **yes** |
| Combined AI-core pytest | **55 passed** |
| Live research QA | **depends on RESEARCH_ENABLED + keys** |
| Prompt 7.x stash | **untouched** |
| Commit / push | **no** — STOP for CPO |

## Prompt 7 V2.1 — Personal context retrieval (prior)

| Item | Stato |
|------|--------|
| Stage A account display name | **yes** |
| Semantic Stage B personal lookup | **yes** (identity/residence/employment/study/general) |
| Provenance + authority reuse (Life Memory bands) | **yes** |
| Context re-entry keeps original question | **yes** |
| Over-broad context query blocked | **yes** |
| No name/residence/job conversation branches | **yes** |
| Tests `test_ai_native_personal_context_v21.py` | **yes** (A–L) |
| Combined AI-core pytest | **34 passed** |
| Live Gemini QA name/residence/work | **yes** — synthetic user: name 1-call; residence/work 2-call |
| Commit / push | **no** — STOP for CPO |

## Prompt 7 V2 — AI-Native Cognitive Core (prior)

| Item | Stato |
|------|--------|
| Package `conversation_engine/ai_core/` | **yes** |
| AI owns cognition (decision contract) | **yes** |
| Context Broker stage A/B | **yes** (upgraded in V2.1) |
| Tool Registry (read + soft note) | **yes** |
| Bounded loop MAX_STEPS=4 | **yes** |
| Governance without domain wizards | **yes** |
| Minimal harness `/ora-ai` + scroll | **yes** |
| Mocked suite `test_ai_native_core_v1.py` | **yes** (20 passed) |
| Web research / Tavily / learning artifacts | **not in scope** |
| Prompt 7.x stash restored | **no** |
| Commit / push | **no** — STOP for CPO |

### Principle

**AI owns cognition. Deterministic systems own capabilities and governance.**

### Abandoned

Prompt 7.x remains in `stash@{0}: backup: abandoned Prompt 7.x cognitive architecture` — do not restore.

## Cognitive Reset — Prompt 7.x abandoned (prior)

| Item | Stato |
|------|--------|
| Working tree restored to HEAD `258cd85` | **yes** |
| Safety stash `backup: abandoned Prompt 7.x cognitive architecture` | **yes** (`stash@{0}`) |
| Cognitive Focus / requirements / research orchestration removed from tree | **yes** (in stash only) |
| New AI-first cognitive engine | **not started** — STOP for CPO |
| Commit / push | **no** |

### Why abandoned

Live QA showed deterministic readiness/requirements/question planners owning dialogue before the LLM: repeated asks, unnatural copy, discriminator loops, research/action at the wrong time. Not fixable by micro-patch.

### Canonical rebuild direction (next prompt — do not implement yet)

**ORA IS AI-FIRST.** The LLM owns goal understanding, what to ask/research/tool/act, and the next conversational turn. Deterministic code validates (auth, schemas, provenance, privacy, idempotency, tool execution, safety) — it does **not** script the conversation via fixed slot sequences.

### V2.8.1 Situation Model V1

| Contract | State |
|---|---|
| User-scoped Situation persistence | **implemented** |
| Cross-session current/recent context slice | **implemented** |
| AI-owned create/update/cancel/resolve/none | **implemented** |
| Runtime ids, ownership, revision, transition validation | **implemented** |
| Same-turn/client-resume idempotency | **implemented** |
| Cross-turn corrections and supersession history | **implemented** |
| Automatic Situation → Memory promotion | **forbidden** |
| Automatic linked plan/object mutation | **forbidden** — AI must use Life OS capability |
| Dedicated Situation UI/Home card | **not implemented by design** |

Target loop (conceptual only): USER → AI orchestrator → structured next action → governance → tool → AI again → response.

### Reusable infrastructure proven in 7.x (capabilities, not conversation architecture)

Gemini provider · Groq provider · Tavily retrieval · Brave fallback · provider failover · source provenance · web evidence · document attachments · StudyPlan persistence · Life Profile · Life Memory · Life Map

### Preserved committed surfaces

Quiet Premium · Home · Shell · Login · Contesti/Life Map · Memoria/Life Memory · Life Setup · auth · canonical backend services · committed Study/Travel services

## Prompt 6.1.1 — Epistemic authority (prior)

| Item | Stato |
|------|--------|
| Life Setup utterance → user_said/confirmed | **yes** |
| Inferred leftover repair (name/home/role keys) | **yes** (idempotent) |
| Account name → known | **yes** |
| GPS/device ≠ known residence | **yes** |
| needs_clarification only if weak authority | **yes** |
| Gemini persona (never “mi chiamo”) | **yes** |
| Commit / push | **no** |

Last prior: 2026-08-10 (Prompt 6.1 — Memory clarification loop)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- Baseline: `9722724`
- No push / no merge unless requested

## Prompt 6.1 — Clarification loop (this batch)

| Item | Stato |
|------|--------|
| Actionable “Da chiarire” | **yes** |
| `POST /life-memory/clarify/*` | **yes** |
| CE `origin=memoria` → Focus clarify (not AE) | **yes** |
| Gemini question + free-text resolve | **yes** (Provider Manager; soft-fail) |
| Governance → Life Profile correct_fact | **yes** |
| Additional facts as suggest only | **yes** |
| Soft language for ambiguous/likely | **yes** |
| Fake Correct/Forget buttons | **no** |
| Home / Contesti / Login / Life Setup / Shell | **frozen** |
| Commit / push | **no** |

## Prompt 6 — Memoria Life Memory V1 (prior)

| Item | Stato |
|------|--------|
| `GET /api/life-memory` deterministic | **yes** |
| Identity + contradiction governance | **yes** |
| Gemini wording (`MEMORY_GEMINI`, default 0) | **yes** (optional) |
| Memoria Quiet Premium browse UI | **yes** (replaces ask-first) |
| FE invent from raw sources on API fail | **no** (honest empty/error) |
| Correct / Forget / Confirm in UI | **clarify loop** (not form editors) |
| Conversation → durable memory promotion | **partial** (clarify path; general CE promotion still gap) |
| Life Objects as Memory evidence | **gap** (hybrid documented; Profile-first V1) |
| Home / Contesti / Login / Life Setup / Shell | **frozen** |
| Commit / push | **no** (CPO/CDO review) |

### Boundaries

- Home = now · Contesti = current situations · Memoria = durable learned · Documenti = files · ORA = talk

## Prompt 5.3.1 — Runtime integration (prior)

| Item | Stato |
|------|--------|
| Live API had `/life-map` before restart? | **no** (stale uvicorn Aug 9 → 404 → FE fallback) |
| After restart `force=true` Psicologia count | **1** canonical + Vibo |
| Snapshot cache masking identity? | **no** (no snapshot; cache is Gemini-only) |
| Contesti uses API when available | **yes** (+ DEV warn on fallback; refresh `force=true`) |
| Semantic truth three plans | **SAME** (lineage + same-day polluted title; not two exams) |
| Contesti visual redesign | **no** |
| Commit / push | **no** |

### Restart reminder

Backend must run **current** tree (prefer `--reload`). Old process without `life_map` router → Contesti shows raw study plans again.

## Prompt 5.3 — Semantic identity & deduplication (prior)

| Item | Stato |
|------|--------|
| Root cause Psicologia ×3 | **3 study_plans** (incl. `Studio: Psicologia` title leak + lineage re-confirm) |
| Level 1/2 deterministic identity | **yes** (`identity.py`) |
| SAME ≠ RELATED | **yes** |
| Gemini identity consultant (capped) | **yes** when `LIFE_MAP_GEMINI=1` |
| Contesti visual redesign | **no** |
| Frontend dedup | **no** (API returns canonical) |
| Home / Life Setup / Memoria / Shell | **frozen** |
| Commit / push | **no** |

### Screenshot expectation (user_0ea622447cfc shape)

BEFORE: 3 Psicologia study rows + Vibo. AFTER: 1 canonical Psicologia + Vibo.

## Prompt 5.2 — Grounded Gemini Life Map vertical slice (prior)

| Item | Stato |
|------|--------|
| Novel grounded situation → Contesti rows | **yes** (open semantics, no gym enum) |
| Stable identity from evidence refs | **yes** |
| Hallucination drop / ambiguity preserve / dedup / det wins | **yes** (tests) |
| `LIFE_MAP_GEMINI` default 0; works when 1 | **yes** |
| Contesti visual redesign | **no** |
| Raw conversation → Life Map | **no** (deliberate) |
| Home / Life Setup / Memoria / Shell | **frozen** |
| Commit / push | **no** (CPO/architecture review) |

### Local AI check

1. `LIFE_MAP_GEMINI=1` + `GEMINI_API_KEY` in `backend/.env`
2. Life Profile fact with free-text novel activity (e.g. salute.attivita)
3. `GET /api/life-map?force=true` → `situations` may include `kind=inferred`
4. Contesti “In questo periodo” shows row without special-case FE

## Prompt 5.1 — AI-Native Life Map foundation (prior)

| Item | Stato |
|------|--------|
| Option | **B** — thin `backend/life_map/` on shared Provider Manager |
| Principle GEMINI=cognition / data=truth | **documented + coded** |
| `GET /api/life-map` deterministic assemble | **yes** |
| Gemini enrichment | **foundation only** (`LIFE_MAP_GEMINI=0` default) |
| Contesti UI redesign | **no** (unchanged Quiet Premium) |
| Novel situations in Contesti rows | **not yet** (validated in interpretation only) |
| Conversation → Life Map evidence | **gap** (not wired) |
| Life Objects projection | **gap** (interpretation layer designed; LO not assembled yet) |
| Home / Life Setup / Memoria / Shell | **frozen** |
| Commit / push | **no** (CPO/architecture review) |

### Gaps / next (5.1)

- Wire conversation-confirmed facts into evidence pack.
- Optionally surface grounded inferred situations in Contesti when product defines nav.
- Life Object list as additional structured source (avoid Profile duplicate).
- Enable `LIFE_MAP_GEMINI=1` only after review + cost/latency check.

## Prompt 5 — Contesti Life Map V1 (prior)

| Item | Stato |
|------|--------|
| Placeholder Contesti sostituito | **yes** |
| Life Map (not category menu) | **yes** |
| Dati: Life Profile + study/travel attivi | **yes** (no new backend) |
| Nessuna tassonomia fissa vuota / + Nuovo contesto | **yes** |
| Sezioni solo se contenuto reale | **yes** |
| Context Detail generico | **no** (deliberato — gap documentato) |
| Life Objects / relazioni / history in Contesti | **no** (gap — shadow / non affidabili per V1) |
| Home / Life Setup / Memoria / Shell | **frozen / untouched** |
| Commit / push | **no** (fermo per review CPO/CDO) |

### Visual QA — Contesti (desktop Light)

1. `scripts/dev`; login utente con Life Profile popolato e/o studio/viaggio attivi.
2. Tab Contesti: titolo + supporting copy; max-width ~800; Ambient rail invariata.
3. Con dati: “In questo periodo” e/o “La tua vita” senza card grid / icone categoria.
4. Utente nuovo / pochi dati: empty *ORA sta ancora conoscendo la tua vita.*
5. Capture Screenshot A (con dati) + B (empty) se possibile.

### Gaps / next

- Generic Context Detail quando esisterà destinazione sensata (Life Object o profile domain).
- Relazioni reali (non string-match) se Life Graph / LO relationships sono product-ready.
- Opzionale: Life Objects active list come spine aggiuntiva (oggi shadow; rischio duplicato con Profile).

## Prompt 4 — Login Quiet Premium V1 (prior)

| Item | Stato |
|------|--------|
| ImmersiveScreen canvas, no login card | **yes** |
| Canonical headline + supporting copy | **yes** |
| AppButton / AppInput / AppDivider + useTheme | **yes** |
| Apple → Google → Email order; modes + register toggle | **yes** |
| Forgot password / legal links | **omitted** (did not exist) |
| Password visibility toggle | **omitted** (did not exist) |
| `routeAfterAuth` / Life Setup / Home / Shell | **frozen / untouched** |
| Backend / AuthContext / api client | **untouched** |
| Commit / push | **no** |

### Visual QA — manual repro (Login)

**Desktop Dark / Light**

1. `scripts/dev` (or Expo web); open `/login` logged out.
2. Viewport ≥1024px: content column ~420–480px, centered, slightly above vertical middle; lots of whitespace; no card.
3. Toggle theme preference Light/Dark/System — surfaces/text/accent from semantic tokens.
4. Providers: Apple (if shown) → Google → divider → Continua con Email; dimmed if unconfigured; tap unconfigured → human config message.
5. Email form: Accedi primary Deep Indigo; toggle *Nuovo? Crea un account*; loading disables double submit; bad password → human error.
6. Capture Screenshot A (Dark) + B (Light).

**Mobile**

1. Narrow viewport / device: full-height Immersive, safe-area, keyboard opens without clipping submit.
2. Capture Screenshot C.

**Post-auth (routing frozen)**

1. New user → Life Setup gate; completed user → Home. Do not bypass gate for QA.

## Micro-batch 3.S — Human Presentation Semantics (prior)

| Item | Stato |
|------|--------|
| Human Italian `reason_summary` from factor codes | **yes** — `home/reason_presentation.py` |
| Ranking scores/weights/order unchanged | **yes** |
| DailyFocus `"Tipo "` omit removed | **yes** — backend fixed |
| Study exam identity ≠ Home/insight title | **yes** — `study/flow.py` + `plan_service` |
| Shell / Home visual / Daily Focus layout | **untouched** |
| Commit / push | **no** |

### INTERNAL ≠ PRESENTATION

- **INTERNAL:** `ReasonFactor` codes + weights drive ranking; type factor may still label `Tipo travel` for debug API.
- **PRESENTATION:** `format_reason_summary(factors, item_type=…)` → short Italian; wired in `ranking.score_item` / dampen path → `explanation.summary`.
- **Study:** subject identity = `intent_entities.subject|exam` only. Never `display_title` / `ctx.title` / `session.title`. Known → `Quando è l'esame di {Subject}?`; unknown → `Quando è l'esame?` + `Quale esame vuoi preparare?`.

## Application Shell V1 Visual Correction (Prompt 3.1) — prior

| Item | Stato |
|------|--------|
| Desktop rail fixed 80px (remove `railWrap` flex:1) | **yes** |
| `useAmbientInset.paddingLeft` = 0 (rail is layout sibling) | **yes** |
| Rail active state quieter (weight; no rail dots; ORA not FAB) | **yes** |
| Action Focus decision max-width 720 (`FOCUS_DECISION_MAX_WIDTH`) | **yes** |
| Focus understood-summary chips hidden (Destinazione: Partenza noise) | **yes** — session data kept |
| DailyFocus omit engine `reason_summary` with `"Tipo "` | **superseded by 3.S** |
| Presentation Semantics Issue (full human Perché copy) | **closed in 3.S** |
| Exam title bug (`study/flow.py`) | **fixed in 3.S** |
| Home layout / DailyFocus structure / max-width | **frozen** |
| Backend / commit / push | **no** |

### Visual QA — manual repro (auth-gated; no auth bypass)

**Screenshot A — Home desktop compact rail**

1. `scripts/dev` (or Expo web + backend) with a logged-in user.
2. Resize viewport ≥1024px width.
3. Open Home `/(tabs)`.
4. Confirm left Ambient rail ≈80px; content (DailyFocus / AskBar / Horizon) centers in the *remaining* viewport, not the full window ignoring the rail.
5. Capture Screenshot A.

**Screenshot B — Action Focus**

1. From Home Daily Focus, open an Action guide (`/action/[sessionId]`).
2. Confirm: no Ambient rail/bar; Focus chrome ← only; decision column ~720px; Continua full-width inside column; no “Destinazione: Partenza” chips above the question.
3. Capture Screenshot B.

### Manual checklist (shell)

1. Tabs: Home · Contesti · ORA · Memoria · Profilo
2. ≥1024: compact rail 80px, not 50/50
3. Narrow: floating Ambient bar unchanged
4. Action: Focus width ~720; no understood-summary noise; Continua primary
5. Light/Dark via tokens
6. Reduce motion: shell fade 0

## Application Shell V1 (Prompt 3) — foundation

| Item | Stato |
|------|--------|
| `OraShellMode` ambient / focus / immersive | **yes** (`frontend/src/shell/`) |
| AmbientTabBar floating + GlassContainer | **yes** |
| Desktop Ambient rail via `useBreakpoint` | **yes** (geometry corrected in 3.1) |
| Primary IA Home · Contesti · ORA · Memoria · Profilo | **yes** |
| Contesti Quiet Premium placeholder | **replaced** by Life Map V1 (Prompt 5) |
| ORA center → ConversationEngine Ask path | **yes** (`/(tabs)/ora`) |
| Documenti / Aggiungi `href: null` (Profilo → Documenti) | **yes** |
| FocusScreen / FocusChrome | **yes** |
| ImmersiveScreen foundation | **yes** (no Life Setup redesign) |
| Action `/action/[sessionId]` Focus chrome + useTheme | **yes** |
| Shell transition ~240ms + reduce-motion | **yes** |
| Home Frozen — shell glue + safe presentation omit only | **yes** |
| Life Setup / Backend | **untouched** |
| Commit / push | **no** (per request) |

## Sprint 4.2 Final Fix — question intent constrained

| Item | Stato |
|------|--------|
| `QUESTION_GOALS` / planner-owned intent | **yes** |
| Gemini context binds `question_goal` | **yes** |
| spoken_question semantic validation (life_places drift) | **yes** |
| Ack judgment sanitize (giustamente/ovviamente/correttamente) | **yes** |
| Architecture A (one StrategistPlan LLM call) | **yes** (planner is deterministic pre-step) |
| MLC / gate / location / Docs / Home / auth / soft-exit frozen | **yes** |
| FE | **untouched** |
| Commit | **pending review** |

## Sprint 4.2 — AI-Native Conversational Rendering

| Item | Stato |
|------|--------|
| Architecture A (same-call spoken fields) | **yes** |
| `acknowledgement` / `spoken_question` / `conversational_bridge` XOR | **yes** |
| `validate_rendered_text` + SAFE fallbacks | **yes** |
| Critical fix: no `lavori come {priority sentence}` | **yes** |
| Optional ONE Gemini wrap synthesis | **yes** |
| MLC / gate / location / soft-exit / Home frozen | **yes** |
| DETERMINISTIC vs AI documented | **yes** |
| Tests A–F + walkthrough + mocks | **yes** (137 passed with MLC/strategist/life_experience/docs) |
| FE | **untouched** |
| Commit | **pending review** |

## Sprint 4.1 — Walkthrough Corrections (this batch)

| Item | Stato |
|------|--------|
| Auth CTA “Nuovo? Crea un account” on initial screen | **yes** |
| Hide Esci / Più tardi on first-run pre-MLC | **yes** (via `allowSoftExit` from `?resume=` / `start.resumed`, not `!done`; Salta tema kept) |
| Soft-exit residual fix (4.1) | **yes** (`softExit.ts` + tests A–D) |
| Thinking state in-thread (no full-screen loader) | **yes** |
| near_mlc_bridge not falsely “chiaro” on thin knowledge | **yes** |
| NUCLEUS explain benefits first-person | **yes** |
| Location assist life_places (geolocation + Nominatim + confirm) | **yes** (no expo-location; city only) |
| synthesize_first_picture paraphrase fixes | **yes** |
| Refusal / doc / synthesis / location tests | **yes** |
| Gate / MLC / Documents V2 / Home / auth backend frozen | **yes** |
| Backend tests (strategist+MLC+life_experience+conversational) | **59 passed** |
| `tsc --noEmit` / ESLint changed FE | **PASS** (0 errors) |
| Commit | **pending review** |

## Sprint 4 — Conversational Experience V1

| Item | Stato |
|------|--------|
| First-contact greeting (intro + one open Q) | **yes** |
| Contextual acknowledgements (strategist/voice) | **yes** |
| Near-MLC conversational bridge (no %/checklist) | **yes** (tightened in 4.1) |
| Fact-grounded final synthesis + learning promise | **yes** (rewrite in 4.1) |
| CTA **Entra in ORA** (same complete→gate→Home flow) | **yes** |
| Document proposal as optional accelerator copy | **yes** |
| Exit / Più tardi copy (≠ Home / ≠ completed) | **yes** (hidden on first-run in 4.1) |
| No FE conversation engine / no progress UI | **yes** |
| Gate / MLC / Documents V2 / Home frozen | **yes** |
| Backend tests (incl. conversational) | **superseded by 4.1 count** |
| `tsc --noEmit` / ESLint life-setup | **PASS** |
| Commit | **pending review** |

## Sprint 3 — Minimum Life Context V1

| Item | Stato |
|------|--------|
| `minimum_life_context.py` coverage model | **yes** |
| `plan_next` wrap only when MLC sufficient | **yes** |
| Multi-nucleus infer from natural language | **yes** |
| Persist coverage via `known_facts` + `meta.mlc_coverage` | **yes** |
| Documents not required for done | **yes** |
| Gate Sprint 2B / Home untouched | **yes** |
| Backend tests MLC + strategist | **passed** (superseded count by Sprint 4) |
| Commit | **included in baseline `9722724` / pending Sprint 4 review** |

## Sprint 2B — Life Setup Conversation behind Gate

| Item | Stato |
|------|--------|
| `/life-setup` mounts `LifeSetupConversationScreen` | **yes** |
| Raw `/(tabs)` bypasses removed from conversation | **yes** |
| Complete → `lifeSetupComplete` then `completeLifeSetupGate` | **yes** |
| Exit / Più tardi do not open Home | **yes** |
| Gate unlocks Home only on `session.status === completed` | **yes** |
| Tabs guard kept (2nd defense) | **yes** |
| Home / Documents pipeline untouched | **yes** |
| Commit | **pending review** |

### Resume limits (documented)

- Active session: cold start resumes via `lifeSetupStart(false)`.
- After Esci (`lifeSetupCancel`): session terminal → in-place `start(force=true)` (new turn, not mid-thread restore).
- “Più tardi” no longer calls `postpone_all` (that marked `skipped` and unlocked Home under old `should_show` semantics).

## Sprint 1 — Life Setup Gate

| Item | Stato |
|------|--------|
| Persistent `ora.lifeSetupCompleted.<userId>` | **yes** |
| Gate module `src/life-setup/gate.ts` | **yes** |
| Placeholder Completa Setup | **rollback only** (not normal path) |
| Home unaware / unchanged | **yes** |

## Prior — Home Quiet Premium V1 — technical consolidation (2.2)

**Scope:** code quality only — **no intentional visual change**. Preparing Frozen V1.

| Item | Stato |
|------|--------|
| `getFocusGlow(scheme)` in theme | **yes** |
| CTA busy disables sibling actions | **yes** |
| Nav+action dual-step documented (intentional) | **yes** |
| Redundant surface ternaries removed | **yes** |
| `focusPresentation` helpers | **yes** |
| Visual design (polish 2.1) | **frozen intent** |

## Prior — Home Quiet Premium Polish 2.1

| Item | Stato |
|------|--------|
| Daily Focus / CTA hierarchy / Horizon / Ask Bar | **yes** |
| Home V3 Life Objects UI | **still OFF** |

## Prior — Design System + Life Objects

| Item | Stato |
|------|--------|
| Quiet Premium tokens / ThemeProvider / primitives | **implemented** |
| Life Object Engine + Knowledge Model | **implemented** (shadow) |
| `LIFE_OBJECT_HOME_UI_ENABLED=0` | **yes** |

## Open / next

1. **Manual new-user Life Setup walkthrough** (Sprint 4 feel test A–G) before more features
2. **Login Quiet Premium** — CPO/CDO visual review (Screenshot A/B/C); commit when approved
3. Theme toggle in Profilo
4. Playwright Ambient IA + Action Focus smoke
5. Home V3 UI — solo con flag=1
6. Exam presentation already fixed in 3.S — monitor residual Perché factor rows

## Credentials / safety

- Never commit `.env` / tokens
- No new UI libraries
- No backend changes in this batch
# V2.8.4 — Unified Clarification + Uncertainty Engine

Status: implemented in the production AI Core, CPO-approved and closed out. `CognitiveDecision`
now has an optional backward-compatible uncertainty contract with typed missing-information
identity, ambiguity and reversible assumptions. Governance prevents repeated structured
questions and unsafe actions under blocking uncertainty; Context Broker V3 remains the bounded
evidence retrieval path. No domain router, new provider, dependency, DB collection or frontend
flow was introduced.

Final local regression gate (2026-08-19): 16/16 deterministic V2.8.4 tests passed; 292 passed
in `conversation_engine/tests/` (excl. provider-real `_live.py`); 44 passed in
`situations/life_memory/life_os/llm`; legacy compatibility `test_iter19_2_memory_ask_documents.py`
3 passed/7 skipped (honest provider-unavailable skip); `compileall`, blocking lint and
`git diff --check` clean. Unrelated legacy `tests/test_iter9..23*` integration suites were
excluded from this gate (remote-preview-URL dependency and pre-existing shared-DB test-order
coupling documented in `backend/tests/conftest.py`) — confirmed unrelated to `ai_core` by
import audit, zero references found.

# V2.8.5 — Life Context Graph + Unified Cognitive State

Status: implemented, **CPO approved — closed out 2026-08-20**. New `backend/context_graph/`
module (edges only, no new node collection); `CognitiveDecision.context_graph_updates`
optional/backward-compatible, ≤2 per turn; new bounded `life_context_graph` Context Broker
source (depth ≤2, ≤10 edges). Deliberately not built on the pre-existing
`life_graph`/`knowledge`/`auto_link`/`life_objects` subsystems — see `docs/ARCHITECTURE.md`
V2.8.5 section for the full architectural rationale.

**Graph convergence decision: COEXISTENCE WITH A STRONG BOUNDARY.** `context_graph` is the
sole canonical source for relationships the conversational AI Core authors and reasons about
(Situation/Memory/Goal/Plan/Object/Profile/Document/Calendar/Presence). `life_graph` /
`knowledge` / `auto_link` keep every existing non-`ai_core` consumer they already have
(Documents, Goal Engine, Action Engine, Home's auto-link surfacing); `life_objects` keeps its
own Digital Twin relationship model (LifeObject↔LifeObject only). No bidirectional sync, no
storage migration/fusion in V2.8.5 — if a future surface needs relationships from both worlds,
the correct pattern is a read-side adapter/projection, never a shared write path.

| Item | Stato |
|------|--------|
| Edge model AI-authored, system-governed, open predicate | **implemented** |
| No duplicate canonical-entity storage (refs only) | **implemented** |
| Ownership/idempotency (`governance_key`)/revision+history | **implemented** |
| Conflicting active edge → `REQUIRES_SUPERSESSION` (never silent) | **implemented** |
| `life_context_graph` Context Broker source, bounded 1-2 hop | **implemented** |
| Temporary Situation / inference / presence never auto-promoted | **enforced** |
| Persist-before-claim honesty for graph-link language | **implemented** |
| No second LLM/embedding call, no new DB technology | **none added** |
| V2.8.5 deterministic tests (A-T) | **20/20 passed** |
| Regression: `conversation_engine/tests` (excl. `_live.py`) | **312 passed** |
| Regression: `situations/life_memory/life_os/llm` | **44 passed** |
| Legacy `test_iter19_2_memory_ask_documents.py` | **3 passed/7 skipped** (honest) |
| `compileall` / blocking lint / `git diff --check` | **all clean** |
| Hardcoding audit (new production code) | **clean** (one prose example self-corrected) |
| Provider-real eval (continuity/correction/arbitrary-life/uncertainty) | **4/4 passed** (live Gemini; one test assertion self-corrected, not production code) |
| Live Chrome gate (real backend, real DB, real auth) — edge creation/persistence | **PASS** — real `context_edges` doc created from a natural arbitrary-life conversation (non travel/study/work/house/medical), verified in Mongo (subject/predicate/object/authority/confidence/revision) |
| Live gate — cross-turn continuity | **PASS** — later turn used the relationship without the user repeating it |
| Live gate — cross-session continuity | **PASS** — new session (new `ces_` id) recalled updated state with zero re-explanation |
| Live gate — negative control | **PASS** — a routine turn with no durable relationship created zero edges |
| Live gate — persist-before-claim | **PASS** — every "ho annotato/aggiornato" claim verified true against Mongo, in both the graph edge and the Situation correction path |
| Live gate — `life_context_graph` retrieval observed live | **NOT OBSERVED** (see follow-up 1) — mechanism wired and indexed correctly; not selected by the Broker in this scenario because Situation alone already answered the query |
| Live gate — graph-level `REQUIRES_SUPERSESSION` observed live | **NOT OBSERVED** (see follow-up 2) — the live correction (a person's role changing) was correctly handled by Situation's own supersession, since no competing graph edge existed to conflict |
| Commit / push | **yes, this close-out** |

### Follow-up items (non-blocking, not yet decided as requirements)

1. `life_context_graph` Context Broker retrieval was not observed firing in the final live
   browser gate. Deterministic + provider-real coverage already exists for this path. Worth
   stressing with a retrieval-only live scenario in a future sprint — **not a defect**, and the
   Source Registry ranking/anchor logic is explicitly NOT to be changed as part of this close-out.
2. `context_graph`-level supersession (`REQUIRES_SUPERSESSION` → new edge → old edge
   `superseded_by`) was not exercised in the final live browser gate — already covered
   deterministically and via provider-real eval. Do not manufacture an artificial conflict just
   to force this live; wait for a natural scenario.
3. `life_object:` is not yet a recognized canonical ref prefix in `context_graph` — a future
   product decision, not implemented now.
4. Whether `life_context_graph` should ever receive an anchor/ranking bonus in the Source
   Registry (mirroring `situations`/`profile`/`memory`) is an open future question, explicitly
   not decided or implemented in this close-out.

## V2.8.6a — Calendar Foundation Hardening (this batch)

**Status: foundation only — hardens the existing Calendar infrastructure. Does NOT expose
Calendar as an AI Core capability yet (that is V2.8.6b, gated separately). No CalendarFlow, no
keyword router, no OAuth structural change.**

| Item | Stato |
|------|--------|
| Context Broker `_calendar` source field-name bug (`start`/`end`/`source` → real schema `start_datetime`/`end_datetime`/`provider`) | **fixed** — AI no longer sees `start=unspecified` for every event |
| General-purpose `timezone_service.resolve_user_timezone()` (user_confirmed → connector_calendar → system_fallback, authority always observable) | **implemented** — no wizard, no auto-write to Profile, no GPS-derived residence inference |
| Real Google Calendar provider `create_event` idempotency (`extendedProperties.private.ora_event_id`, bounded exact lookup via `privateExtendedProperty`, never fuzzy) | **fixed** — previously only the fake provider checked this; a network failure after Google accepted could duplicate an event on retry |
| Canonical `GoogleCalendarSyncService.reschedule_draft()` (title/start/end/timezone/location/description; never a second draft; failure never claims success) | **implemented** — no update/reschedule path existed for document-derived drafts before this batch |
| `connectors/google_calendar/consent.py` — reusable, non-HTTP `calendar_consent_granted()`/`require_calendar_consent()` for a future AI Core tool handler | **implemented** — reuses `PermissionService`, no second permission system |
| `reauthorization_required` instance status now set on refresh failure | **fixed** — small, additive; OAuth flow itself unchanged |
| Revocation now also revokes `calendar.write` consent (previously only `calendar.read`); google-synced drafts flagged `sync_status="revoked"` when no other active Google instance remains for the user (non-destructive — never deletes/touches Google, never touches `google_event_id`) | **fixed** — multi-account edge case (attributing a draft to a specific surviving instance) explicitly left as a documented limitation, not solved here |
| `calendar_event_drafts` index `(user_id, status)` | **added** — verified live on boot |
| Three pre-existing independent write subsystems (`documents/intelligence`, `action_engine/study`, `action_engine/travel`) | **untouched** — consolidation explicitly out of scope for this batch |
| `intent_engine`/`semantic_engine` keyword routing, Action Engine reminder wizard, `goal_engine.linked_calendar_events`, `ai_life_strategist` | **untouched**, as instructed |
| AI Core tool registry | **unchanged** — verified 0 Calendar capabilities (V2.8.6a does not add any) |
| `context_graph` | **untouched** — `calendar:` ref prefix already supported since V2.8.5 |
| V2.8.6a tests (A–T) | **22/22 passed** |
| Calendar regression (`test_iter9_ingestion_and_google_calendar`, `test_google_calendar_write_sync`, `test_iter18_apple_calendar_connector`, `test_oauth_loopback_hosts`) | **57 passed** |
| `conversation_engine/tests` (excl. `_live.py`) | **312 passed** |
| `situations/life_memory/life_os/llm` | **44 passed** |
| Provider Manager | **22 passed, 1 skipped** |
| `compileall` / blocking lint / `git diff --check` | **all clean** |
| Real backend boot (`server.startup()` invoked directly, real configured DB) | **PASS** — "Life Context Graph indexes ready" + new calendar index confirmed live, no regression |
| No real Google/Apple call anywhere in this batch | **confirmed** — fake provider + mocked `httpx` transport only |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up (non-blocking, not decided as requirements)

1. Multi-account attribution of `calendar_event_drafts` to a specific revoked instance is not solvable with the current schema (no `connector_instance_id` on the draft) — documented limitation, not fixed.
2. The three independent Google write subsystems (`documents/intelligence`, `action_engine/study`, `action_engine/travel`) still duplicate "resolve active instance" logic — consolidation candidate for a future batch, not this one.
3. V2.8.6b will add the actual AI Core capabilities (`get_calendar_events`, `create_calendar_event`, `update_calendar_event`, `cancel_calendar_event`) on top of this now-hardened foundation, using the `consent.py` helper and `reschedule_draft()` added here.

## V2.8.6b — AI-native Calendar Intelligence (this batch)

**Status: Calendar is now an AI Core capability — read-only evidence plus confirmed,
consent-gated writes. No CalendarFlow, no intent router, no new confirmation UI, no new
governance code, no new idempotency mechanism, no Context Graph changes.**

| Item | Stato |
|------|--------|
| `get_calendar_events` (READ_ONLY), `create_calendar_event`/`update_calendar_event`/`cancel_calendar_event` (REVERSIBLE_WRITE) registered in `ToolRegistry` | **implemented** — `conversation_engine/ai_core/tools/calendar_caps.py` |
| Calendar write confirmation | **reuses** the existing `response_mode="act"` mechanism — no new confirmation surface |
| Governance for calendar writes | **reuses** the existing `_blocks_side_effect(uncertainty)` gate — zero new governance code |
| Local-draft idempotency | **reuses** `InternalCalendarProvider.create_from_candidate`'s existing keying (`source_document_id="ai_core_conversation"`, `source_event_candidate_id=f"epoch:{reasoning_epoch}"`) |
| Persist-before-claim guard for calendar | **implemented** — `_CALENDAR_CLAIM_RE` in `loop.py`, fourth instance of the Memory/Graph pattern |
| Consent instance-scoping bug (write handlers checked the wildcard consent tier, but real OAuth grants consent scoped to the specific connected instance) | **found and fixed** during implementation — `_active_instance_id()` helper added |
| `update_calendar_event` false-negative honesty bug (`reschedule_draft()` commits the local field patch unconditionally before any Google-side step; the handler's failure paths denied the update had happened at all, when it always had, locally) | **found live during Chrome QA and fixed** — both failure paths now return `status="partial"` with an accurate "saved locally, not confirmed on Google" message, mirroring `create_calendar_event`'s existing convention |
| Keyword-based routing (`if "calendar"/"ricordami" in text`, `calendar_intent ==`) | **absent**, statically verified — `test_v`/`test_z` grep the production diff |
| Timezone | **exclusively** via `timezone_service.resolve_user_timezone` — no new hardcoded `Europe/Rome` in the AI-native path |
| Conflict awareness | **implemented** — bounded O(n²) overlap check inside `get_calendar_events`, capped at 20 events / 10 pairs; evidence only, no new scheduling engine, no Google FreeBusy call |
| Canonical ref | `calendar:{draft_id}` for AI-managed events; `ingestion_events` remain read-only mirrors with `calendar_ref: None` — no legacy migration |
| Calendar ↔ Situation/Plan/Goal relationship | **AI-proposed only**, via the existing V2.8.5 `context_graph_updates` channel with open predicates — never auto-created by the calendar tool |
| Deterministic tests (A–Z + 1 live-QA-derived regression test) | **27/27 passed** — `conversation_engine/tests/test_ai_native_calendar_v286b.py` |
| `conversation_engine/tests` full suite (excl. `_live.py`) | **339/339 passed, 0 errors** — verified both under the project's default `-n 2 --dist loadscope` and under `-n 0` |
| `backend/tests/test_calendar_foundation_v286a.py` (V2.8.6a regression) | **22/22 passed** |
| Calendar/connector regression (`test_iter9_ingestion_and_google_calendar`, `test_google_calendar_write_sync`, `test_iter18_apple_calendar_connector`, `test_oauth_loopback_hosts`) | **57/57 passed under `-n 0`**; the same 4-file combination shows pre-existing, non-deterministic pytest-xdist worker-sharing flakiness under the project's default `-n 2` config (14–16 spurious errors, varying run to run) — reproduced **without** any V2.8.6b file in the run, confirmed pre-existing and out of this sprint's scope |
| `situations/life_memory/life_os/llm` | **44/44 passed** |
| Provider Manager | **23/23 passed** (a real `GEMINI_API_KEY` was available this session, so the previously-skipped live-enrichment test ran and passed instead of skipping — not a regression) |
| `compileall` / blocking lint (`flake8 --select=E9,F63,F7,F82`) / `git diff --check` | **all clean** |
| Hardcoding audit (manual grep of the full diff for `calendar intent`/`reminder`/`appointment`/`meeting`/`domani`/`tomorrow`/`dentist`/`notaio`/`travel`/`study`/`work`/`medical`/`house`) | **clean** — the one match is prose guidance in `prompt.py` explicitly telling the AI never to route on those words, not a code branch |
| Security audit (ownership scoping on every query, no raw Google payload/token/secret in any Observation, no broad delete, confirmation required, uncertainty blocks write) | **verified** — all four `calendar_event_drafts`/`ingestion_events` queries in `calendar_caps.py` are scoped by `user_id`; `test_w` asserts no token/secret substrings and a fixed payload-key whitelist |
| Performance (no live Google call per turn, no new polling/cron, no mandatory second LLM call) | **verified** — `get_calendar_events` is local-only; writes are on-demand and rare |
| **Provider-real eval** (5 scenarios: simple read, create-with-confirmation, correction, Situation-linked, arbitrary vague reminder) | **5/5 passed**, run serially (`-n 0`) — parallel xdist workers triggered transient `LLMNetworkError` connection contention against the live Gemini endpoint in this environment; isolated/serial runs were reliably clean. No real Google Calendar event was created, modified or cancelled by this eval (pure `_call_ai` reasoning-shape checks, no tool execution) |
| **Chrome QA** | **executed**, in an isolated environment: a second backend instance on an alternate port (`CALENDAR_PROVIDER_MODE=fake`, process-env override only — the real `.env` file was never modified) and a dedicated throwaway account (`qa.calendar.v286b@ora.app`), fully cleaned up afterward. Covered: empty-calendar honest read, create-with-confirmation, consent-gating (honest `consent_required` message), create-partial honesty (Google not connected), correction/reschedule (found and fixed the false-negative honesty bug above, then re-verified live), cancel-with-confirmation. No real Google Calendar write occurred. One unrelated pre-existing console `409` was observed during account setup, before any Calendar-specific request; every Calendar-specific network call returned `200 OK` |
| Real backend boot with the QA-mode instance | **PASS** — full index/module startup banner identical to V2.8.6a's, no regression |
| No real Google/Apple call anywhere in this batch | **confirmed** — fake provider throughout deterministic tests and Chrome QA; provider-real eval never executes a tool handler |
| Commit / push | **NO** — STOP for CPO review |

## V2.8.6b — Final Pre-Commit Hardening Gate (this batch)

**Status: two CPO-identified gaps closed — update on a cancelled event, and calendar.read
revocation vs. cached Google events. No design reopened, no new feature, no Context Graph
change, no FreeBusy, no reminder-architecture change, no UI change, no Google real writes.**

| Item | Stato |
|------|--------|
| `update_calendar_event` on a cancelled event | **fixed** — explicit typed rejection (`status="rejected"`, `failure_kind="event_cancelled"`) before consent/Google, no DB mutation, no reactivation, no recreation, no exception reaches the reasoning loop |
| `get_calendar_events` after `calendar.read` revocation | **fixed** — `source: "google_external"` items are now gated on `calendar.read` consent (previously ungated); `source: "ora_managed"` items remain visible regardless, per CPO decision |
| Cached Google events survive revocation (not deleted) | **confirmed** — revocation only changes visibility, never touches `ingestion_events` |
| Cross-user isolation on the read path | **confirmed** — unchanged, still scoped by `user_id` on every query |
| No live Google call during read | **confirmed** — `_active_instance_id` resolves from local `connector_instances`, no network call |
| Additional bug found and fixed while adding the CPO's read-policy tests | `get_calendar_events`'s default time window used the server's **naive local** `datetime.now()`; compared via lexicographic string range against event strings that are always UTC-aware, this could silently exclude real events depending on the server's timezone offset. Fixed to default to UTC-aware "now" |
| `partial` semantics re-confirmed | Local success + Google sync unconfirmed → `status="partial"`, message says the local change was saved and Google is not confirmed — never "not moved", never "Google was updated" |
| New deterministic tests | 7 added (1 cancelled-update + 6 read-policy A–F) — suite now **34/34 passed** |
| `conversation_engine/tests` full suite (excl. `_live.py`) | **346/346 passed, 0 errors** |
| `backend/tests/test_calendar_foundation_v286a.py` | **22/22 passed** |
| Calendar/connector regression (serial, per the method already proven reliable) | **57/57 passed** |
| `situations/life_memory/life_os/llm` | **44/44 passed** |
| Provider Manager | **23/23 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit on the changed file | **clean** — no new matches |
| Security audit | **clean** — no token/secret in the file, all queries remain `user_id`-scoped, no broad delete, no consent bypass |
| Provider-real eval repeated | **NO** — prompt, `CognitiveDecision`, tool descriptions and AI-facing semantics did not change in this gate (only runtime-side consent/validation logic) |
| Chrome QA repeated | **NO** — no UI-visible behavior changed; the two fixes are runtime-internal (an error path and a consent gate), not reachable through a different observable flow than what was already verified live |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up (non-blocking, not decided as requirements)

1. The pre-existing pytest-xdist worker-sharing flakiness in `backend/tests/` (see regression row above) is unrelated to Calendar but was newly characterized this session — worth a dedicated fix in a future batch (likely: align the remaining `asyncio.get_event_loop()`-style tests in that directory to the `@pytest.mark.asyncio` convention already proven in `conversation_engine/tests/`).
3. Google FreeBusy-based availability (as opposed to local-event-derived conflict detection) remains a documented, undecided future follow-up, not built in V1.

## V2.9.1 — Life Change Signal / Continuous Life Reasoning foundation — CPO APPROVED / CLOSED OUT

**Status: event-driven foundation only. `life mutation → LifeChangeSignal` and nothing beyond
it. V2.9.1 CREATES NO PROACTIVE SUGGESTIONS, sends no notification, adds zero LLM calls, zero
external calls and zero background work. "SO WHAT?" is V2.9.2; "SHOULD I SPEAK?" is V2.9.3.**

| Item | Stato |
|------|--------|
| Pre-existing equivalent primitive | **none found** — repo-wide search for change/domain-event/outbox/signal semantics returned nothing user-scoped, persistable, idempotent and notification-neutral, so a minimal new primitive was created rather than bending a semantically different legacy model |
| New module `backend/life_signals/` (`models.py`, `repository.py`, `service.py`, `emitters.py`) | **created** — follows the `context_graph/` module convention exactly |
| New collection `life_change_signals` | **created** — indexes `(user_id,id)` unique, `(user_id,dedupe_key)` unique+sparse, `(user_id,status,created_at,id)`; registered in `server.py` startup like every other subsystem |
| Emission point | `conversation_engine/ai_core/loop.py` — in production the **single** call site of `SituationService.apply` / `ContextGraphService.apply` / `MemoryGovernanceService.process` and the executor of Calendar + Life OS write capabilities. Zero changes to any mutation subsystem's own code or contract |
| Persist-before-signal | **enforced per adapter** — proposals (`response_mode=act`), consent denials, CLARIFY/REJECT, revision conflicts, explicit no-ops, reads and failures all emit nothing |
| Idempotency | **enforced twice** — adapter-level dedupe keys derived from stable mutation identity (entity ref + revision, or reasoning epoch + capability), plus a unique sparse storage index. Adapters fail closed when no stable discriminator exists rather than risk a duplicate storm |
| No recursion | **enforced** — emitting never mutates a life entity, never creates a Graph edge, never creates a suggestion, never emits a second signal |
| Canonical refs | **reused** (`context_graph.models.is_recognized_ref`) — no second namespace; an unrecognized ref is refused, not stored. Graph signals point at the edge **subject** (the `lce_` edge id is not a canonical ref) with the object as a deterministic `affected_ref` |
| Graph expansion | **absent by design** — `affected_refs` holds only refs already present in the mutation result; bounded expansion belongs to V2.9.2 |
| Failure isolation | **implemented** — `emit()` never raises, `_emit_life_change` wraps it again; the already-committed mutation is never rolled back, and the failure stays observable via the `life_change_signal_failures` trace counter and a warning log |
| Privacy | **refs + technical metadata only** — no conversation text, entity payload, document content, token or secret; verified by a test asserting the exact stored key set |
| Mutation sources CONNECTED | Situation, Life Memory, Context Graph, Life OS (plan/object), Calendar |
| Mutation sources DEFERRED | **Documents** — its persistence is spread across many `documents.update_one` call sites in `documents/` and `documents/intelligence/` with no single canonical AI-native mutation boundary; connecting it would have required duplicating emission logic or designing a boundary this sprint was told not to design |
| Proactive Engine | **untouched** — no generator added, none removed, scoring/gate/notification policy unchanged; coexistence preserved |
| Context Broker | **untouched** — deliberately NOT given a `life_change_signals` source; the signal feeds future asynchronous reasoning, not the per-turn answer |
| Context Graph / Memory governance / Calendar semantics | **unchanged** |
| LLM calls added | **0** |
| External calls added | **0** |
| Cron / polling / scheduler / background worker | **0** |
| V2.9.1 tests | **32/32 passed** (`conversation_engine/tests/test_life_change_signal_v291.py`) |
| `conversation_engine/tests` (excl. `_live.py`) | **378/378 passed, 0 errors** |
| V2.8.6b calendar suite | included above — **34/34 passed** |
| V2.8.6a foundation | **22/22 passed** |
| Calendar connector regression (`-n 0`, the method already documented as reliable) | **57/57 passed** |
| `situations` / `life_memory` / `life_os` / `llm` | **44/44 passed** |
| Proactive Engine | **232/232 passed** (untouched; run as a safety check) |
| Provider Manager | **23/23 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms and zero keyword branches in the new module or the production diff |
| Security audit | **clean** — every signal-store query user-scoped, no secret/token/`.env`, no delete of any kind in the module, no cross-user read or write, no raw payload, no new external call |
| Provider-real Gemini | **NOT REQUIRED / NOT RUN** — V2.9.1 introduces no AI decision and changes no prompt, `CognitiveDecision` field or tool description |
| Chrome QA | **NOT REQUIRED / NOT RUN** — purely infrastructural; no user-visible behaviour changed, no UI touched, no new surface |
| Commit / push | **DONE** — CPO approved; committed and pushed to `origin/feature/ora-quiet-premium-design-system` |

### Follow-up recommended for V2.9.2 (non-blocking, deliberately not built)

1. **Impact reasoning consumer** — read a bounded batch via `list_pending`, resolve authorized context through the existing Context Broker, reason once per batch (not once per mutation), `mark_processed`.
2. **Bounded graph/context expansion** at consume time, using the existing `ContextGraphService.relevant_edges` depth cap — never at emission time.
3. **Documents emission boundary** — decide a single canonical AI-native mutation boundary for Documents, then connect it the same way (CPO decision, deliberately not taken here).
4. **Processed signal retention/compaction** — `processed` signals currently accumulate; a retention rule should be decided once a consumer exists and its replay needs are known.
5. **More robust retry/recovery for signal persistence failure** — today a failed emit loses the derived event (observable via the `life_change_signal_failures` trace counter and a warning log) with no automatic replay; a durable retry path is worth designing once a consumer exists.
6. **Claiming/lease semantics** — if V2.9.2 ever runs more than one consumer per user concurrently, `list_pending` will need a claim/lease; deliberately not built while no worker exists.
7. **`_CALENDAR_CAP_KINDS` duplication** — `life_signals/emitters.py` restates the Calendar capability names by value rather than importing `loop.py`'s `_CALENDAR_WRITE_CAPS` (that module pulls in heavy AI Core wiring). Low risk and indirectly covered by tests H/J/K, but worth collapsing if a shared lightweight constants module ever appears.

## V2.9.2 — AI-native Impact Reasoning ("SO WHAT?") — CPO APPROVED / CLOSED OUT

**Status: reasoning only. `LifeChangeSignal → bounded context → one reasoning call →
ImpactAssessment`. V2.9.2 DOES NOT DECIDE WHETHER TO SPEAK — no suggestion, no notification, no
message, no tool execution. "SHOULD I SPEAK?" is V2.9.3.**

| Item | Stato |
|------|--------|
| New module `backend/life_reasoning/` (`models.py`, `repository.py`, `prompt.py`, `context.py`, `service.py`) | **created** — follows the `life_signals/` module convention |
| New collection `life_impact_assessments` | **created** — indexes `(user_id,id)` unique, `(user_id,batch_key)` unique+sparse, `(user_id,created_at desc)`, `(user_id,focal_refs)`; registered in `server.py` startup |
| Consumer | **explicitly invoked** (`ImpactReasoningService.run_pass(user_id)`) — no worker, cron, scheduler or polling |
| Batching | ref-overlap + Context Graph connection via deterministic union-find; correlated signals cost **1** AI call, unrelated signals are never merged. Bounds: ≤5 signals/pass, ≤3 batches, ≤5 signals/batch |
| Cost model | `no change ⇒ no signal ⇒ no AI call` preserved end to end — a user with no pending signals returns before any retrieval (verified by test P) |
| Context resolution | **existing infrastructure only** — `ContextBroker` Stage B, `ContextGraphService.relevant_edges`, `timezone_service`, `ToolRegistry`. No second context loader |
| Graph expansion | bounded, seeded from the signal's own refs, depth ≤2, ≤10 edges; never global, never creates a relation |
| Epistemic model | **reused verbatim** from Memory/Graph (`epistemic_status`, `authority`, evidence refs, confidence) — no third vocabulary |
| Impact `kind` | six general-purpose technical categories (dependency/risk/opportunity/constraint/conflict/missing_information) — no domain taxonomy |
| Attention fields | **absent by construction** — no `notify`/`send_now`/`surface_home`/`interrupt`/`batch_notification`/`message_to_user`; a model that emits them has nowhere to put them (test N) |
| Chain-of-thought | **never requested, never persisted** — `reason_summary` is a bounded conclusion (test U) |
| Capability awareness | names only; `capability_hint` validated against the live registry so an invented capability is dropped (test O2). Nothing is ever executed (test O) |
| Failure honesty | provider unavailable/unparseable → no assessment, signals stay pending (I/I2); context unreadable → deferred with **zero** AI calls (J); persistence failure → signals not consumed (K); consume only after persist (L) |
| Idempotency | deterministic order-independent `batch_key` + unique sparse index; replay consumes without a second assessment (B/B2); a new signal yields a new distinguishable assessment (G) |
| Provider access | **exclusively Provider Manager** — V2.8.3a failover and circuit breaker preserved; static test forbids any direct vendor import (Z) |
| Commercial neutrality | prompt-level contract asserted by test (Z3): optimise for the user's interest, never for whoever might be selling; no company/product/vendor/brand/offer, no invented price or rate |
| Proactive Engine / Context Broker / Context Graph / Memory governance / Calendar semantics | **all untouched** |
| V2.9.2 tests | **35/35 passed** (`conversation_engine/tests/test_impact_reasoning_v292.py`) |
| `conversation_engine/tests` (excl. `_live.py`) | **413/413 passed, 0 errori** |
| V2.9.1 | **32/32 passed** |
| V2.8.6b Calendar | **34/34 passed** |
| V2.8.6a foundation | **22/22 passed** |
| Context Broker V3 | **11/11 passed** |
| Context Graph + Situation + Memory | **67/67 passed** |
| `situations`/`life_memory`/`life_os`/`llm` | **44/44 passed** |
| Calendar connector regression (`-n 0`) | **57/57 passed** |
| Provider Manager | **23/23 passed** |
| Proactive Engine (untouched, safety check) | **232/232 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms in executable code (docstrings excluded from the scan, since they state the rule rather than break it) |
| Security audit | **clean** — every query user-scoped, no secret/token/`.env`, no delete in the module, no external call beyond the LLM provider, no tool write, no notification |
| **Provider-real eval** | **5/5 passed** against real Gemini via Provider Manager — arbitrary life change without invention, unstated dependency discovery, context-grounded consequence citing only supplied refs, insufficient-evidence honesty, vendor-neutral option comparison. Run serially (`-n 0`) |
| Chrome QA | **NOT REQUIRED / NOT RUN** — V2.9.2 is internal; no UI, no user-visible behaviour changed, no new surface |
| Commit / push | **DONE** — CPO approved; committed and pushed to `origin/feature/ora-quiet-premium-design-system` |

### Follow-up recommended for V2.9.3 (non-blocking, deliberately not built)

1. **Attention / intervention policy** — read recent assessments, decide whether, when and how to surface anything; this is where `relevance` finally meets a delivery decision.
2. **Proactive Engine adapter** — route an assessment that clears the attention gate into the existing scoring/dedupe/notification-policy machinery rather than building a parallel one.
3. **Assessment retention/supersession** — assessments about the same `focal_refs` accumulate; a supersession or compaction rule should be decided once V2.9.3 defines what "still relevant" means.
4. **Concurrency** — `run_pass` is safe to replay (the unique `batch_key` index prevents duplicates) but two concurrent passes for the same user can both spend a reasoning call before one loses the race; a claim/lease becomes worthwhile only when a scheduler exists.
5. **Documents emission boundary** — still deferred from V2.9.1; documents already reachable through the Context Broker can serve as evidence, but no Documents mutation emits a signal yet.

## V2.9.3 — Attention & Intervention Intelligence ("SHOULD I SPEAK?") (this batch)

**Status: the three-question sequence is complete. V2.9.3 decides whether reasoning is worth the
user's attention and through which surface. Silence is a first-class outcome; the deterministic
system gate can only ever make the result quieter; nothing is ever pushed.**

| Item | Stato |
|------|--------|
| New module `backend/life_attention/` (`models.py`, `repository.py`, `prompt.py`, `context.py`, `gate.py`, `service.py`) | **created** — follows the `life_signals/`/`life_reasoning/` convention |
| New collection `life_attention_decisions` | **created** — indexes `(user_id,id)` unique, `(user_id,decision_key)` unique+sparse, `(user_id,created_at desc)`, `(user_id,focal_refs)`, `(user_id,delivery,defer_until)`; registered in `server.py` startup |
| Consumer | **explicitly invoked** (`AttentionService.run_pass(user_id)`) — no worker, cron, scheduler or polling |
| Relevance ≠ permission | `ai_delivery` (model) and `delivery` (system) are separate persisted fields; **only `delivery` is acted on** |
| System gate one-way property | **enforced and asserted for every possible model choice** — a downgrade may only move quieter along silent ← defer ← home ← ask_user ← propose_action ← notify |
| Silence | **first-class** — `silent` decisions persisted; zero suggestions created (test B/M) |
| Safety not in the prompt | the model is **not shown** `notifications_allowed`, `quiet_hours`, `likely_sleep`, `interruption_cost`, `user_dismiss_rate` (test X2) |
| Interruption cost | **deterministic** — resolved clock via `timezone_service`, real calendar time-overlap, measured suggestion volume, recorded dismissal history. Never inferred from calendar titles |
| Proactive Engine integration | `regenerate` refactored by **extraction** into `submit_candidates`, shared by legacy generators and the AI-native path — identical scoring, gate, dedupe, learning, notification policy. No second pipeline |
| Legacy generators | **untouched**, coexisting; the 232-test Proactive Engine suite is unchanged |
| Pre-existing scoring ceiling | **found and fixed** — `generic` candidates need 0.55 but importance/urgency/confidence alone cap at ~0.54 without a deadline or goal link (which every legacy generator happens to have, hiding it). Added one optional domain-neutral `quality_hint`; legacy leaves it `None` and scores identically |
| Dedupe vs legacy | **ref-based**, never fuzzy title — one user-facing item per entity (test Q) |
| Push dispatch | **structurally impossible** — the reused notification policy never returns `send_now` (test T) |
| Tool execution | **none** — `ask_user`/`propose_action` write nothing anywhere (tests R/S) |
| Learning | bounded — repeated dismissal downgrades to Home, never a permanent blacklist (test H2); a first-time user gets a neutral multiplier (test I) |
| Home surfacing | reuses the existing suggestion model and card; AI-native items distinguishable by `source="life_reasoning"`, verified through `home_suggestions()` |
| V2.9.3 tests | **37/37 passed** |
| `conversation_engine/tests` (excl. `_live.py`) | **450/450 passed, 0 errors** |
| V2.9.2 / V2.9.1 | **35/35** / **32/32 passed** |
| Context Broker V3 | **11/11 passed** |
| Context Graph + Situation + Memory | **67/67 passed** |
| Calendar V2.8.6b / V2.8.6a | **34/34** / **22/22 passed** |
| `situations`/`life_memory`/`life_os`/`llm` | **44/44 passed** |
| Calendar connector legacy (`-n 0`) | **57/57 passed** |
| Provider Manager | **23/23 passed** |
| **Proactive Engine (module touched — full regression)** | **232/232 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms in executable code |
| Security audit | **clean** — every query user-scoped, no secret/token/`.env`, no delete, no push dispatch, no tool execution, no external call beyond the LLM provider |
| **Provider-real eval** | **6/6 passed** against real Gemini via Provider Manager — high value not silent, low value silent, speculative never pushed, missing-information can justify asking, opportunity surfaced vendor-neutrally, and the system gate demonstrably overruling the model |
| Chrome QA | see the report — conditional requirement, environment actively in use |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up recommended for V2.9.4 (non-blocking, deliberately not built)

1. **Deferred decision re-evaluation** — `defer_until` is persisted and indexed but nothing re-reads it yet; a re-evaluation path belongs with whatever eventually schedules passes.
2. **Actual delivery** — `notify` currently resolves to a Home item with a deferred batch window; a real push channel needs its own consent flow, transport and rate policy.
3. **Continuous orchestration** — signals → reasoning → attention are three explicitly-invoked passes; nothing chains them automatically yet. This is the natural place for the scheduler all three sprints deliberately avoided.
4. **Claiming/lease** — replay is safe (unique `decision_key`), but two concurrent passes for one user can both spend a call before one loses the race.
5. **Assessment/decision retention** — both stores accumulate; a compaction rule should follow once re-evaluation semantics exist.
6. **Legacy `likely_driving` heuristic** — still governs the legacy path only; worth replacing with a real activity signal rather than calendar-title keywords if that path is ever modernised.

## V2.9.4 — Continuous Life Reasoning orchestration (this batch)

**Status: the pipeline is now autonomous and event-driven. A real mutation produces a signal, a
reasoning pass and an attention decision without anyone invoking anything — and an idle system
costs literally nothing. Autonomy did NOT increase how often ORA speaks: silence remains the most
common outcome.**

| Item | Stato |
|------|--------|
| New module `backend/life_orchestration/` (`state.py`, `service.py`, `scheduler.py`) | **created** — thin coordinator; owns no cognition, executes no tool, sends nothing |
| Why a separate module (not `life_reasoning/orchestration.py` as sketched) | the dependency chain is strictly one-way (`life_attention → life_reasoning → life_signals`); an orchestrator inside `life_reasoning` importing `life_attention` would close an **import cycle** |
| New collection `life_orchestration_state` | **created** — indexes `(user_id)` unique, `(next_retry_at)`; registered in `server.py` startup |
| Trigger | `loop.py::_emit_life_change`, only when a signal was really persisted. Best-effort: never blocks, never raises, never awaits a provider |
| Event-driven guarantee | worker blocks on `asyncio.Queue.get()`; deferrals get a one-shot alarm; recovery runs once after boot. **Static AST test asserts no loop in the module contains a sleep call** |
| Cost chain | `no change ⇒ no signal ⇒ no wake-up ⇒ no reasoning ⇒ no AI call` — verified end to end, including against the live provider |
| Idle user cost | **zero** — pending work is checked before the lease is taken, so an idle pass writes no document at all |
| Coalescing | one pending pass per user; a 20-mutation burst yields **1** pass; a change arriving mid-pass sets a redo flag instead of being lost |
| Lease | one collection, one granularity (the whole pass). TTL 120s, crash-reclaimable, released only by its owner, opaque non-PII owner id. Prevents double AI spend only — the unique `dedupe_key`/`batch_key`/`decision_key` indexes already make duplicate persistence impossible |
| Lease acquisition hardening | written explicitly (try-take → check-exists → insert) instead of relying on upsert provoking a unique-index violation, so a missing index degrades to "no lease" rather than silently handing out two |
| Bounded pass | `MAX_CYCLES = 2`; sub-service budgets unchanged (V2.9.2 ≤5 signals/≤3 batches, V2.9.3 ≤5 assessments/≤3 batches) |
| Failure isolation | impact failure never fabricates an assessment; attention failure leaves the assessment recoverable; both record **per-user** exponential backoff (60s→1h), distinct from the Provider Manager's global per-vendor circuit breaker |
| Durability | in-process queue is an accelerator, never the queue of record — dropped wake-up / full queue / cancelled task / dead process cost latency, never work |
| Shutdown | cancels rather than drains; Mongo pending state is the source of truth |
| No recursion | assessments, decisions and suggestions emit no signals; a full pass ends holding exactly the one signal it consumed |
| Legacy coexistence | `regenerate()` is never called by the orchestrator — it reaches the Proactive Engine only through the `submit_candidates` path separated in V2.9.3, so automatic reasoning adds **no** legacy generator cost |
| Deferred decisions | **partially operational, deliberately** — one-shot timer + startup recovery + `defer_status="due"` marker make them discoverable. Re-running attention on the same batch is NOT done: it needs a second decision for the same assessments, i.e. a change to V2.9.3's approved idempotency contract (CPO decision) |
| V2.9.4 tests | **39/39 passed** (`conversation_engine/tests/test_orchestration_v294.py`) |
| `conversation_engine/tests` (excl. `_live.py`) | **489/489 passed, 0 errors** |
| V2.9.3 / V2.9.2 / V2.9.1 | **104/104 passed** combined |
| **Proactive Engine (reached automatically now — full regression)** | **232/232 passed** |
| Calendar V2.8.6b + V2.8.6a | **56/56 passed** |
| `situations`/`life_memory`/`life_os`/`llm` | **44/44 passed** |
| Calendar connector legacy (`-n 0`) | **57/57 passed** |
| Provider Manager | **23/23 passed** |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — the only matches are the English noun "work" in two log strings |
| Security audit | **clean** — all lease/state queries user-scoped; the only cross-user reads are the once-per-boot recovery sweeps, each `.limit()`-capped; queue bounded; opaque owner id; no secret, no `.env`, no delete, no push, no tool execution |
| **Provider-real smoke** | **2/2 passed** against real Gemini — full pipeline signal→impact→attention end to end, plus the idle-user zero-cost guarantee |
| Chrome QA | see the report |
| Commit / push | **NO** — STOP for CPO review |

### Follow-up recommended for V2.9.5 (non-blocking, deliberately not built)

1. ~~**Deferred re-evaluation semantics**~~ — **closed by the hardening batch below.**
2. **Multi-process coordination** — the lease makes concurrent passes safe and cheap, but wake-ups are process-local: with N uvicorn workers only the process that served the mutation schedules one. Others rely on startup recovery. A shared trigger becomes worthwhile when ORA actually runs multiple processes.
3. **Actual delivery** — `notify` still resolves to a Home item; a real push channel needs consent flow, transport and rate policy.
4. **Retention/compaction** — signals, assessments, decisions and orchestration state all accumulate; nothing is deleted, deliberately, since the history is reasoning and audit material.
5. **Opportunistic wake-up on user activity** — login/Home-open could also trigger a best-effort pass; not added because the signal trigger already covers the cases that matter and this would add cost to every session start.

## V2.9.4 — Deferred re-evaluation final hardening (this batch)

**Status: closes the one open point left by the batch above. A `defer` decision whose moment
arrives is now genuinely RECONSIDERED by the AI — refreshed operational context, one Attention
call, the identical V2.9.3 gate — never merely flagged. "AI DECIDES. SYSTEM GUARANTEES." now covers
reconsideration too: the system bounds automatic cost, it never manufactures a verdict.**

| Item | Stato |
|------|--------|
| `life_attention/models.py` | `root_attention_key_for` (order-independent), `decision_key_for(..., revision=1)` (rev 1 ≡ pre-hardening key), `MAX_AUTOMATIC_DEFER_REEVALUATIONS = 3`, `AttentionDecision` gains `root_attention_key`/`attention_revision`/`supersedes_decision_id`/`superseded_by`/`automatic_re_evaluations_used`/`auto_re_evaluation_exhausted`, `AttentionPassReport` gains `defer_reevaluations_*`/`defer_budget_exhausted`/`defer_to_*` counters |
| `life_attention/repository.py` | `list_due_deferred` now excludes superseded/exhausted chains; new `latest_for_root`, `chain_for_root`, `mark_superseded` (called only after the replacement is durably persisted), `mark_budget_exhausted` |
| `life_attention/service.py` | `_evaluate_batch` factored into shared `_build_decision` (identical AI-vs-gate rules for a first evaluation and every reconsideration); new `reevaluate_due_deferrals` / `_reevaluate_one` / `_assessments_by_ids` — re-fetches the SAME assessments, never re-runs Impact Reasoning, never re-derives |
| `life_orchestration/service.py` | `_run_cycles` gains a third bounded step (due deferral → `reevaluate_due_deferrals`, guarded by a zero-AI existence check); `mark_due_deferrals` (flag-only) replaced by `has_due_deferral` (read-only existence check) |
| `life_orchestration/scheduler.py` | `_deferred_wake` / `recover_pending` no longer reconsider inline — they only confirm a deferral is still due (no AI) and queue `schedule_user_reasoning`; the actual reconsideration happens inside the lease-protected `run_user_pass`, exactly like every other AI call in this pipeline |
| Persistence order | build → persist new revision → **only then** mark previous superseded → done. No Mongo transaction introduced — this ordering already makes every step independently safe to retry or lose |
| Failure honesty | provider failure / invalid output / persistence failure all leave the old defer current, unsuperseded, with its automatic budget unspent |
| Budget semantics | exhausting `MAX_AUTOMATIC_DEFER_REEVALUATIONS` is a **cost** marker (`auto_re_evaluation_exhausted`) — the delivery stays whatever the AI last chose, never forced to `silent`; a brand-new `LifeChangeSignal` opens a fresh, unbounded root |
| New tests | **26/26 passed** (`conversation_engine/tests/test_deferred_reevaluation_v294.py`, A–Z) |
| V2.9.4 orchestration (updated) | **39/39 passed** (`conversation_engine/tests/test_orchestration_v294.py`) |
| V2.9.3 / V2.9.2 / V2.9.1 / conversation_engine / Proactive Engine / Life OS / Calendar / Context Broker / Context Graph / Situation / Memory / Provider Manager | **553/554 passed** — the one failure is `test_real_gemini_enrichment_optional` (`tests/test_ai_provider_manager.py`), an opt-in live-network test of the unrelated document-intelligence analyzer that failed on a real Gemini timeout + real OpenAI 429s; it touches no file this sprint changed |
| `compileall` / `flake8 --select=E9,F63,F7,F82` / `git diff --check` | **all clean** |
| Hardcoding audit | **clean** — zero domain terms in the new reconsideration code |
| Provider-real | **NOT REQUIRED** — the Attention prompt/contract did not change semantically; reconsideration reuses the exact same call shape V2.9.3's provider-real gate already covered |
| Chrome QA | **NOT REQUIRED** — no UI surface changed |
| Commit / push | **NO** — STOP for CPO review |

## PX1.1 — Product Experience Foundation (this batch)

**Status: the interface finally belongs to one product. One theme, one navigation model, one
geometry, one vocabulary — the foundations PX1.2–PX1.9 will build on. No screen was redesigned;
the house was.**

| Item | Stato |
|------|--------|
| **Calendar write consent (P0)** | **real bug found and fixed** — the document pipeline auto-called `confirm_event(sync_to_google=True)` above a 0.90 confidence score, writing real Google Calendar events unattended. Now unconditionally refuses; legacy preference inert and always reported `False` |
| Theme unification | `tokens.color`/`tokens.shadow` resolved dark while the provider resolved light; ~40 files read that static export at module load. Both now light, behind one reversible `CONSUMER_LIGHT_ONLY` constant |
| Information Architecture 2.0 | `Home · Vita · ORA · Attività · Documenti` + account set apart; Memoria demoted to a trust surface (reachable from Profilo); Documenti promoted out of the account menu |
| New route | `app/(tabs)/attivita.tsx` — named, empty, human copy; PX1.6 fills it |
| Desktop geometry | new `PageContainer` (≤800px centred decision column); applied to Profilo and Documenti, the two screens that set no width at all. Contextual rail (320px) reserved, renders nothing |
| Dev diagnostics | moved to `src/components/dev/DevDiagnostics.tsx`, `__DEV__`-gated — zero provider/model names in consumer settings |
| Profilo | "Prossimamente" group removed (spese/obiettivi/email/banche); Memoria link added |
| Snooze | human-time primitive (`src/components/ui/humanTime.ts`); no "(ore)" input; unchanged ISO wire format |
| New doc | `docs/PRODUCT_EXPERIENCE.md` — owns the binding rule *NEVER EXPOSE IMPLEMENTATION STATE WHEN A HUMAN STATE EXISTS* |
| Frontend tests | **PX1.1 guards pass** (`src/shell/px11Foundation.test.ts`, A–N); `actionLabels` and `softExit` still green |
| Typecheck | `tsc --noEmit` **clean** |
| Backend touched | **YES — only** `documents/intelligence/service.py`, for the consent fix authorised by §23–24. Cognitive core untouched |
| **Chrome QA (desktop + mobile)** | **completed on a real signed-in account** — Home, Vita, ORA, Attività, Documenti, Profilo, Impostazioni, snooze dialog; desktop 1440x900 and phone 375x812. Console clean on a fresh session |
| **QA-found regressions, all fixed** | raw `confidence` badges in Documents (card + detail panel); horizontal stats/filter rows vertically compressed to half height (**pre-existing**); "Documenti" truncating in the phone bar once labels reached the 12px floor; nested `<h1>` in `ContextsHeader` (**pre-existing**, invalid HTML + hydration error); "più tardi oggi" proposing 05:23 at 02:23 |
| Typography floor | `MIN_READABLE_FONT_SIZE = 12` declared and applied to navigation chrome (was 10) and document metadata (was 11) |
| Backend documents regression | **17/17 passed**, including the new consent test |
| Commit / push | **NO** — STOP for CPO review |

### Deferred by design

PX1.2 Home 3.0 · PX1.3 Workspace 2.0 · PX1.4 Conversation Experience · PX1.5 Vita/Memory trust UX ·
PX1.6 Activity Center · PX1.7 Documents UX 2.0 · PX1.8 Profile/Settings/Permissions ·
PX1.9 Motion/States/Accessibility.

## PX1.2 — Home 3.0 (this batch)

**Status: Home is now the canonical life dashboard — two columns on desktop, the
same hierarchy stacked on phone, every section rendering only from real payload
data.**

| Item | Stato |
|------|--------|
| New module `src/components/home/v3/` | `ContextualCardVisual`, `visualKind`, `HeroAdesso`, `HomeSections`, `ContextRail`, `HomeChrome`, `homeItemView` |
| Contextual imagery | semantic, derived from structural metadata (`type`/`card_type`/`source_type`) — never from titles. `imageSource` contract ready for a future `visual_key` |
| Action hierarchy | one primary CTA; secondary inline; snooze/ignore/correct in overflow and never primary |
| Sections | ADESSO · DOMANDE PER TE · OGGI · PIÙ AVANTI · AGGIORNAMENTI, each hidden when it has no real data |
| Contextual rail | real month grid (marks from the user's own dated items), upcoming, counts — no extra fetch |
| Desktop geometry (1280 measured) | nav 80 · main 788 (hero visual 260×260 side panel) · rail 340 — matches the reference structure |
| Mobile (375 / 390 / 430) | no horizontal overflow, zero elements wider than viewport, sections full width, tap targets ≥44 |
| API contracts | unchanged — `getHome`, `refreshHome`, `homeAction`, `acceptSuggestion`, `dismissSuggestion`, and the V2 dual-step navigation split |
| Backend touched | **NO** |
| Tests | PX1.2 guards **pass**; PX1.1, actionLabels, softExit still green; `tsc --noEmit` clean |
| Commit / push | **NO** — STOP for CPO review |

## V3.10 — CONNECTED LIFE — CLOSED

**Stato: chiusa.** Il ciclo calendario + posta → auto-sync → ingestion →
segnale → comprensione cross-source → Life Model → Home è stato dimostrato
end-to-end su un account Google vero, con l'ambient runtime acceso. Anche
l'ultima riga aperta — la latenza dell'auto-sync — è stata misurata e chiusa:
sei operazioni reali fra 9 s e 25 s, tutte dentro il bersaglio di 30 s.

| Punto | Stato |
|------|--------|
| Sprint 1 — Calendar come sensore | chiuso |
| Sprint 2 — reazione e consegna | chiuso |
| Sprint 3 — comunicazioni e cross-source | chiuso |
| Freschezza | calendario 20 s · posta 60 s · giro 10 s · nessun modello nel percorso — latenza reale misurata 9-25 s |
| Scrittura di ORA | archiviata subito, la Home non aspetta il giro |
| Scheda evento | titolo, giorno, ora, posto, provenienza — nessun id, nessun JSON |
| Elimina evento | un solo percorso: autorità sull'evento → provider → rilettura → «eliminato» |
| Dedupe | la decisione precede la scrittura; le riletture invariate non lasciano righe |
| Attuatori | `calendar.write` è l'unico; nessun `mail.send` |
| Corpo delle email | mai conservato: né ingestion, né segnale, né audit, né log, né frontend |
| Prodotto target | **iOS**. Nessun lavoro specifico Android |

**Prossimo: V3.11 — Financial Intelligence.** *(chiusa il 9 settembre 2026)*

**Roadmap futura (registrata, non pianificata):** agente vocale/telefonico
nazionale capace di fare telefonate reali previa autorizzazione esplicita
della persona.

