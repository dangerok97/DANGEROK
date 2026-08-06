# Life Experience — Real Document Upload

Branch: `feature/life-experience-ai-documents` (da `feature/life-experience-ai` @ `c518a23`)

## Cosa cambia rispetto a prima

Prima: nella conversazione Life Experience, "caricare un documento" era un percorso sintetico/API-only (`upload-doc` con `synthetic_text`), usato per test e2e ma non un vero picker file.

Ora: **file picker reale** (`expo-document-picker`, web = `<input type=file>` nativo intercettato da Playwright con `filechooser`), che avvia l'**upload binario reale** attraverso Documents V2 (`POST /api/documents/upload`) — l'unica pipeline di upload/OCR/storage/classificazione del prodotto. Life Experience non duplica nulla: collega, sonda lo stato, consuma il risultato, mappa nel Life Profile.

## Flusso end-to-end

```
Conversazione → ORA raccomanda un documento (rogito/libretto/bolletta/mutuo/piano di studi)
   → "Carica {label}" / "Non ora" / "Preferisco rispondere" / "Perché me lo chiedi?"
   → [Carica documento] → DocumentPicker reale → POST /api/documents/upload (Documents V2)
   → POST /life-setup/documents/attach {document_id, doc_type} → salva pending_document_id in sessione
   → poll GET /life-setup/documents/{id}/status (Documents V2 pipeline_status)
   → quando pronto: POST /life-setup/documents/{id}/consume
       → AI Document Understanding (Gemini/fallback) → life_reasoning
       → mapping dichiarativo → Life Profile (con provenienza)
       → cross-document reasoning (link/conflitti/duplicati)
       → re-plan AI Life Strategist (Home/Proactive/Goal aggiornati)
   → Document Result UI: Cosa ho capito / Dati trovati / Dati da verificare / Cosa posso fare / Documento originale
   → Conferma / Modifica / Rifiuta campo → Continua con ORA → prossima domanda (mai ripetuta)
```

## Schermata file picker (conversazione)

Quando `turn.recommended_document` è presente e nessun'analisi è in corso, il composer mostra:

- Bottone primario `Carica {label}` (es. "Carica Rogito / atto di compravendita")
- `Non ora` (posticipa, la domanda non viene ripetuta subito)
- `Preferisco rispondere` (passa alla domanda testuale equivalente)
- `Perché me lo chiedi?` (spiegazione breve del beneficio, mai catena di ragionamento)

Dopo la selezione file: nome file, tipo, dimensione (via `expo-document-picker` asset), stato di progresso (`docPhaseLabel` riflette lo stato pipeline reale di Documents V2: "in coda", "estrazione", "classificazione", ecc.), bottone `Annulla`.

Al termine dell'analisi il ritorno alla conversazione è **automatico** (polling, non richiede refresh manuale) e mostra il pannello risultato.

## API (solo endpoint aggiunti — nessuna duplicazione)

Documents V2 resta l'unica via per upload/validazione MIME-size/storage/OCR/estrazione/classificazione/analisi/retry/reanalyze/delete. Life Experience aggiunge **solo**:

| Metodo | Path | Ruolo |
|---|---|---|
| POST | `/api/life-setup/documents/attach` | Collega un `document_id` (già caricato via Documents V2) alla sessione Life Experience |
| GET | `/api/life-setup/documents/{id}/status` | Stato pipeline (proxy verso Documents V2, mai una seconda pipeline) |
| POST | `/api/life-setup/documents/{id}/consume` | Esegue AI Document Understanding + mapping + cross-document + re-plan, produce il Document Result |
| POST | `/api/life-setup/documents/{id}/retry` | Ri-accoda l'analisi (stessa pipeline, stesso documento) |
| POST | `/api/life-setup/documents/{id}/detach` | Rimuove la conoscenza derivata da Life Experience — il file e il documento restano su Documents V2 |
| POST | `/api/life-setup/documents/confirm-field` | Conferma un campo (`status → confirmed`) |
| POST | `/api/life-setup/documents/correct-field` | Corregge un campo (`status → corrected`, valore utente prevale per sempre) |
| POST | `/api/life-setup/documents/reject-field` | Rifiuta un campo (`status → rejected`, non riproposto) |
| POST | `/api/life-setup/documents/resolve-confirmation` | Risolve un conflitto cross-document (`use_new` / `keep_existing`) |

