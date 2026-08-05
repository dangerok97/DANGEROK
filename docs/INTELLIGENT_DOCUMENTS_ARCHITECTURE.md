# ORA — Intelligent Documents Architecture

Branch: `feature/intelligent-documents-real-verification`  
Data: 2026-08-05

## Overview

Upload remains fast and isolated. Understanding runs asynchronously:

```
Upload → storage + Mongo doc → queue job
  → extract (PDF / OCR / text / DOCX / PPTX)
  → classify (legacy insights + taxonomy refine)
  → analyze (local structured + optional LLM JSON)
  → persist analysis / event_candidates / education
  → merge Knowledge / Life Graph (idempotent)
  → UI: confirm event / ask / maps / reanalyze
```

## Packages

| Path | Role |
| --- | --- |
| `backend/documents/extraction.py` | PDF, OCR (Tesseract), text; scanned-PDF OCR fallback via pypdfium2 |
| `backend/documents/office_extract.py` | DOCX / PPTX local extract |
| `backend/documents/intelligence/*` | pipeline, taxonomy, analyzer, worker, calendar |
| `backend/llm/manager.py` | Provider Manager (gemini → openai → ollama → emergent) |
| `backend/llm/providers/gemini.py` | Gemini via official `google-genai` Client |
| `backend/llm/structured.py` | validated JSON + chunking / cost controls |

## Pipeline states

`uploaded → queued → extracting → classifying → analyzing → action_required|needs_review|completed|failed`

## AI enrichment

- Optional; never required to boot or upload
- Structured schema `LLMDocumentEnrichment` (Pydantic)
- Chunking: `DOCUMENT_AI_MAX_CHARS` / `DOCUMENT_AI_MAX_CHUNKS`
- Dedup: `content_hash` skips new LLM call if unchanged
- Errors: not configured / timeout / rate limit / quota → local fallback + warning
- Gemini SDK: `google-genai` (not deprecated `google-generativeai`)

## Calendar

- Confirmation creates `calendar_event_drafts` with `provider=internal`
- Idempotent on double confirm
- Google/Apple write **not** wired from documents

## Worker limits

In-process asyncio queue + recovery loop. Suitable for local/single instance only.

## Privacy

See `INTELLIGENT_DOCUMENTS_PRIVACY.md`.
