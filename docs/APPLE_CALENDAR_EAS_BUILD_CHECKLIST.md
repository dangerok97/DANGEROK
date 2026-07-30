# ORA — Iterazione 18 — Checklist EAS iOS Development Build

> **Scopo del documento**: portare la Iterazione 18 (Apple Calendar / EventKit)
> dal preview web al tuo iPhone/iPad fisico per la validazione E2E dei permessi
> nativi. Fino a quando non hai fatto una build EAS, il flusso Apple Calendar
> **NON** funzionerà su Expo Go (limite nativo — EventKit non è disponibile).

---

## 0. Prerequisiti (una tantum)

- [ ] Account Apple Developer (99 $/anno) attivo — richiesto per firmare la build.
- [ ] macOS o accesso a un Mac (per generare il certificato di distribuzione la prima volta; EAS può farlo per te ma alcune operazioni richiedono un dispositivo Apple).
- [ ] iPhone/iPad con iOS 16+ (raccomandato iOS 17+ per NSCalendarsFullAccessUsageDescription).
- [ ] Accesso al progetto Emergent (l'account che possiede l'app).

---

## 1. Abilitare il feature flag lato backend (in produzione o preview)

Il flag è già configurato ma volutamente **OFF** in `/app/backend/.env`:

```
APPLE_CALENDAR_ENABLED="false"
```

Prima del test E2E su device, imposta a `true`:

- [ ] Modifica `/app/backend/.env` → `APPLE_CALENDAR_ENABLED="true"`
- [ ] Riavvia il backend: `sudo supervisorctl restart backend`
- [ ] Verifica: `curl -H "Authorization: Bearer <token>" \
       https://ora-decision-engine.preview.emergentagent.com/api/connectors/apple-calendar/config-status`
      → deve rispondere `{"enabled": true, ...}`

> 🛡️ **Sicurezza**: il flag protegge da chiamate accidentali quando la feature non è ancora pronta in produzione. Puoi riportarlo a `false` in qualsiasi momento.

---

## 2. Publish di ORA con Emergent (bottone in alto a destra)

Il modo più semplice (e supportato) di generare una build iOS è tramite il flusso
di deployment Emergent.

