# ORA — Social Auth Architecture

Data: 2026-08-04  
Branch: `feature/social-auth`

## 1. Architettura attuale (pre-intervento)

- Sessione unica: JWT ORA HS256 (`make_jwt` / `get_current_user`), 30 giorni.
- Login email/password operativo (`POST /api/auth/register|login`).
- Google: bridge Emergent `POST /api/auth/google-session` (off con `EMERGENT_GOOGLE_AUTH=0`).
- Apple Sign-In: solo UI placeholder.
- Utenti in `users` con `providers[]` e match per **email** (`upsert_user`) — nessun `sub` stabile.
- Google Calendar OAuth è un **connettore** separato (richiede già JWT).

## 2. Problemi individuati

1. Nessuna verifica ID token Google/Apple first-party.
2. Linking per sola email → rischio account takeover.
3. Apple mock; Google disabilitato senza Emergent.
4. Logout non invalida JWT.
5. Bundle/scheme ancora Emergent (`com.emergent.oradecisionengine.b7escs`, scheme `frontend`).
6. Nessuna collection `user_identities`.

## 3. Architettura proposta

```
FE (Google / Apple / Email)
  → proof (id_token / password)
  → Backend verifica col provider (JWKS)
  → resolve identity (provider + sub)
  → create/link user ORA
  → JWT ORA only
  → FE storage (SecureStore / web AsyncStorage)
```

Regole linking:

- Identità primaria = `(provider, provider_subject)`.
- Stessa email + password esistente → **non** auto-link; login password poi `POST /auth/link/{provider}`.
- Apple Private Relay: mai dedurre uguaglianza con email “reale”.
- Apple: non sovrascrivere nome/email con null al secondo login.
- Legacy Emergent Google-only (no password): se email_verified e stessa email, allega `sub` una volta (migrazione documentata).

## 4. File da modificare / aggiungere

- `backend/social_auth/*` (nuovo)
- `backend/routers/auth.py`, `backend/server.py`, `backend/deps.py` (minimo)
- `frontend/app/login.tsx`, `frontend/app/settings.tsx`, `frontend/src/api/client.ts`
- `frontend/src/auth/*` (Google/Apple helpers)
- `.env.example`, `.gitignore`, docs

## 5. Credenziali esterne indispensabili

| Provider | Dove | Cosa |
|----------|------|------|
| Google | Google Cloud Console | OAuth client Web (+ iOS/Android dedicati) |
| Apple | Apple Developer | App ID, Services ID, Key (.p8), Team ID, Key ID |

Vedi `docs/SOCIAL_AUTH_SETUP.md`.