## Errori e resume — mai perdere `document_id` o stato pipeline

| Scenario | Comportamento |
|---|---|
| File non supportato / troppo grande | Errore Documents V2 propagato, messaggio umano, nessun documento orfano nella sessione |
| OCR fallito / nessun testo | `pipeline_status=failed` → `docPhase='error'`, "La lettura del documento non è riuscita", bottone `Riprova` (retry) |
| Gemini non disponibile | Fallback deterministico automatico, `ai_used=false` mostrato onestamente in UI |
| Output AI non valido | Fallback deterministico (mai un errore bloccante per l'utente) |
| Upload interrotto / chiusura app a metà | `pending_document_id` resta in sessione → al riapertura, `start()` restituisce `pending_document` e la UI mostra "Stavo analizzando {tipo}…" e riprende il polling/consume automaticamente |
| Riavvio backend durante analisi | Stato pipeline persistito su Mongo (Documents V2); al prossimo poll lo stato reale viene riletto, nessuna perdita |
| Timeout analisi (>2 minuti di polling) | Messaggio soft "Sto ancora leggendo il documento — riprova tra poco (nessun dato perso)", `document_id` resta valido per retry |
| Documento eliminato nel frattempo | 404 gestito esplicitamente, messaggio "Documento non trovato" |
| Utente non autorizzato (documento di altro utente) | 404 (mai leak di esistenza), stesso isolamento di Documents V2 |

## File coinvolti

| Layer | File |
|---|---|
| Conversazione FE | `frontend/app/life-setup/index.tsx` |
| Client API FE | `frontend/src/api/client.ts` (`lifeSetup*` functions) |
| Router | `backend/life_setup/router.py` |
| Servizio sessione | `backend/life_setup/service.py` (`attach_document`, `document_status`, `consume_document`, `confirm_field`, `correct_field`, `reject_field`, `retry_document`, `detach_document`) |
| AI Document Understanding | `backend/documents/intelligence/life_reasoning.py` |
| Mapping Life Profile | `backend/life_setup/document_mapping.py` |
| Cross-document | `backend/life_setup/cross_document.py` |
| Profilo/provenienza | `backend/life_setup/profile_service.py`, `backend/life_setup/models.py` |

## Compatibilità mobile (Expo DocumentPicker) — NON verificato su dispositivo/emulatore

Note di compatibilità preparate per iOS/Android, **non testate** in questa sessione (solo Playwright web è stato eseguito):

| Piattaforma | API usata | Note |
|---|---|---|
| Web (Playwright, verificato) | `expo-document-picker` → `<input type=file>` | `filechooser` di Playwright intercetta e imposta un file reale; comportamento verificato end-to-end |
| iOS | `expo-document-picker` → UIDocumentPickerViewController | Richiede permesso di accesso ai file (nessun permesso runtime aggiuntivo per file picker su iOS moderni); `copyToCacheDirectory: true` necessario per leggere il file selezionato prima dell'upload; testare `content://`/iCloud Drive/Files app come sorgenti |
| Android | `expo-document-picker` → Storage Access Framework | Nessun permesso runtime richiesto per SAF; testare URI `content://` da Google Drive/Downloads; verificare limiti dimensione su connessioni dati lente durante l'upload multipart |
| Entrambi | Upload multipart verso `POST /api/documents/upload` | Stesso endpoint usato da web; nessuna logica separata per mobile nel codice attuale, ma **non è stato eseguito** un build/emulatore reale in questa sessione |

**Dichiarazione esplicita:** mobile nativo (iOS/Android reali o emulatore) **non è stato verificato** in questo lavoro. Solo Playwright su Expo web è stato eseguito ed è verde. Non riportare "verificato su mobile" finché non viene eseguito un test reale su dispositivo/emulatore.
