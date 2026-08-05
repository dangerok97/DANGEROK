# ORA — Google Calendar Architecture

Branch: `feature/google-calendar-sync`  
Data: 2026-08-05

## Audit (pre-implementazione)

### Funzionante
- Login Google (ID token) **separato** da Calendar OAuth
- Calendar OAuth + PKCE + vault + inbound sync → `ingestion_events`
- Document confirm → `calendar_event_drafts` (solo interno)

### Scope precedenti
`calendar.readonly`, `calendar.calendarlist.readonly`, `openid`, `email`, `profile`

### Refresh token
Salvato cifrato in `secret_vault` (Fernet); riferimento in `connector_instances.secret_reference`

### Mancava
- Scope scrittura eventi
- `events.insert/patch/delete`
- Collegamento draft ↔ Google event id
- Scelta sync in UI dopo conferma documento
- Vault: `TOKEN_VAULT_BACKEND=local` non accettato (fix: alias → fernet)

## Design post-migrazione

```
Document confirm
  → calendar_event_drafts (sempre, interno)
  → opzionale sync_to_google
       → Google Calendar events.insert
       → sync_* fields on draft
```

Login Google ≠ Calendar OAuth. Connessione esplicita: Impostazioni → Google Calendar.

## Scope minimi (v1 write)

- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/calendar.calendarlist.readonly`
- `openid` `email` `profile`

Utenti già collegati devono **ri-autorizzare** per il nuovo scope.

## Modello credenziali (vault)

Payload cifrato in `secret_vault`:

| Campo | Note |
|-------|------|
| access_token | cifrato |
| refresh_token | cifrato |
| expires_at | ISO |
| scope | stringa Google |
| token_type | Bearer |

Metadati istanza: `user_id`, `provider`/`connector_id=calendar_google`, `google_account_email`, `authorized_scopes`, `created_at`/`updated_at`, `revoked` via status.

Chiave: `TOKEN_VAULT_KEY` o `OAUTH_TOKEN_ENCRYPTION_KEY` (Fernet).

## Modello evento (`calendar_event_drafts`)

Campi sync: `sync_provider`, `sync_status`, `google_calendar_id`, `google_event_id`, `google_event_html_link`, `google_event_etag`, `last_synced_at`, `sync_error`, `sync_version`.

Stati: `local_only` | `pending` | `synced` | `failed` | `conflict` | `revoked`.

Dedup: `ora_event_id` in `extendedProperties.private` + lock per draft + idempotenza confirm documento.

## Endpoint

Connettore esistente (OAuth/inbound):

- `POST /api/connectors/google-calendar/oauth/start`
- `GET /api/connectors/google-calendar/oauth/callback`
- `GET /api/connectors/google-calendar/instances/.../calendars`
- revoke / sync lettura

Write path documenti:

- `GET /api/documents/calendar/google/status`
- `GET /api/documents/calendar/google/calendars`
- `PATCH /api/documents/calendar/google/default`
- `POST /api/documents/{doc}/events/{ev}/confirm` (`sync_to_google`)
- `POST /api/documents/calendar/events/{draft_id}/sync|retry`
- `POST /api/documents/calendar/events/{draft_id}/resolve-conflict`
- `DELETE /api/documents/calendar/events/{draft_id}?also_delete_google=`

## Conflitti

Se etag Google ≠ etag salvato: `sync_status=conflict`. Risoluzione: `keep_google` | `overwrite_ora` | `unlink`.

## Sicurezza
- Token solo backend + vault Fernet
- Nessun refresh token al FE
- Descrizione Google: titolo + metadati minimi, mai testo documento completo
- Vedi `GOOGLE_CALENDAR_PRIVACY.md`