- [ ] Clicca **Publish** (angolo alto-destro dell'editor Emergent).
- [ ] Segui il wizard Emergent → sceglie iOS build (Development o Production).
- [ ] Inserisci le credenziali Apple richieste (Team ID, App-Specific Password se attivato).
- [ ] Attendi il completamento della build (5–20 minuti tipici).

> Emergent gestisce internamente `eas.json`, la firma e il caricamento del file `google-services.json` (se applicabile). **Non serve EAS CLI locale.**

---

## 3. Voci `Info.plist` — già configurate

Ho già aggiornato `/app/frontend/app.json` con:

```json
"ios": {
  "supportsTablet": true,
  "bundleIdentifier": "com.emergent.oradecisionengine.b7escs",
  "infoPlist": {
    "NSCalendarsFullAccessUsageDescription": "Legge i tuoi eventi per aiutarti a organizzare la giornata."
  }
}
```

e il plugin `expo-calendar`:

```json
"plugins": [
  "expo-router",
  ["expo-calendar", { "calendarPermission": "Leggi gli eventi del tuo calendario per organizzare la giornata." }],
  ...
]
```

Su iOS 17+ EventKit richiede **NSCalendarsFullAccessUsageDescription** (non più `NSCalendarsUsageDescription`). La stringa è breve (< 10 parole significative), chiara e user-focused come richiesto dall'App Store.

- [ ] Verifica in `app.json` che entrambe le chiavi siano presenti.
- [ ] Al momento della build EAS, il plugin `expo-calendar` genererà automaticamente anche le entitlements native.

---

## 4. Installazione della build sul device

Emergent genera una build **development** installabile via TestFlight o via
direct install (Ad Hoc):

- [ ] Riceverai un link di download / QR code da Emergent (`emergent.sh/builds/...`).
- [ ] Sull'iPhone:
  1. Apri il link nel browser Safari (**non** Chrome).
  2. Tocca "Install".
  3. Vai in **Impostazioni → Generali → VPN e gestione dispositivi**.
  4. Fidati del profilo dello sviluppatore ORA.
- [ ] Apri l'app ORA. Al primo lancio farà login.

---

## 5. Test E2E del flusso Apple Calendar

Sequenza da provare sul device:

1. **Login**
   - [ ] Accedi con `demo@ora.app` / `Demo!2026` (o registra un nuovo utente).

2. **Aprire Impostazioni**
   - [ ] Tab **Profilo** (bottom-nav) → **Impostazioni**.
   - [ ] Deve comparire la sezione "Apple Calendar" con il logo Apple.
     - Se non compare: verifica che `APPLE_CALENDAR_ENABLED=true` lato backend e ricarica.

3. **Avviare il flusso**
   - [ ] Tocca **Collega Apple Calendar** → si apre `/connect-apple-calendar`.

4. **Pre-permission explanation**
   - [ ] Vedi la card "Collega il tuo calendario" con i 3 bullet: Solo lettura / I dati restano tuoi / Zero duplicati.
   - [ ] Tocca **Consenti accesso al calendario**.

5. **Prompt nativo iOS**
   - [ ] Deve apparire il popup iOS "ORA vorrebbe accedere ai tuoi calendari"
         con il testo di `NSCalendarsFullAccessUsageDescription`.
   - [ ] Su iOS 17+: opzioni "Consenti accesso completo" / "Solo eventi selezionati" / "Non consentire".
     - Scegli **Consenti accesso completo** per il test.

6. **Selezione calendari**
   - [ ] Compaiono i calendari veri del tuo iPhone (iCloud, Local, Gmail collegati a iOS, ecc.).
   - [ ] Sono tutti pre-selezionati. Deseleziona quelli che non vuoi sincronizzare.
   - [ ] Tocca **Sincronizza N calendari**.

7. **Sync**
   - [ ] Card "Sto leggendo gli eventi…" (spinner).
   - [ ] Al termine: card verde "Calendario collegato" con conteggi:
     - **Eventi importati** = eventi nuovi
     - **Già presenti (Google)** = eventi presenti anche su Google Calendar (mirrored, primary tenuto)
     - **Aggiornati** = eventi già visti in un sync precedente
     - **Ignorati** = eventi malformati (dovrebbe essere 0)

8. **Verifica in Impostazioni**
   - [ ] Torna a `/settings` → la riga "Apple Calendar" ora mostra "Collegato" + numero di calendari + "Ultima sincronizzazione: adesso".

9. **Test deduplicazione cross-provider**
   - [ ] Se hai anche Google Calendar collegato E lo stesso evento su iCloud+Google, il conteggio "Già presenti (Google)" dovrebbe essere > 0 e non dovrebbero comparire eventi duplicati in Home.

10. **Test denial**
    - [ ] Ripeti il flusso da un altro utente/dispositivo negando il permesso.
    - [ ] Vedi la card "Accesso non concesso" → tocca **Riprova** → il popup iOS riappare.
    - [ ] Nega di nuovo → alla terza volta iOS non chiede più: dovrebbe apparire la card "Autorizzalo dalle Impostazioni" con bottone che apre direttamente Impostazioni → Privacy → Calendari → ORA.

11. **Test disconnect**
    - [ ] Impostazioni → Apple Calendar → **Disconnetti** → conferma.
    - [ ] Il conteggio in Home degli eventi di quei calendari deve diminuire (mirrored source rimosso, primary Google preservato).

---

## 6. Cose che DEVI verificare visivamente

| Punto | Aspettato | Se fallisce |
|-------|-----------|-------------|
| Sezione "Apple Calendar" appare in `/settings` | ✅ solo su iOS con `APPLE_CALENDAR_ENABLED=true` | Riavvia backend + verifica config-status |
| Prompt iOS mostra il testo corretto | "Legge i tuoi eventi per aiutarti a organizzare la giornata." | Rigenera la build EAS |
| Selezione calendari mostra i calendari veri | Elenco con colore + nome + provider (iCloud/Local) | Controlla `Calendar.getCalendarsAsync` in dev tools |
| Sync completa in <30s per 200 eventi | Card verde con conteggio | Controlla i log backend `calendar.sync` |
| Cross-provider dedup funziona | "Già presenti (Google)" > 0 | Verifica che il primary Google esista prima del sync Apple |
| Disconnect ripulisce mirrored | Google node resta, mirrored_sources vuoto | Query MongoDB `db.life_nodes` |

---

## 7. Logging backend utile

Su Emergent puoi vedere i log backend in tempo reale:

```bash
sudo tail -f /var/log/supervisor/backend.err.log | grep -E "apple_calendar|calendar.sync|connector.connect"
```

Eventi chiave che dovresti vedere:
- `connector.connect` con `apple_calendar_connected`
- `calendar.sync` con `records_returned=<N>`
- `consent.grant` per `calendar.read` sull'istanza appena creata

---

## 8. Rollback in caso di problemi

Se qualcosa va storto e vuoi tornare indietro senza uninstallare l'app:

1. [ ] Backend: `APPLE_CALENDAR_ENABLED="false"` + restart → la riga "Apple Calendar" scompare dalle Impostazioni; il client rifiuta chiamate `/sync` con 503.
2. [ ] Nessuna migrazione DB da annullare: mirrored_sources sono attributi non-breaking dei life_nodes esistenti.
3. [ ] Per rimuovere completamente i dati Apple ingeriti:
   ```
   POST /api/connectors/apple-calendar/instances/{id}/disconnect
   ```
   che marca ingestion_events come `detached` e pulisce mirrored_sources.

---

## 9. Prossimi step (fuori scope Iterazione 18)

- Attivare **Behavior-Aware Decision Engine Real Mode** (Iter17 lo ha lasciato in shadow).
- Connettore Email (Gmail / Apple Mail via IMAP).
- Connettore Health (Apple Health / Google Fit).
- Connettore Banking (PSD2 AIS).

---

## Riepilogo file toccati in Iterazione 18

### Backend
- `backend/connectors/apple_calendar/{__init__.py, scopes.py, normalizer.py, service.py, router.py}` (nuovo)
- `backend/ingestion/cross_provider.py` (nuovo — first-write-wins dedup)
- `backend/ingestion/{__init__.py, routing.py}` (esteso — content_key + mirrored_sources preservation)
- `backend/deps.py`, `backend/routers/__init__.py` (wiring)
- `backend/.env` (`APPLE_CALENDAR_ENABLED=false` di default)
- `backend/tests/test_iter18_apple_calendar_connector.py` (13 test, tutti passing)

### Frontend
- `frontend/src/utils/apple-calendar.ts` (nuovo — wrapper platform-safe di expo-calendar)
- `frontend/app/connect-apple-calendar.tsx` (nuovo — flow completo)
- `frontend/app/settings.tsx` (aggiunta sezione Apple Calendar con render condizionale)
- `frontend/src/api/client.ts` (aggiunte API + tipi)
- `frontend/app.json` (permesso NSCalendarsFullAccessUsageDescription + plugin expo-calendar)
- `frontend/package.json` (aggiunto `expo-calendar@15.0.8`)

---

**Contatti**: se qualcosa non funziona durante il test su device, prendi:
1. Screenshot del popup iOS (o dello step che fallisce).
2. Log backend degli ultimi 5 minuti (`sudo tail -100 /var/log/supervisor/backend.err.log`).
3. Segnalalo con il messaggio successivo e riprendiamo insieme.
