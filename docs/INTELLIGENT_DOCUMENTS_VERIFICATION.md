# ORA — Intelligent documents verification

Branch: `feature/intelligent-documents-real-verification`  
Base: `feature/intelligent-documents` @ `65ef2e650cd91a254a99a258e218b0660ddf83a0`  
Data: 2026-08-05

## Verdict (honest)

| Layer | Status |
| --- | --- |
| Local parsing / taxonomy / events | **Verified** (pytest + HTTP) |
| Real OCR (Tesseract 5.4 host) | **Verified** (PNG/JPG/PDF scan + HTTP PNG) |
| Real OpenAI enrichment | **Not verified** — `OPENAI_API_KEY` absent in local `.env` |
| Internal calendar drafts | **Verified** (confirm + dedupe) |
| Brain merge / ask isolation | **Verified** (HTTP ask + 404 other user; Knowledge path best-effort) |
| Browser UI shell | **Partial** — `/documenti` empty state + upload CTAs visible |
| File picker OS | **Not verified** (not automatable here) |
| Mobile native | **Not verified** |
| Google Calendar sync | **Not started** (deferred) |

## Git

- Working branch: `feature/intelligent-documents-real-verification`
- Ancestor commit present: `65ef2e650cd91a254a99a258e218b0660ddf83a0`
- No push / no merge

## Format matrix

| Format | Upload | Extract | OCR | Classify | Analyze | Real verify |
| --- | --- | --- | --- | --- | --- | --- |
| TXT | yes | yes | n/a | yes | local | HTTP + pytest |
| Markdown | yes | yes | n/a | yes | local | pytest |
| CSV | yes | yes | n/a | yes | local | pytest |
| PDF text/image | yes | yes / OCR fallback | yes (scanned) | yes | local | OCR + HTTP |
| PNG / JPG | yes | via OCR | **real** | yes | local | OCR + HTTP PNG |
| DOCX | yes | **python-docx** | n/a | yes | local | HTTP + pytest |
| PPTX | yes | **python-pptx** | n/a | yes | local | pytest |

Legend: upload ≠ extract ≠ OCR ≠ AI. A format is not “AI supported” merely because upload accepts it.

## Synthetic cases (A–F)

| Case | Macro / sub | Event / action | Notes |
| --- | --- | --- | --- |
| A Visita | medical / medical_appointment | event @ 2027-09-18 10:30 Rome | no clinical advice; confirm required |
| B Concerto | event / concert_ticket | start 21:00 (not doors 19:30) | doors vs start separated in notes |
| C Treno | travel / train_ticket | Firenze → Roma | origin/dest distinct |
| D Dispensa | education / university_notes | education summaries | concepts/questions present |
| E Admin | administrative / official_communication | generic_action + due | confirmation required |
| F Ambigua | event + review | `ambiguous_date`, start null | `03/04/2027` not silently chosen |

Fixtures: `backend/tests/fixtures/intel_docs/` (synthetic only).

## OCR real

- Binary: `C:\Program Files\Tesseract-OCR\tesseract.exe` (v5.4.0)
- Install (Windows): `winget install UB-Mannheim.TesseractOCR`
- Env: `DOCUMENT_OCR_ENABLED=1`, optional `TESSERACT_CMD=...`
- Verified: readable PNG confidence ~0.63; tilted JPG; low-quality flagged; scanned PDF raster+OCR path; HTTP upload of `ocr_readable.png` → medical classification
- Temp files: none persisted by OCR path (in-memory buffers)
- Logs: no document body logged

## OpenAI provider

Configured adapter path:

- `LLM_PROVIDER=none|openai|emergent`
- Key only from backend env; never returned to FE; not logged; not committed
- Structured output via `llm.structured.chat_json` + Pydantic `LLMDocumentEnrichment`
- Cost controls: `DOCUMENT_AI_MAX_CHARS`, `DOCUMENT_AI_MAX_CHUNKS`, timeout, retries, content-hash dedupe
- Missing key: upload/archive/local analysis continue

**Real OpenAI calls were not executed** in this session (`OPENAI_API_KEY` empty). Model intended when enabled: value of `OPENAI_MODEL` (example `gpt-4o-mini`).

## Worker

In-process asyncio queue:

- recovery of `queued|extracting|classifying|analyzing`
- per-document lock + inflight dedupe
- max attempts = 3
- persisted `failed` + retry via reanalyze
- **Single-instance / local-dev only** — not multi-replica safe (no Redis)

## Tests executed

- `pytest tests/test_intelligent_documents.py tests/test_intelligent_documents_real_verification.py` → **28 passed, 1 skipped** (real OpenAI skip)
- HTTP multipart upload/analyze/confirm/dedupe/ask/maps/isolation
- Browser: `/documenti` shell (Metro toast observed; picker not driven)

## Manual procedure

1. Install Tesseract; set `TESSERACT_CMD` + `DOCUMENT_OCR_ENABLED=1`
2. Optionally set `LLM_PROVIDER=openai` + `OPENAI_API_KEY` + `DOCUMENT_AI_ENABLED=1`
3. Start Mongo + `uvicorn` + Expo web
4. Upload fixtures from `backend/tests/fixtures/intel_docs/`
5. Open detail → verify pipeline, title, classification, event/education
6. Edit field → confirm event → check calendar draft → double-confirm no duplicate
7. Reanalyze → confirmed title/event preserved
8. Maps / Indicazioni / Non aggiungere / Ricordamelo / Chiedi al documento
9. Second user must get 404 on ask/analysis

## Open issues

1. OpenAI real enrichment blocked by missing API key
2. File picker UI not e2e-automated
3. Mobile not verified
4. Expo Metro intermittent toast during browser check
5. Google Calendar sync deferred
