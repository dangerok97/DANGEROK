# Cross-Document Reasoning

Branch: `feature/life-experience-ai-documents`

## Cos'è

Logica che confronta un documento appena capito (`DocumentReasoning` + campi mappati) con il Life Profile esistente per **collegare** (mai fondere) oggetti correlati e **rilevare** contraddizioni/duplicati, chiedendo sempre conferma invece di sovrascrivere in silenzio.

Modulo: `backend/life_setup/cross_document.py`

## Funzioni

| Funzione | Scopo |
|---|---|
| `find_related_documents(profile, domain, reasoning, new_document_id)` | Trova documenti/oggetti esistenti collegabili tramite identificatori ad **alta confidenza** (stesso indirizzo, stessa targa, stesso fornitore) |
| `detect_conflicts(profile, domain, mapped_fields, source_document_id)` | Confronta i nuovi campi mappati con i campi esistenti `confirmed`/`corrected` — se divergono, produce un `Conflict` invece di applicare il campo |
| `detect_duplicate_document(...)` | Rileva un documento dello stesso tipo con lo stesso identificatore normalizzato (es. stessa bolletta caricata due volte) |

## Regola d'oro: link, mai merge

- Il matching per **collegare** due oggetti richiede un identificatore ad alta confidenza condiviso (indirizzo normalizzato, targa, codice contratto fornitore) — **mai** una semplice similarità di titolo/testo.
- Nessuna fusione automatica di oggetti diversi: un secondo rogito con indirizzo diverso non viene mai unito al primo.
- I collegamenti trovati vengono salvati come `related_documents` nel `DomainProfile`, visibili nel risultato ("Documento originale" / cross-reference), mai come merge distruttivo dei dati.

## Conflitti → conferma, mai sovrascrittura silenziosa

Quando `detect_conflicts` trova un campo `confirmed`/`corrected` esistente con un nuovo valore ad alta confidenza divergente (es. bolletta con importo diverso dall'ultima confermata), il campo:

1. **Non** viene applicato automaticamente al profilo.
2. Viene aggiunto a `pending_confirmations` del dominio (`LifeProfileService.add_pending_confirmation`).
3. Compare nella UI sotto **"Dati da verificare"** con `needs_confirmation=true`, `existing_value` vs `new_value`.
4. L'utente sceglie esplicitamente: **"Usa il nuovo"** o **"Mantieni quello che avevo"** (`resolve_pending_confirmation`).

Nessun percorso del codice sovrascrive un campo `confirmed`/`corrected` senza passare da questo flusso.

## Duplicati

Un documento con lo stesso `document_type` + identificatore normalizzato (es. stesso codice contratto bolletta, stesso numero polizza) di uno già collegato viene segnalato come possibile duplicato: l'utente decide se si tratta di un rinnovo/aggiornamento (nuova scadenza) o di un vero doppione, mai un'assunzione automatica.

## Copertura test

`backend/ai_life_strategist/tests/test_life_experience_documents.py` include casi per: link tra documenti collegati (stesso indirizzo casa tra rogito e bolletta), conflitto su campo confermato, rilevamento duplicato con stesso identificatore.
