# ORA — Verifica modulo Documenti

Data: 2026-08-04  
Branch: `feature/documents-ui-alignment`  
Ambiente: Windows locale, MongoDB, uvicorn `:8000`, Expo web `:8081`

## Cosa è operativo

- Tab Documenti: lista, empty state, ricerca, filtri sort, toggle archivio
- Upload file (web via `expo-document-picker` + `POST /api/documents/upload`)
- Elenco aggiornato dopo upload; navigazione al dettaglio
- Dettaglio `document/[id]`: nome, tipo, dimensione, data, stato (attivo/archiviato), insights deterministici
- Isolamento per `user_id` (utente B non vede/non apre doc di A → 404)
- Auth JWT richiesta su upload/list/detail
- Storage locale filesystem sotto `DOCUMENT_STORAGE_DIR` (default `backend/data/documents/<user_id>/…`)

## Cosa è stato testato

| Verifica | Metodo | Esito |
|----------|--------|-------|
| Upload autenticato + list + detail | pytest `test_documents_local.py` | PASS |
| Empty list | pytest | PASS |
| Unauthenticated upload | pytest → 401/403 | PASS |
| Isolamento utente A≠B | pytest → 404 | PASS |
| MIME non valido (exe) | pytest → 400 | PASS |
| Doc inesistente | pytest → 404 | PASS |
| Persistenza dopo re-login | HTTP script ad hoc | PASS |
| UI label Profilo Documenti attivo | browser web | PASS |
| UI Aggiungi Documento “Carica un file” | browser web | PASS |
| Empty state Documenti | browser web | PASS |
| File picker click → OS dialog | non automatizzato | — |

## Limiti web / mobile

- Verifica UI e upload picker eseguita su **Expo web** soltanto.
- iOS / Android **non** dichiarati verificati in questa release.
- Il file picker nativo dipende dalla piattaforma; su web usa il dialog browser.

## Limiti storage locale

- Nessun cloud (S3/GCS) in questa fase.
- File salvati su disco della macchina che esegue uvicorn; non sopravvivono a wipe della cartella `backend/data/`.
- Non adatto a multi-istanza senza volume condiviso.
- Backup/retention non implementati.
- Dimensione max default **25 MB** (`DOCUMENT_MAX_SIZE_BYTES`).
- MIME whitelist in `backend/documents/service.py` (`DEFAULT_ALLOWED_MIMES`).

## Non incluso (corretto)

- OCR, analisi AI, classificazione automatica avanzata, condivisione, sync cloud, modifica file.

## Problemi ancora aperti

- Upload UI progress: spinner/disabled durante upload (ok); nessuna percentuale byte-level.
- Insights “Contenuto” per PDF binari restano limitati (estrazione testo deterministica, non OCR).
- Native mobile non smoke-testato.
- BACKLOG-003+ (LLM UX, Decision E2E UI) indipendenti.
