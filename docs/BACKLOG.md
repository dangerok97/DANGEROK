# ORA — Backlog operativo

Attività piccole e verificabili derivate da `docs/ROADMAP.md` e dall’audit.

## BACKLOG-MEMO-COMPLEANNI — Memoria permanente e ricorrenze annuali

**Richiesta di prodotto registrata il 7 ottobre 2026. Stato: DA IMPLEMENTARE E VERIFICARE.**
Questa voce aggiunge un requisito al piano; non dichiara la funzione già disponibile e non crea promemoria reali. Non sostituisce il gate aperto sugli avvisi spontanei delle spedizioni.

**Esperienza richiesta.** L'utente comunica naturalmente un compleanno, per esempio «il 13 marzo è il compleanno di mia zia Elena». ORA salva persona, relazione e giorno/mese nella memoria permanente e prende in carico il promemoria annuale. L'esempio è un caso di collaudo, non un dato personale da inserire nell'account. Risposta attesa, soltanto dopo persistenza verificata della memoria e della ricorrenza: «Va bene, te lo ricorderò ogni 13 marzo».

**Regola esplicita di creazione della stella, precisata dall'utente:**
- Con **un solo compleanno distinto**, memoria permanente e ricorrenza annuale sono già attive, ma **la stella di gruppo “Compleanni” non deve ancora essere creata**.
- Al salvataggio del **secondo compleanno distinto**, ORA crea automaticamente **una sola stella permanente “Compleanni”**. Il tap apre l'elenco di tutti i compleanni registrati, inclusi il primo e il secondo.
- Dal terzo compleanno in poi si aggiorna lo stesso gruppo, senza nuove stelle di categoria o duplicazione delle voci.
- La soglia riguarda compleanni distinti effettivamente salvati, non il numero di messaggi: ripetere o correggere lo stesso compleanno non fa scattare il gruppo. Due persone diverse nate nello stesso giorno sono due compleanni distinti.

**Persistenza e autonomia.** La ricorrenza deve sopravvivere a chiusura dell'app, nuove chat, riavvii e cambio d'anno. Un avviso annuale non cancella la memoria e non esaurisce la ricorrenza: viene preparata l'occorrenza successiva. Memoria e promemoria devono essere verificati separatamente; nessuna promessa di avviso se il lavoro non è stato salvato. Non richiedere l'anno di nascita se non serve: giorno e mese bastano al compleanno annuale; nessuna età inventata. Rispettare fuso orario, preferenze e disponibilità reale dei canali di avviso, senza promettere push non abilitate.

**Modifiche e controllo dell'utente.** Correzioni di data/persona aggiornano la stessa voce e la relativa ricorrenza; disattivare un promemoria non equivale a dimenticare la data. Richieste di cancellazione devono eliminare soltanto i dati e gli avvisi pertinenti, rispettando le conferme previste. Omonimi e date ambigue richiedono il solo chiarimento necessario. La politica per il 29 febbraio e il comportamento del gruppo quando le voci tornano da due a una vanno definiti prima dell'implementazione, senza modificare la soglia iniziale richiesta.

**Criteri di accettazione:** primo compleanno persistito + ricorrenza, nessun gruppo; secondo distinto → un gruppo con entrambe le voci; terzo → stesso gruppo; duplicato/correzione → nessuna nuova voce o ricorrenza; avviso alla ricorrenza senza un secondo messaggio; memoria e promemoria mantenuti per l'anno successivo; isolamento tra utenti; nessuna notifica duplicata dopo retry o riavvio. Competenza della conversazione e della mappa esistente, non un pulsante principale o un'app separata.

## Priorità corrente — 25 settembre 2026

V4 autonomia trasversale anticipata prima di V3.23 su richiesta del
proprietario. Piano: [AUTONOMY_PROGRAM.md](AUTONOMY_PROGRAM.md).

1. A0: baseline fonti/capacità/configurazione e tracciamento completo.
2. A1–A2: recupero dettagli, relazioni e iniziativa senza perdita di lavoro.
3. A3–A4: risultato verificabile, autorità e recovery.
4. A5–A6: esperienza del risultato e prove trasversali/cloud.
5. Ripresa V3.23; alpha solo dopo i gate obbligatori della roadmap.

