# ORA — Development State

Last updated: 2026-08-05 (Google Calendar write sync)

## Branch

- Active: `feature/google-calendar-sync` (local, no push)
- Base ancestor: `a12fae3` (`chore: migrate Gemini provider to google-genai`)

## Google Calendar write sync

| Item | Stato |
|------|--------|
| Scope `calendar.events` + OAuth separato dal login | implementato |
| Vault `local`/`fernet` + `OAUTH_TOKEN_ENCRYPTION_KEY` | implementato |
| Draft sync fields + create/update/delete/conflict | implementato |
| UI conferma doc + Impostazioni write status | implementato |
| Test fake provider | suite `test_google_calendar_write_sync.py` |
| Verifica reale Google (evento su calendar.google.com) | **BLOCCATA** — manca `GOOGLE_OAUTH_CLIENT_ID/SECRET` in `.env` |

Documentazione: `docs/GOOGLE_CALENDAR_*.md`.

## AI providers

| Provider | Configured | Real verified |
|----------|------------|---------------|
| Gemini | yes (`GEMINI_API_KEY`) | **yes** — SDK `google-genai`, model `gemini-flash-lite-latest` |
| OpenAI | yes | no (quota exceeded) |
| Ollama | off / not running | no |
| Emergent | no | no |

## Next

1. Aggiungere `GOOGLE_OAUTH_*` locali e completare checklist in `GOOGLE_CALENDAR_VERIFICATION.md`
2. Rotate Gemini key (pasted in prior chat)
3. Optional: OpenAI billing restore for failover smoke
