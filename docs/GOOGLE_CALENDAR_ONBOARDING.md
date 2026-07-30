# ORA — Google Calendar: primo test end-to-end

Guida operativa passo-passo per collegare **il primo account Google Calendar reale**
al backend ORA e verificare l'intero flusso di ingestion in preview.

> Tempo stimato: 20 minuti (10 min Google Cloud + 10 min verifica su ORA).

---

## Parte 1 — Progetto Google Cloud

### 1.1 Crea (o riutilizza) un progetto
1. Vai su https://console.cloud.google.com
2. In alto a sinistra, dropdown progetti → **New Project**
3. Nome: `ora-preview` (o simile). Organization: opzionale.
4. Clicca **Create**. Attendi 10-15s.
5. Assicurati che il progetto appena creato sia selezionato in alto.

### 1.2 Abilita la Google Calendar API
1. Menu ☰ → **APIs & Services** → **Library**
2. Cerca **Google Calendar API** → clicca sul risultato → **Enable**
3. Verifica: la pagina cambia in "API enabled".

### 1.3 OAuth consent screen
1. Menu ☰ → **APIs & Services** → **OAuth consent screen**
2. **User Type**: `External` → **Create**
3. **App information**
   - App name: `ORA (preview)`
   - User support email: la tua email
   - App logo: opzionale (skip)
4. **App domain** (opzionale in test): lascia vuoto
5. **Developer contact**: la tua email → **Save and Continue**
6. **Scopes**: clicca **Add or Remove Scopes** e aggiungi:
   - `openid`
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
   - `.../auth/calendar.readonly`
   - `.../auth/calendar.calendarlist.readonly`
   Poi **Update** → **Save and Continue**.
7. **Test users**: clicca **Add Users** → inserisci la/le email che userai per testare (max 100 in modalità test) → **Save and Continue**.
8. **Summary** → **Back to Dashboard**.

> ⚠️ In modalità *Testing* solo gli utenti nella lista possono completare il flow.
> Non serve la verifica Google finché resti su `External + Testing`.

### 1.4 Crea le credenziali OAuth Client ID
1. Menu ☰ → **APIs & Services** → **Credentials**
2. **+ Create Credentials** → **OAuth client ID**
3. **Application type**: `Web application`
4. **Name**: `ORA preview web`
5. **Authorized JavaScript origins**: aggiungi
   ```
   https://ora-decision-engine.preview.emergentagent.com
   ```
6. **Authorized redirect URIs**: aggiungi ESATTAMENTE (nessuno slash finale, nessun trailing):
   ```
   https://ora-decision-engine.preview.emergentagent.com/api/connectors/google-calendar/oauth/callback
   ```
7. **Create** → si aprirà un modal con **Client ID** e **Client Secret**.
   **Copia entrambi** — il secret non sarà più visualizzabile dopo la chiusura.

---

## Parte 2 — Configurazione ORA (Emergent)

### 2.1 Variabili d'ambiente da impostare in `/app/backend/.env`
Aggiornare le seguenti chiavi con i valori appena ottenuti:

```
GOOGLE_OAUTH_CLIENT_ID="<CLIENT_ID_APPENA_COPIATO>"
GOOGLE_OAUTH_CLIENT_SECRET="<CLIENT_SECRET_APPENA_COPIATO>"
GOOGLE_OAUTH_REDIRECT_URI="https://ora-decision-engine.preview.emergentagent.com/api/connectors/google-calendar/oauth/callback"
```

Devono già essere presenti (non toccare):
```
TOKEN_VAULT_BACKEND="fernet"
TOKEN_VAULT_KEY="<chiave Fernet 32-byte b64url>"
CALENDAR_PROVIDER_MODE="real"
CALENDAR_DECISION_GENERATION_ENABLED="false"
CALENDAR_CONTEXT_ENABLED="false"
```

### 2.2 (opzionale) Rigenera la chiave Fernet
Se necessario:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Incolla il risultato in `TOKEN_VAULT_KEY`.

> ⚠️ Cambiare la chiave Fernet invalida i token già salvati nel vault:
> qualsiasi istanza connesso in precedenza andrà revocata e ricollegata.

### 2.3 Riavvia il backend
```bash
sudo supervisorctl restart backend
```
Attendi ~3s che il processo si avvii.

---

## Parte 3 — Verifica di configurazione (prima di qualunque OAuth)

Autenticati come utente di test e chiama l'endpoint diagnostico
(`Bearer <TOKEN>` ottenuto da `/api/auth/login` o `/api/auth/register`).

```bash
BASE=https://ora-decision-engine.preview.emergentagent.com
TOKEN=<il tuo token>
curl -s $BASE/api/connectors/google-calendar/config-status \
     -H "Authorization: Bearer $TOKEN" | jq
```