Primo task: riprodurre documento→opportunità→obiettivo→risultato senza Home,
inclusi burst oltre due opportunità e aggiornamenti; verificare il medesimo
passaggio con calendario. Modificare solo difetti confermati.

## Priorità precedente — 24 settembre 2026 (superata nell'ordine)

1. V3.21.3e: PASS confermato dall’utente.
2. V3.21.4: reality gate **Calendar PASS** sul provider reale e posizione/meteo **PASS** sul dispositivo reale. Mount persistente, sessioni/health, sync cloud e readiness telefonia non sono più blocker. History Git riscritta e tutti i ref pubblicizzati sono puliti; resta solo la purga GitHub Support perché un vecchio commit non raggiungibile è ancora risolvibile per SHA.
3. V3.22 **IN CORSO**: lifecycle dalla preparazione + continuation callback già implementati; recovery essenziale V3.15.2 ora copre pending stantii e failed transitori con stessa chiave, reconcile-first, massimo 3 tentativi, backoff e metriche aggregate. CI e Railway backend verdi. Restano due reality gate: telefonata reale dal cloud attraverso la UX completa e conflitto reale dell'application layer.
4. V3.23: iPhone reale con Railway, permessi e lifecycle.
5. V4: un caso proattivo completo; V4.1: alpha 3–5 persone dopo i gate minimi.

Criteri e fasi successive: `ROADMAP.md`, fonte canonica. Nessun GPT-Live, WhatsApp, banking o nuovo engine nel percorso immediato. Le sezioni sotto conservano lo storico.

---

## BACKLOG-SEMANTIC — Semantic Extraction + Gap Analyzer

- **Stato:** completato (2026-08-06, branch `feature/semantic-extraction-gap-analyzer`)
- **Obiettivo:** estrarre slot strutturati; domande dinamiche; fix “Fra due settimane parto”.
- **Aree:** `backend/semantic_engine/`, CE orchestrator, AE travel flow, FE action summary
- **Accettazione:** departure-only → destinazione; Vibo → alloggio; pytest 17; Playwright `semantic-extraction-gap.spec.ts`
- **Esito:** implementato; Gemini opzionale
- **Priorità:** critica (fatto)

## BACKLOG-001 — Allineare label “In arrivo” su moduli già vivi

- **Stato:** completato (2026-08-04, branch `feature/documents-ui-alignment`)
- **Obiettivo:** eliminare messaggi fuorvianti su Documenti/Foto in Profilo e Aggiungi.
- **Aree:** `frontend/app/(tabs)/profilo.tsx`, `frontend/app/(tabs)/aggiungi.tsx`
- **Accettazione:** Profilo non dice “Documenti In arrivo”; Aggiungi punta a upload/documenti reale o nasconde voci false.
- **Esito:** Profilo → Documenti attivo (“File caricati e archivio”); Aggiungi → Documento “Carica un file”; Foto resta “In arrivo”.
- **Test:** verifica UI manuale web su `/profilo` e `/aggiungi`.
- **Dipendenze:** nessuna.
- **Rischi:** basso.
- **Priorità:** critica.

## BACKLOG-002 — Smoke upload documento (web)

- **Stato:** completato (2026-08-04; dettagli in `docs/DOCUMENTS_VERIFICATION.md`)
- **Obiettivo:** dimostrare upload → list → detail.
- **Aree:** `frontend` documenti, `backend/documents`, `backend/tests/test_documents_local.py`.
- **Accettazione:** un PDF/txt di prova appare in lista; GET dettaglio 200; file su disco locale.
- **Esito:** pytest 6/6 + HTTP persistenza post re-login; storage locale `backend/data/documents/`.
- **Test:** HTTP multipart + UI empty state web; file picker OS non automatizzato.
- **Dipendenze:** backend up, Mongo.
- **Rischi:** differenze FormData web/native.
- **Priorità:** critica.

## BACKLOG-HOME-V2 — Rebuild Home as intelligence dashboard

