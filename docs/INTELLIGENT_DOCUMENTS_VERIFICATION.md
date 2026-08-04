# ORA — Intelligent documents verification

Branch: `feature/intelligent-documents`  
Data: 2026-08-05

## Implementato

- Pipeline stati + worker in-process
- Analisi locale strutturata (taxonomy, event candidates, education)
- Arricchimento LLM opzionale
- Calendar draft interno (no Google sync)
- Maps deep link
- API analyze/events/ask/search
- UI dettaglio: stato, evento, studio, ask
- Test sintetici pytest

## Verificato con test

- Concert text → event candidate
- Notes → education
- Ambiguous date → review
- Confirm → internal calendar
- Isolation user B
- LLM absent → local_only
- Maps URLs

## Non verificato / limiti

- OCR reale su immagine (dipende Tesseract host)
- LLM arricchimento E2E (serve chiave)
- Google Calendar write (rimandato)
- iOS/Android UI
- PPTX/DOCX full text extract (upload ok, extract spesso mime_not_supported)

## Provider AI

Usa `backend/llm` (`none` / `openai` / `emergent`). Default locale senza chiave.
