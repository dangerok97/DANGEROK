# ORA — Development State

Last updated: 2026-08-05 (intelligent documents real verification)

## Branch

- Active: `feature/intelligent-documents-real-verification` (local, no push)
- Base: `feature/intelligent-documents` @ `65ef2e650cd91a254a99a258e218b0660ddf83a0`
- Prior: `feature/social-auth`, documents UI alignment

## Verified locally

- Intelligent docs pytest: **28 passed, 1 skipped** (real OpenAI skipped — no key)
- Real OCR via Tesseract 5.4 on synthetic PNG/JPG/PDF + HTTP PNG
- DOCX/PPTX local extract (`python-docx` / `python-pptx`)
- HTTP: upload → analyze → confirm/dedupe → ask → maps → isolation 404
- Browser: `/documenti` shell visible; file picker not automated
- Frontend Expo web running; Metro toast observed during check

## Document intelligence

| Piece | Status |
|-------|--------|
| Pipeline states + in-process worker + recovery | implemented + tested |
| Local taxonomy / events / education / admin | verified with synthetic cases A–F |
| LLM structured adapter (OpenAI) | implemented; **real call blocked** (no API key) |
| Internal calendar drafts | verified + idempotent confirm |
| Google Calendar sync from docs | deferred |
| OCR | **real verified** on this host |
| Mobile UI | not verified |

## Next

1. Provide `OPENAI_API_KEY` and re-run real AI enrichment smoke
2. Manual UI file-picker pass on web
3. Real Google login E2E
4. Apple Sign-In credentials
5. Do not start Attività/Promemoria until auth/docs stabilize
