# Google Calendar — Verification log

Branch: `feature/google-calendar-sync`  
Data: 2026-08-05

## Test automatici (fake provider)

Suite: `backend/tests/test_google_calendar_write_sync.py`

Copertura mock (NON verifica reale Google):

- sanitizzazione privacy / titolo medico
- all-day + timezone Europe/Rome
- create / update / delete
- idempotenza `ora_event_id`
- conflitto etag
- isolamento utenti
- data ambigua senza override
- OAuth start + callback fake + status + calendari + default
- state errato
- endpoint senza auth

Eseguire:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_google_calendar_write_sync.py -q
```

Esito locale 2026-08-05: **15 passed** (fake provider only).

## Verifica reale Google

### Stato (2026-08-05 — aggiornato)

OAuth locale configurato. Connect reale OK. **Creazione evento reale verificata via Google Calendar API.**

### Checklist

Usa **solo eventi sintetici** (titolo tipo `ORA TEST SYNC <timestamp>`).

1. [x] Imposta client OAuth + redirect URI
2. [x] `CALENDAR_PROVIDER_MODE=real`, vault configurato
3. [x] Collega Google Calendar (consent con `calendar.events`)
4. [x] Elenca calendari reali
5. [x] Seleziona calendario primario
6. [x] Conferma evento documento → ORA + Google
7. [x] Verifica evento via API Google (`get_event`) — titolo `ORA TEST SYNC 20260805_094512`
8. [x] Modifica titolo → sync → verificato su Google (`ORA TEST SYNC UPDATED 094512`)
9. [x] `google_event_html_link` presente
10. [ ] Elimina con conferma “elimina anche Google”
11. [ ] Verifica rimozione / 404 gestito
12. [ ] Ripeti create → nessun duplicato
13. [ ] Disconnetti e ricollega
14. [ ] Verifica refresh token (attendi scadenza access o forza refresh)

### Esito reale (create)

| Campo | Valore |
|-------|--------|
| Account | francesconicolocefala@gmail.com |
| Draft | `ced_257959c863bd` |
| Google event id | `rf6v9s66o6tnpe8dukq3qdtk68` |
| Start | 2026-11-20T15:00 Europe/Rome |
| sync_status | synced |
| API get_event | PASS |

## Piattaforme

| Piattaforma | Stato |
|-------------|--------|
| Backend pytest (fake) | Da eseguire in CI/locale |
| Web autenticato | Parziale (UI aggiornata; OAuth reale non verificato) |
| Mobile nativo | Non verificato |
