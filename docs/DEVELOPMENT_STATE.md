# ORA — Development State

Last updated: 2026-08-05 (Gemini SDK migration `google-genai`)

## Branch

- Active: `chore/migrate-gemini-sdk` (local, no push)
- Base ancestor: `80a4300125ff0b27e6cfdf43dafbf0ed7fb7a0d2` (Gemini real verification)

## AI providers

| Provider | Configured | Real verified |
|----------|------------|---------------|
| Gemini | yes (`GEMINI_API_KEY`) | **yes** — SDK `google-genai`, model `gemini-flash-lite-latest` |
| OpenAI | yes | no (quota exceeded) |
| Ollama | off / not running | no |
| Emergent | no | no |

Default priority: Gemini → OpenAI → Ollama → Emergent.  
SDK: `google-generativeai` **removed**; adapter uses official `google-genai` Client.

## Gemini verification (synthetic fixtures, post-migration)

| Fixture | ai_used | Notes |
|---------|---------|-------|
| caso_b_concerto | yes | ~3.4s |
| caso_d_dispensa | yes | ~2.4s |
| caso_e_admin | yes | ~2.0s |
| caso_a_visita | yes | ~2.2s |

## Next

1. Rotate Gemini key (pasted in prior chat)
2. Optional: OpenAI billing restore for failover smoke
3. Optional: prune unused transitive pins left from old generativeai stack
