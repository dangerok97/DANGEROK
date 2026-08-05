# ORA — Development State

Last updated: 2026-08-05 (Gemini real verification)

## Branch

- Active: `feature/ai-provider-manager` (local, no push)

## AI providers

| Provider | Configured | Real verified |
|----------|------------|---------------|
| Gemini | yes (`GEMINI_API_KEY`) | **yes** — model `gemini-flash-lite-latest` |
| OpenAI | yes | no (quota exceeded) |
| Ollama | off / not running | no |
| Emergent | no | no |

Default priority: Gemini → OpenAI → Ollama → Emergent.  
Note: `gemini-2.0-flash` returned 429 quota; `gemini-flash-lite-latest` succeeded.

## Gemini verification (synthetic fixtures)

| Fixture | ai_used | Notes |
|---------|---------|-------|
| caso_b_concerto | yes | title/summary + event start |
| caso_d_dispensa | yes | education enrich (after dict→list coerce) |
| caso_e_admin | yes | administrative summary |
| caso_a_visita | yes | medical appointment event |

Avg latency (successful AI calls): ~1.6–2.6s.

## Next

1. Migrate SDK from deprecated `google.generativeai` → `google.genai`
2. Rotate Gemini key (pasted in chat)
3. Optional: OpenAI billing restore for failover smoke
