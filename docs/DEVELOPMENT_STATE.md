# ORA — Development State

Last updated: 2026-08-05 (Documents V2 rebuild)

## Branch

- Active: `feature/rebuild-intelligent-documents` (local, no push)
- Ancestor: `feature/google-calendar-sync` @ `213ea4f` (real Google create/update verified)

## Documents V2

| Item | Stato |
|------|--------|
| Hub API + prefs (auto-add default off) | implementato |
| Pipeline states V2 + migration stamp | implementato |
| FE hub `documenti.tsx` | ricostruito |
| FE detail utility-first labels | aggiornato |
| Settings auto-add toggle | implementato |
| Dati esistenti | preservati (no wipe) |
| Test `test_documents_v2.py` | da eseguire in sessione |
| Flashcard / interrogami avanzato | rimandato (hooks ask/summary presenti) |
| Confronto documenti admin | rimandato |

## Google Calendar

Real sync verified earlier on connected account (synthetic event). Auto-add uses same confirm+sync path.

## Next

1. Complete browser verification checklist in `DOCUMENTS_V2_VERIFICATION.md`
2. Expand study flashcard / quiz UI
3. Rotate OAuth client secret (was pasted in chat)
