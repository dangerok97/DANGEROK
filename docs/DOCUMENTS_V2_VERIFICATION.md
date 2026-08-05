# Documents V2 — Verification

Branch: `feature/rebuild-intelligent-documents`

## Automated

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_documents_v2.py -q
```

## Real flows (checklist)

### Event
1. Upload synthetic concert/appointment txt
2. Hub shows card with smart title / Eventi filter
3. Detail → confirm ORA + Google (or auto-add if enabled)
4. Event on Google Calendar

### Study
1. Upload notes/dispensa
2. Macro education, summary/concepts visible
3. Ask document grounded

### Admin
1. Upload synthetic invoice
2. Amount/deadline/actions surfaced when extracted

### Safety
- Auto-add off by default
- Low confidence never auto-adds
- Legacy documents still open; version fields stamped

## Status log

| Check | Result |
|-------|--------|
| pytest V2 | **5 passed** |
| `tsc --noEmit` | OK |
| HTTP hub + prefs (auth user reale) | **200**; auto-add default false / 0.9 |
| Browser hub UI | reload Expo su `:8081` dopo rebuild |
| Google create | path conferma invariato (verificato in sessione Calendar sync) |
