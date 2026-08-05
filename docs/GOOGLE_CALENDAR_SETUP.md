# Google Calendar — Setup locale

## Prerequisiti

1. Progetto Google Cloud con OAuth 2.0 Client (tipo Web).
2. Consent screen configurato (External o Internal).
3. Scope OAuth approvati / in test:
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/calendar.calendarlist.readonly`
   - `openid`, `email`, `profile`
4. MongoDB locale + backend ORA avviato.

## Variabili (`backend/.env`)

Copia da `backend/.env.example`:

```
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/connectors/google-calendar/oauth/callback
TOKEN_VAULT_BACKEND=local
TOKEN_VAULT_KEY=<fernet-key>
# oppure
# OAUTH_TOKEN_ENCRYPTION_KEY=<fernet-key>
CALENDAR_PROVIDER_MODE=real
```

Genera una chiave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Non** committare `.env` né chiavi reali.

## Redirect URI

Deve coincidere **esattamente** con Google Cloud Console:

`http://localhost:8000/api/connectors/google-calendar/oauth/callback`

## Separazione login vs Calendar

| Flusso | Scope calendario |
|--------|------------------|
| Login Google (account ORA) | No |
| Collega Google Calendar (Impostazioni) | Sì (events + calendarlist.readonly) |

## Passi UI

1. Impostazioni → **Collega Google Calendar**
2. Consenti nello schermo Google
3. Gestisci calendari → scegli calendario di test
4. Documento → conferma evento → **ORA + Google Calendar**

## Utenti già collegati (solo lettura)

Dopo l’upgrade scope, in Impostazioni compare **Ri-autorizza** / **Collega scrittura Google**.
Ricollegare per ottenere `calendar.events`.

## Revoca

Impostazioni → Disconnetti. I token in vault vengono revocati lato ORA; l’utente può anche revocare da Google Account → Sicurezza → Accesso terze parti.