- **Stato:** completato codice + pytest (2026-08-05, branch `feature/home-v2-intelligence`)
- **Obiettivo:** Home risponde “cosa è più utile sapere/fare adesso” con ranking reale multi-fonte.
- **Aree:** `backend/home/*`, `frontend/src/components/home/v2/*`, `frontend/app/situazione.tsx`, docs `HOME_V2_*`.
- **Accettazione:** `/api/home` aggrega fonti fail-soft; UI senza seed/static/dead buttons; Playwright web.
- **Test:** `tests/test_home_v2.py` (21); Playwright `e2e/home-v2.spec.ts`.
- **Non verificato:** native mobile.
- **Priorità:** critica.

## BACKLOG-ACTION-ENGINE — Guided priority flows

- **Stato:** codice + pytest (2026-08-05, branch `feature/ora-action-engine`)
- **Obiettivo:** Apri/Organizza/Inizia/card aprono sempre un flusso guidato (mai pagina vuota).
- **Aree:** `backend/action_engine/*`, CE router/service, `frontend/app/action/*`, Home wiring.
- **Accettazione:** API open→answer→complete; Brain/project/calendar/reminder; Home refresh; medical senza consigli.
- **Test:** `tests/test_action_engine.py`; regressione home_v2 / documents_v2.
- **Non verificato:** Playwright E2E Action Engine; native; weather live.
- **Priorità:** critica.

## BACKLOG-STUDY-ACTION-FLOW — Complete study plan conversational flow

- **Stato:** completato codice + pytest (2026-08-05, branch `feature/complete-study-action-flow`)
- **Obiettivo:** Intent study → piano confermato con sessioni/materiali/tools/Home/resume.
- **Aree:** `backend/action_engine/study/*`, AE router/service, `frontend/app/study-plan/*`.
- **Accettazione:** preview+confirm obbligatori; idempotency; Google/Gemini opzionali; niente complete silenzioso via API.
- **Test:** `tests/test_study_action_flow.py`; Playwright `e2e/study-action-flow.spec.ts`.
- **Non verificato:** native mobile; Google sync senza credenziali.
- **Priorità:** critica.

## BACKLOG-003 — Messaggi UI per LLM assente

- **Obiettivo:** su “Risolvi” e “Chiedi alla memoria”, mostrare copy italiano “AI non configurata” invece di errore grezzo.
- **Aree:** Home sheets / `memoria.tsx`, `humanizeErrorError`.
- **Accettazione:** senza `OPENAI_API_KEY`, tap mostra messaggio chiaro; app non crasha.
- **Test:** UI + HTTP 503 già esistente.
- **Dipendenze:** nessuna chiave.
- **Rischi:** basso.
- **Priorità:** alta.

## BACKLOG-004 — E2E Decision: completa e rimanda

- **Obiettivo:** verificare da UI che complete/postpone aggiornano Home e Mongo.
- **Aree:** `DecisionSheets`, `/decisions/{id}/complete|postpone`.
- **Accettazione:** dopo azione, decision non resta in focus; history ha evento.
- **Test:** HTTP già ok; aggiungere test UI o script.
- **Dipendenze:** BACKLOG-001 opzionale.
- **Rischi:** race refresh Home.
- **Priorità:** alta.

## BACKLOG-005 — Checklist loading/empty/error su Memoria e Documenti

- **Obiettivo:** allineare pattern Home (skeleton/offline/error).
- **Aree:** `memoria.tsx`, `documenti.tsx`, Skeleton components.
- **Accettazione:** spegnendo backend, banner/errore comprensibile; lista vuota ok.
- **Test:** manuale offline.
- **Dipendenze:** nessuna.
- **Rischi:** basso.
- **Priorità:** alta.

## BACKLOG-006 — Documentare e template Google OAuth locale

- **Obiettivo:** checklist copia-incolla per `GOOGLE_OAUTH_*` + redirect `localhost:8000`.
- **Aree:** `docs/GOOGLE_CALENDAR_ONBOARDING.md`, `.env.example`.
- **Accettazione:** sviluppator segue doc e ottiene config-status `provider_ready` (con secret reali).
- **Test:** config-status.
- **Dipendenze:** account Google Cloud (utente).
- **Rischi:** redirect mismatch.
- **Priorità:** alta.

