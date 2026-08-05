# ORA — Development State

Last updated: 2026-08-05 (AI Provider Manager)

## Branch

- Active: `feature/ai-provider-manager` (local, no push)
- Prior: `feature/intelligent-documents-real-verification`

## AI providers

| Provider | Configured locally | Real verified |
|----------|-------------------|---------------|
| Gemini | no key yet | **no** |
| OpenAI | key present | quota exceeded (not usable until billing) |
| Ollama | not running | no |
| Emergent | no | no |

Default priority: Gemini → OpenAI → Ollama → Emergent.  
Local parsing always available.

## Verified

- Provider Manager unit tests (failover mock) passed
- Intelligent docs local/OCR suite still green
- Settings UI section “AI Provider” added
- API `GET/PATCH /api/llm/*`

## Next

1. Add `GEMINI_API_KEY` and run real Gemini smoke on synthetic docs
2. Rotate exposed OpenAI key; fix OpenAI billing if needed
3. Manual UI pass on Settings → AI Provider
