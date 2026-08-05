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

### Stato (2026-08-05)

**BLOCCATA** — in `backend/.env` locale **non** risultano:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`

Presenti: `TOKEN_VAULT_*`.  
Quindi **non** è stato possibile creare un evento reale su Google Calendar in questa sessione.

### Checklist da completare con credenziali

Usa **solo eventi sintetici** (titolo tipo `ORA TEST SYNC <timestamp>`).

1. [ ] Imposta client OAuth + redirect URI
2. [ ] `CALENDAR_PROVIDER_MODE=real`, vault configurato
3. [ ] Collega Google Calendar (consent con `calendar.events`)
4. [ ] Elenca calendari reali
5. [ ] Seleziona calendario di test (non personale critico)
6. [ ] Conferma evento documento → ORA + Google
7. [ ] Verifica evento su calendar.google.com
8. [ ] Modifica titolo/ora in ORA → sync → verifica aggiornamento
9. [ ] Apri `google_event_html_link`
10. [ ] Elimina con conferma “elimina anche Google”
11. [ ] Verifica rimozione / 404 gestito
12. [ ] Ripeti create → nessun duplicato
13. [ ] Disconnetti e ricollega
14. [ ] Verifica refresh token (attendi scadenza access o forza refresh)

### Esito reale

| Step | Esito |
|------|-------|
| Connect reale | Non eseguito (manca client OAuth) |
| Evento su Google | Non eseguito |
| Update / delete | Non eseguito |

**L’integrazione NON può essere dichiarata completa** finché un evento sintetico non compare realmente in Google Calendar.

## Piattaforme

| Piattaforma | Stato |
|-------------|--------|
| Backend pytest (fake) | Da eseguire in CI/locale |
| Web autenticato | Parziale (UI aggiornata; OAuth reale non verificato) |
| Mobile nativo | Non verificato |