## BACKLOG-007 — Deprecare API client legacy tasks

- **Obiettivo:** rimuovere metodi `/tasks` non usati dalle screen o marcarli deprecated.
- **Aree:** `frontend/src/api/client.ts`, grep usi.
- **Accettazione:** nessun import da screen attive; tsc OK.
- **Test:** tsc.
- **Dipendenze:** nessuna.
- **Rischi:** basso se grep completo.
- **Priorità:** media.

## BACKLOG-008 — Test CI smoke auth+health

- **Obiettivo:** job locale/CI che esegue `test_local_smoke.py`.
- **Aree:** scripts, eventuale `.github/workflows` (solo con consenso deploy CI).
- **Accettazione:** comando unico green su macchina con Mongo.
- **Test:** pytest -n 0.
- **Dipendenze:** Mongo.
- **Rischi:** flaky se porta occupata.
- **Priorità:** alta.

## BACKLOG-009 — Decisione prodotto su “Progetti”

- **Obiettivo:** decidere se introdurre progetti o restare su Decision+Life Graph.
- **Aree:** `docs/PRODUCT.md`, issue.
- **Accettazione:** decisione scritta; nessuna implementazione prematura.
- **Test:** n/a.
- **Dipendenze:** Creative/product owner.
- **Rischi:** scope creep.
- **Priorità:** media.

## BACKLOG-010 — OpenAI provider smoke (con chiave utente)

- **Obiettivo:** con `LLM_PROVIDER=openai` verificare resolve + memory ask.
- **Aree:** `.env` locale (non commit), `backend/llm`.
- **Accettazione:** entrambi 200; testo IT non vuoto.
- **Test:** HTTP manuale.
- **Dipendenze:** `OPENAI_API_KEY` dall’utente.
- **Rischi:** costo API.
- **Priorità:** alta (dopo chiave).

## BACKLOG-011 — Privacy: export/delete user data

- **Obiettivo:** endpoint o script documentato per cancellare dati utente locale.
- **Aree:** backend admin/user, docs privacy.
- **Accettazione:** utente di test rimosso da users/decisions/memories/docs.
- **Test:** script verifica count 0.
- **Dipendenze:** consenso prodotto.
- **Rischi:** cancellazione accidentale → dry-run.
- **Priorità:** alta pre-produzione.

## BACKLOG-012 — Google Login senza Emergent

- **Stato:** codice completato su `feature/social-auth`; **verifica reale bloccata da credenziali**
- **Obiettivo:** sostituire bridge Emergent con OAuth Google Identity.
- **Aree:** `backend/social_auth`, `auth.py`, login.tsx, env.
- **Accettazione:** login Google funziona in locale/staging senza `auth.emergentagent.com`.
- **Test:** mock OK; E2E reale dopo `GOOGLE_WEB_CLIENT_ID`.
- **Dipendenze:** Google Cloud OAuth web client.
- **Rischi:** alto (sessione, redirect).
- **Priorità:** critica (prossimo passo: credenziali).

## BACKLOG-014 — Documenti intelligenti (pipeline + azioni)

- **Stato:** **completato web** su `feature/documents-v2-completion` (pytest 15p; Playwright Chromium E2E: flashcards, Interrogami, dynamic detail, upload, search, re-login)
- **Obiettivo:** documento → comprensione → event/studio/azioni con conferma utente
- **Fatto:** hub/pipeline/auto-add gates; study tools; admin edit; provenance; fixtures; browser web
- **Rimane:** smoke mobile nativo; Gemini live opzionale; confronto multi-documento admin; re-check Google live dopo rotazione secret
- **Fatto (locale, sessione precedente):** Google Calendar write sync su evento sintetico

## BACKLOG-013 — Apple Sign-In reale (web e/o iOS)

- **Stato:** codice completato; verifica reale bloccata da credenziali / device
- **Obiettivo:** Sign in with Apple verificato almeno su web o iOS nativo.
- **Dipendenze:** Apple Developer (Services ID, key `.p8`, capability).
- **Priorità:** critica.
