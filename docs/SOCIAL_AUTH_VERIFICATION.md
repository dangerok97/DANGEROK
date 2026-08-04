# ORA — Verifica social auth

Data: 2026-08-04  
Branch: `feature/social-auth`

## Stato onesto

| Area | Stato |
|------|--------|
| Implementazione codice | Completata |
| Test mock / unit / service | Previsti in `backend/tests/test_social_auth_unit.py` |
| Email login | Deve restare operativo (regressione HTTP) |
| Google reale (web) | **Bloccato da credenziali** (`GOOGLE_WEB_CLIENT_ID`) |
| Apple reale (web/iOS) | **Bloccato da credenziali** (Services ID / capability / key) |
| iOS device | Non verificato |
| Android device | Non verificato |

## Implementato

- Collection `user_identities` + indici unici `(provider, provider_subject)`
- Migrazione non distruttiva identity `password` per utenti con hash
- `POST /api/auth/google` / `apple` — verifica ID token (JWKS) poi JWT ORA
- Link / unlink / list identities
- FE login con stati loading / non configurato
- Settings “Metodi di accesso”
- Legacy Emergent `google-session` resta gated

## Verificato con test mock

- Audience Google errata
- Token Google scaduto
- Token Google valido (claims iniettati)
- Nonce Apple errato
- Apple private relay
- Nuovo utente + login ripetuto senza duplicati
- Conflitto email con password
- Link + unlink unico provider rifiutato
- Separazione provider
- Apple secondo login senza nome/email preserva dati
- HTTP: body google vuoto → 422; providers; register/login/identities/logout

## Non verificato realmente

- Finestra Google consent + callback end-to-end
- Finestra Apple consent + callback
- Development build iOS/Android
- Persistenza SecureStore su device

## Limiti noti

- Logout non invalida JWT (comportamento preesistente)
- Apple web richiede HTTPS/return URL Apple-compliant
- Bundle ancora branded Emergent
- Auto-link per email disabilitato (solo legacy Google-only Emergent)
