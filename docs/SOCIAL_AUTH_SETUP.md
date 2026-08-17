# ORA — Setup Google & Apple Sign-In

Istruzioni ufficiali. Non inserire secret in git. Bundle/package attuali del progetto:

| Campo | Valore |
|-------|--------|
| iOS bundle ID | `com.emergent.oradecisionengine.b7escs` |
| Android package | `com.emergent.oradecisionengine.b7escs` |
| URL scheme | `frontend` |
| Backend locale | `http://127.0.0.1:8000` (also `http://localhost:8000`) |
| Expo web | `http://127.0.0.1:8081` **and** `http://localhost:8081` (different origins) |

---

## Google Cloud Console

Portale: [Google Cloud Console](https://console.cloud.google.com/)

1. Crea o seleziona un progetto.
2. **APIs & Services → OAuth consent screen** — configura app (External/Internal) con email di supporto.
3. **Credentials → Create credentials → OAuth client ID**:

### Client Web

- Tipo: **Web application**
- ORA web usa **Google Identity Services (GIS)** in modalità popup e riceve una `credential` ID token in callback.
- Authorized JavaScript origins (dev) — **entrambi obbligatori** se usi entrambi gli host:
  - `http://127.0.0.1:8081`
  - `http://localhost:8081`
- Produzione: aggiungi l'origin HTTPS esatto (schema + host + eventuale porta, senza path).
- **Authorized redirect URIs:** non richiesti dal flusso GIS popup di ORA. Non aggiungere callback Calendar o URL contenenti token.
- Se manca un origin, GIS non autorizza il frontend su quell’host.
- Copia il **Client ID** → `GOOGLE_WEB_CLIENT_ID` e `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`
- Imposta anche `GOOGLE_ALLOWED_CLIENT_IDS` con le audience effettivamente emesse (normalmente il Web/Server Client ID).

### Client iOS

- Tipo: **iOS**
- Bundle ID: `com.emergent.oradecisionengine.b7escs`
- → `GOOGLE_IOS_CLIENT_ID` / `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`
- `app.config.ts` deriva il reversed client ID e abilita il config plugin solo quando il valore è presente.
- Richiede development build/EAS; **Expo Go non è il target supportato**.

### Client Android

- Tipo: **Android**
- Package: `com.emergent.oradecisionengine.b7escs`
- Registra gli SHA-1 reali: debug, development/EAS, release e Play App Signing quando applicabili. Non copiarli da esempi.
- → `GOOGLE_ANDROID_CLIENT_ID` / `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`
- Richiede development build/EAS con il modulo native installato.

Il native SDK usa anche il Web/Server Client ID per richiedere l'ID token destinato al backend. I client iOS/Android identificano l'app installata. Verifica l'`aud` reale e inserisci nell'allowlist soltanto le audience necessarie.

### Contratto runtime ORA

Frontend (valori pubblici, nessun secret):

```env
EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID=
EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID=
EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID=
```

Backend:

```env
GOOGLE_WEB_CLIENT_ID=
GOOGLE_IOS_CLIENT_ID=
GOOGLE_ANDROID_CLIENT_ID=
GOOGLE_ALLOWED_CLIENT_IDS=
```

`GOOGLE_ALLOWED_CLIENT_IDS` è la allowlist esplicita. Se vuota, il fallback legacy accetta esclusivamente i tre client ID Login configurati. Non include mai `GOOGLE_OAUTH_CLIENT_ID`.

Calendar OAuth (`GOOGLE_OAUTH_CLIENT_*`, secret, callback, scope e refresh token) resta un flusso **separato** dal Login e non viene riutilizzato automaticamente.

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