Risultato atteso:
```json
{
  "provider_mode": "real",
  "client_id_configured": true,
  "client_secret_configured": true,
  "redirect_uri_configured": true,
  "token_vault_ready": true,
  "provider_ready": true,
  "missing_requirements": [],
  "environment": "preview",
  "connector_id": "calendar_google",
  "capability_id": "calendar.read"
}
```

Se `provider_ready` NON è `true`:
- verifica quale requisito è in `missing_requirements`;
- riapri `.env`, correggi e riavvia il backend;
- ripeti la chiamata.

> L'endpoint espone **solo booleani**: non stampa mai il Client ID, il Client
> Secret, il redirect URI configurato o la chiave Fernet.

---

## Parte 4 — Flusso OAuth reale end-to-end

### 4.1 Account di test
Usa una delle email inserite come **Test User** nel consent screen
(Parte 1.3, step 7). Se non ne hai aggiunte, torna indietro e aggiungile.

### 4.2 Avvia il flow OAuth
```bash
curl -s -X POST $BASE/api/connectors/google-calendar/oauth/start \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{}' | jq
```
Risposta:
```json
{
  "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "…",
  "provider_mode": "real",
  "expires_at": "…"
}
```

**Apri `authorize_url` in un browser** (la stessa sessione dove sei loggato su Google
con l'account di test). Google chiederà consenso agli scope readonly. Accetta.

### 4.3 Callback → creazione istanza
Google reindirizza al redirect URI (`/api/connectors/google-calendar/oauth/callback?code=…&state=…`).
Il backend:
1. Convalida `state` (one-shot, TTL 10 min).
2. Scambia `code` per access/refresh token via PKCE.
3. Recupera userinfo (sub + email).
4. Salva i token nel Token Vault (Fernet-encrypted).
5. Crea la `ConnectorInstance` con `status="connected"`, `secret_reference="sv_…"`.
6. Auto-grant del consenso ORA `calendar.read` sull'istanza.

Risposta JSON:
```json
{ "ok": true, "instance": { "id": "ci_…", "status": "connected", ... } }
```

### 4.4 Verifica ConnectorInstance
```bash
curl -s $BASE/api/connectors/google-calendar/instances \
     -H "Authorization: Bearer $TOKEN" | jq '.items[0]'
```
Controlla che:
- `secret_reference` inizi con `sv_`
- NON esistano campi `access_token` / `refresh_token` / `client_secret`
- `authorized_scopes` contenga gli scope readonly
- `poll_interval_min == 15`, `window_past_days == 30`, `window_future_days == 180`.

### 4.5 Elenca i calendari disponibili
```bash
INSTANCE_ID=<ci_… dal passo precedente>
curl -s $BASE/api/connectors/google-calendar/instances/$INSTANCE_ID/calendars \
     -H "Authorization: Bearer $TOKEN" | jq
```

### 4.6 Seleziona i calendari da sincronizzare
```bash
curl -s -X POST \
  $BASE/api/connectors/google-calendar/instances/$INSTANCE_ID/select-calendars \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"calendar_ids": ["primary"]}' | jq
```
> `"primary"` funziona come alias per il calendario predefinito.
> Puoi inserire più `calendar_ids` per selezionare più calendari.

### 4.7 Prima sync
```bash
curl -s -X POST \
  $BASE/api/connectors/google-calendar/instances/$INSTANCE_ID/sync \
  -H "Authorization: Bearer $TOKEN" | jq
```
Risposta attesa:
```json
{
  "instance_id": "ci_…",
  "totals": { "received": N, "processed": N, "skipped": 0, "quarantined": 0, "failed": 0, "cancelled": 0 },
  "per_calendar": [ ... ]
}
```
`N > 0` se l'account di test ha eventi nella finestra `-30/+180 giorni`.

### 4.8 Seconda sync (deve essere idempotente)
Rilancia la stessa chiamata: `totals.processed == 0`, `totals.skipped >= 1`.
Il cursor `sync_token` è ora persistito sull'istanza.

---

## Parte 5 — Verifiche di ingestion

### 5.1 Statistiche
```bash
curl -s $BASE/api/ingestion/stats -H "Authorization: Bearer $TOKEN" | jq
```
Esempio:
```json
{ "total": N, "by_connector": { "calendar_google": { "processed": N, ... } } }
```

### 5.2 Eventi ingestion
```bash
curl -s "$BASE/api/ingestion/events?connector_id=calendar_google&limit=20" \
     -H "Authorization: Bearer $TOKEN" | jq '.items[0]'
```
Verifica su un item:
- `ingestion_status == "processed"` (o `skipped` per la seconda run);
- `external_id` = event ID di Google;
- `payload_hash` valorizzato;
- `normalized_payload.title.value` = titolo evento;
- `raw_reference` contiene solo `calendar_id`, `external_event_id`, `htmlLink` (nessun token);
- `provenance.connector_id == "calendar_google"`.

### 5.3 Life Graph
```bash
curl -s "$BASE/api/life-graph/nodes?type=event" \
     -H "Authorization: Bearer $TOKEN" | jq '.items[0]'
```
Ogni evento Google diventa un `Node` di tipo `event` con:
- `attributes.external_event_id`
- `attributes.calendar_id`
- `attributes.canonical_key` = `cal:<instance>:<external_id>`
- `starts_at`, `ends_at`, `timezone`.

### 5.4 Knowledge Layer
Prendi l'ID di un nodo `event` (`node_id`):
```bash
NODE=<node_…>
curl -s $BASE/api/knowledge/nodes/$NODE \
     -H "Authorization: Bearer $TOKEN" | jq
```
`properties.starts_at.value`, `properties.calendar_name.value`,
`properties.location.value` devono essere presenti con la loro provenienza
`source_type=calendar_google`.

### 5.5 Nessuna Decision automatica (flag OFF)
```bash
curl -s $BASE/api/decisions -H "Authorization: Bearer $TOKEN" \
  | jq '[.items[] | select(.metadata.origin=="ingestion:calendar")]'
```
Attesa: `[]`. Il flag `CALENDAR_DECISION_GENERATION_ENABLED` è OFF di default.

### 5.6 Audit
```bash
curl -s "$BASE/api/permissions/audit?connector_id=calendar_google&limit=20" \
     -H "Authorization: Bearer $TOKEN" | jq '.items[].event_type' | sort | uniq -c
```
Ti aspetti almeno: `oauth.start`, `oauth.callback`, `calendar.list`, `calendar.select`,
`calendar.sync`, `consent.grant`. **NON** deve apparire nessun titolo evento nel body.

---

## Parte 6 — Revoca completa

```bash
curl -s -X POST \
  $BASE/api/connectors/google-calendar/instances/$INSTANCE_ID/revoke \
  -H "Authorization: Bearer $TOKEN" | jq
```
Verifica:
- risposta `status == "revoked"`;
- `curl $BASE/api/permissions/consents?status=active` → nessun consenso `calendar.read` per l'istanza;
- una nuova `/sync` sull'istanza restituisce **403 consent_denied**;
- ingested events risultano con `source_status == "detached"` (soft; i fatti utente non sono cancellati).

Per invalidare del tutto il grant lato Google:
1. Vai su https://myaccount.google.com/permissions
2. Individua l'app **ORA (preview)** → **Rimuovi accesso**.

---

## Troubleshooting

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `503 provider_not_configured` su `/oauth/start` | Manca uno di `GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI` | Verifica `.env` e riavvia backend |
| `redirect_uri_mismatch` da Google | URI di callback non identico a quello registrato | Copia ESATTAMENTE il redirect URI (nessun `/` finale) |
| `oauth_state_invalid` sul callback | `state` scaduto (>10 min) o già consumato | Ripeti `/oauth/start` |
| `access_denied` da Google | L'account non è nella lista Test Users | Aggiungilo nel consent screen |
| Sync riporta `0 received` | Nessun evento nella finestra `-30/+180 giorni`, oppure non hai chiamato `/select-calendars` | Crea un evento nel primo calendario e riprova; o seleziona esplicitamente |
| Test user con Workspace aziendale | Il consent screen è ancora *External* e il tenant blocca app non verificate | Usa un account Gmail personale, oppure procedi con la verifica Google |
| `403 consent_denied` sulla sync | Il consenso ORA è stato revocato | Rifai il flow OAuth per riottenere il consenso |

---

## Checklist ridotta (copia-incolla)

- [ ] Progetto Google Cloud creato
- [ ] Google Calendar API abilitata
- [ ] OAuth consent screen configurato (External + Testing)
- [ ] Scope readonly + userinfo.email/profile aggiunti
- [ ] Test users inseriti
- [ ] OAuth Client ID Web creato
- [ ] Redirect URI = `https://ora-decision-engine.preview.emergentagent.com/api/connectors/google-calendar/oauth/callback`
- [ ] `.env` aggiornato con `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
- [ ] Backend riavviato
- [ ] `/config-status` → `provider_ready: true`
- [ ] `/oauth/start` → 200 + `authorize_url`
- [ ] Consenso Google concesso via browser
- [ ] Callback → `instance.status == "connected"`
- [ ] `/instances/{id}/calendars` → elenco calendari
- [ ] `/select-calendars` → OK
- [ ] Prima `/sync` → `processed > 0`
- [ ] Seconda `/sync` → `skipped >= 1, processed == 0`
- [ ] `/ingestion/events` → item `processed`
- [ ] `/life-graph/nodes?type=event` → nodo evento presente
- [ ] `/knowledge/nodes/{node}` → properties `calendar_google`
- [ ] `/decisions` → nessuna Decision con `metadata.origin=="ingestion:calendar"`
- [ ] `/permissions/audit` → contiene eventi ma non titoli
- [ ] `/revoke` → 200 + `status: revoked`
- [ ] `/sync` post-revoca → 403 consent_denied
