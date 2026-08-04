# ORA — Setup Google & Apple Sign-In

Istruzioni ufficiali. Non inserire secret in git. Bundle/package attuali del progetto:

| Campo | Valore |
|-------|--------|
| iOS bundle ID | `com.emergent.oradecisionengine.b7escs` |
| Android package | `com.emergent.oradecisionengine.b7escs` |
| URL scheme | `frontend` |
| Backend locale | `http://127.0.0.1:8000` |
| Expo web | `http://127.0.0.1:8081` |

---

## Google Cloud Console

Portale: [Google Cloud Console](https://console.cloud.google.com/)

1. Crea o seleziona un progetto.
2. **APIs & Services → OAuth consent screen** — configura app (External/Internal) con email di supporto.
3. **Credentials → Create credentials → OAuth client ID**:

### Client Web

- Tipo: **Web application**
- Authorized JavaScript origins (dev):
  - `http://127.0.0.1:8081`
  - `http://localhost:8081`
- Authorized redirect URIs (dev, tipici Expo AuthSession):
  - `http://127.0.0.1:8081`
  - `https://auth.expo.io/@YOUR_EXPO_USERNAME/frontend` (se usi proxy Expo)
- Copia il **Client ID** → `GOOGLE_WEB_CLIENT_ID` e `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`

### Client iOS

- Tipo: **iOS**
- Bundle ID: `com.emergent.oradecisionengine.b7escs`
- → `GOOGLE_IOS_CLIENT_ID` / `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`

### Client Android

- Tipo: **Android**
- Package: `com.emergent.oradecisionengine.b7escs`
- SHA-1 (debug): da `keytool -list -v -keystore ~/.android/debug.keystore` (password `android`)
- → `GOOGLE_ANDROID_CLIENT_ID` / `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`

**Nota:** non riusare il solo client Web per iOS/Android in produzione. Il backend accetta come `aud` tutti i client ID configurati.

Calendar OAuth (`GOOGLE_OAUTH_CLIENT_*`) resta un flusso **separato** (connettore).

---

## Apple Developer

Portale: [Apple Developer](https://developer.apple.com/account)

### 1. App ID

- Identifiers → App IDs → seleziona/crea `com.emergent.oradecisionengine.b7escs`
- Capability: **Sign In with Apple**

### 2. Services ID (web / Android browser)

- Identifiers → Services IDs → New
- Es. `com.ora.app.web` (scegli il tuo; deve combaciare con `APPLE_SERVICE_ID` / `EXPO_PUBLIC_APPLE_SERVICE_ID`)
- Enable Sign In with Apple → Configure:
  - Domains: il dominio HTTPS pubblico (Apple non accetta `localhost` in produzione; per dev serve tunnel/HTTPS)
  - Return URLs: es. `https://YOUR_DOMAIN/login` o il redirect Expo dichiarato in `EXPO_PUBLIC_APPLE_REDIRECT_URI`

### 3. Key

- Keys → New → Enable **Sign In with Apple** → link all’App ID
- Scarica `.p8` **una sola volta**
- Annota **Key ID** e **Team ID**
- Salva `.p8` fuori dal repo; path in `APPLE_PRIVATE_KEY_PATH`
- Aggiungi a `.gitignore` (già coperto `*.p8`)

### 4. Variabili backend

```
APPLE_TEAM_ID=
APPLE_KEY_ID=
APPLE_CLIENT_ID=com.emergent.oradecisionengine.b7escs
APPLE_BUNDLE_ID=com.emergent.oradecisionengine.b7escs
APPLE_SERVICE_ID=
APPLE_REDIRECT_URI=
APPLE_PRIVATE_KEY_PATH=C:\secure\AuthKey_XXXXX.p8
```

La private key **non** va mai nel frontend.

### 5. Expo / EAS

- Development build consigliato per Google/Apple nativi (Expo Go ha limiti).
- `app.json` ha già `usesAppleSignIn: true` e plugin `expo-apple-authentication`.
- Per device: `eas build` / `npx expo run:ios` / `run:android` con entitlement Sign in with Apple.

---

## File `.env` locali (gitignored)

Copia da `.env.example` e compila. Riavvia uvicorn e Metro dopo ogni cambio.

---

## Verifica rapida post-config

```bash
curl http://127.0.0.1:8000/api/auth/providers
```

`google.configured` / `apple.configured` devono essere `true` quando i client ID sono presenti.
