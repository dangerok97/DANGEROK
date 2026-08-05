# Documents V2 — Privacy

- Preference `document_ai_analysis` (default on): if off → local parse only, no cloud LLM.
- Calendar auto-add default **off**; user opt-in.
- Medical Google titles stay discrete (`Visita specialistica`); no full clinical text to Google.
- No document body / tokens in logs.
- User isolation on all endpoints.
- Delete removes analysis + file (soft/hard as existing service).
- Path traversal / MIME / size limits unchanged from Documents foundation.
