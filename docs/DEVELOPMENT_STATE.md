# ORA — Development State

Last updated: 2026-08-05 (intelligent documents)

## Branch

- `feature/intelligent-documents` (local, no push)
- Prior: `feature/social-auth`, documents UI alignment

## Verified locally

- Intelligent docs pytest: 7 passed (+ documents local suite → 13 combined in last run)
- Frontend `tsc --noEmit` OK
- Backend restarted with intel worker
- Upload archive still works; analysis local without LLM

## Document intelligence

| Piece | Status |
|-------|--------|
| Pipeline states + in-process worker | implemented |
| Local taxonomy / events / education | implemented + tested |
| LLM enrichment | optional (`DOCUMENT_AI_ENABLED` + LLM provider) |
| Internal calendar drafts | implemented |
| Google Calendar sync from docs | deferred |
| OCR | existing Tesseract path; host-dependent |
| Mobile UI | not verified |

## Next

1. Real Google login E2E (credentials already partially set)
2. OpenAI key for document AI enrichment smoke
3. Apple Sign-In credentials
4. Do not start Attività/Promemoria until auth/docs stabilize
