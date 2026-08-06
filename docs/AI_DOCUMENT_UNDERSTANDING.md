# AI Document Understanding

Branch: `feature/life-experience-ai-documents`

## Cos'è

Un livello di ragionamento AI **aggiuntivo** sopra Documents V2 (OCR/estrazione/classificazione invariati). Dopo che Documents V2 produce `extracted_text` + `analysis`, il **Document Reasoner** chiama Gemini (via Provider Manager) per capire il documento a livello "life": tipo reale, contesto, beneficio, azioni, knowledge, relazioni, priorità, scadenze, criticità, documenti correlati — output **strutturato Pydantic**, mai JSON libero, mai chain-of-thought (solo `reason_summary` breve).

Il risultato è scritto come `doc["life_reasoning"]` **sullo stesso documento Documents V2** — nessuna seconda pipeline.

## Moduli

| Modulo | Ruolo |
|---|---|
| `documents/intelligence/document_reasoner.py` | Façade stabile |
| `documents/intelligence/life_reasoning.py` | Schema `DocumentReasoning`, prompt, Gemini + fallback |
| `documents/intelligence/document_context.py` | Contesto vita privacy-safe (profilo/goal/calendario/brain/doc noti) |
| `documents/intelligence/document_actions.py` | Azioni AI-first per «Cosa posso fare» |
| `documents/intelligence/document_memory.py` | Persistenza best-effort su Brain/Knowledge |
| `documents/intelligence/versions.py` | Schema version (stringa) vs revision counter (int) — **mai** `int("2.0")` |

## Versioni (importante)

| Campo | Tipo | Significato |
|---|---|---|
| `document_schema_version` | stringa semantica (`"2.0"`) | Forma del documento |
| `analysis_schema_version` | stringa semantica (`"2.0"`) | Forma del payload analysis |
| `analysis_version` | **int** (revision counter) | Quante volte è stata rianalizzata |
| `life_reasoning.analysis_version_tag` | stringa (`life-doc-understanding-2.0`) | Versione del reasoner |
| `processing_version` | stringa | Pipeline (`intel-docs-2.0`) |

Legacy: se in Mongo resta `analysis_version: "2.0"`, la migration lo sposta in `analysis_schema_version` e imposta il counter a `1`. Tutti i bump usano `coerce_analysis_revision` / `next_analysis_revision`.

## Contesto inviato a Gemini (minimo, privacy-safe)

- Testo OCR (chunkato) + metadata file + categoria stimata
- Slice Life Profile (valori + status, no dump completo)
- Goals / calendario / brain summary / documenti noti (titolo+tipo)
- Storia reasoner precedente (tipo/confidenza, non testo)
- **Mai**: password, PIN, OTP, IBAN completi, dati carta, dump interi di collezioni

## Schema `DocumentReasoning` (estratto)

`document_type`, `context`, `benefit`, `entities`, `relationships`, `dates`/`deadlines`, `amounts`, `recommended_actions` (motivo, beneficio, confidence, origine, documento, spiegazione), `knowledge`, `related_docs`, `linked_life_objects`, `priority`, `criticality`, `type_specific`, `confidence`, `reason_summary`, `ai_used`.

## Life Profile

Il mapping (`document_mapping.py`) applica fatti con provenance. Ipotesi (es. bolletta → contratto energia + `ownership_hypothesis`) restano **`suggested`**, mai overwrite di campi `confirmed`/`corrected`.

## Cross-document

`cross_document.py` collega (non fonde) rogito+mutuo+bollette sulla stessa casa, libretto+polizza sulla stessa targa, piano studi+verbale sullo stesso corso — solo identificatori normalizzati ad alta confidenza. Contraddizioni → conferma utente.

## Azioni e titoli promemoria

Azioni da AI reasoning (fallback locale assist-only). Titoli preferiti: «Pagamento bolletta Enel» / «Pagamento rata mutuo Intesa» invece di «Scadenza pagamento 87 EUR» (`_admin_deadline_title`).

## Fallback onesto

Senza Gemini: `ai_used=False`, `provider=local-deterministic`. La UI non deve mostrare «Compreso da Gemini».

## Test

- `tests/test_analysis_versions.py` — regressione `int("2.0")`
- `tests/test_ai_document_understanding.py` — fixture sintetiche (bolletta, mutuo, rogito, libretto, polizza, contratti, piano studi, busta paga, verbale, ambiguous, incomplete, duplicate, updated) + smoke Gemini opzionale
- `ai_life_strategist/tests/test_life_experience_documents.py` — LE E2E
- Playwright `life-experience-documents.spec.ts` — CASA / AUTO / BOLLETTA

## CI

`.github/workflows/ci.yml` — secret scan, compileall, pytest focused, tsc, Playwright web. Test Gemini reali **skip** senza `GEMINI_API_KEY`.
