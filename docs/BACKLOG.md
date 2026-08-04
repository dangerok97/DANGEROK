# ORA — Backlog operativo

Attività piccole e verificabili derivate da `docs/ROADMAP.md` e dall’audit.

---

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

## BACKLOG-003 — Messaggi UI per LLM assente

- **Obiettivo:** su “Risolvi” e “Chiedi alla memoria”, mostrare copy italiano “AI non configurata” invece di errore grezzo.
- **Aree:** Home sheets / `memoria.tsx`, `humanizeError`.
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

- **Obiettivo:** sostituire bridge Emergent con OAuth Google Identity.
- **Aree:** `auth.py`, login.tsx, env.
- **Accettazione:** login Google funziona in locale/staging senza `auth.emergentagent.com`.
- **Test:** E2E login.
- **Dipendenze:** Google Cloud OAuth web client.
- **Rischi:** alto (sessione, redirect).
- **Priorità:** media.
