# Life Experience — Document Verification (onesta, per tipo)

Branch: `feature/life-experience-ai-documents`. Data: 2026-08-06.

**Principio guida:** "upload riuscito" non implica "supportato". Ogni riga sotto distingue: caricabile → testo estraibile → classificato → **capito dall'AI** → mappato nel Life Profile → **davvero verificato** (con quale metodo).

Legenda verifica: `pytest` (unit/integration su fixture sintetiche) · `pytest+Gemini reale` (stessa suite, con `GEMINI_API_KEY` presente) · `Playwright` (UI reale, file picker reale, browser) · `classificazione soltanto` (tipo riconosciuto, mapping/AI non testato end-to-end in questa sessione).

## Casa

| Documento | Caricabile | Testo estraibile | Classificato | **Capito dall'AI** | Mappato Life Profile | Davvero verificato |
|---|---|---|---|---|---|---|
| Rogito | ✅ | ✅ (TXT+PDF sintetico) | ✅ | ✅ Gemini reale (`gemini-flash-lite-latest`, conf. 0.99) | ✅ | **pytest + pytest+Gemini reale + Playwright (scenario CASA)** |
| Contratto di locazione | ✅ | ✅ | ✅ | Solo deterministico/mock in pytest | ✅ (`map_contratto_locazione`) | pytest (mapping+classificazione); **AI Gemini reale NON verificata** per questo tipo |
| Contratto di mutuo | ✅ | ✅ | ✅ | Solo deterministico/mock in pytest | ✅ (`map_mutuo`) | pytest (E2E attach→consume); **AI Gemini reale NON verificata** per questo tipo |
| Bolletta luce | ✅ | ✅ | ✅ | ✅ Gemini reale (conf. 1.00) | ✅ | **pytest + pytest+Gemini reale + Playwright (scenario BOLLETTA)** — include draft deadline `event_candidate` + UI «Salva promemoria su ORA» → confirm (no auto-calendar) |
| Bolletta gas | ✅ | ✅ | ✅ (classificato come `bolletta`) | Non testata con Gemini reale separatamente (stesso mapper della luce) | ✅ | classificazione + mapping via pytest; **AI Gemini reale NON verificata separatamente** (bolletta luce sì) |

## Auto

| Documento | Caricabile | Testo estraibile | Classificato | **Capito dall'AI** | Mappato Life Profile | Davvero verificato |
|---|---|---|---|---|---|---|
| Libretto di circolazione | ✅ | ✅ | ✅ | ✅ Gemini reale (conf. 1.00) | ✅ | **pytest + pytest+Gemini reale + Playwright (scenario AUTO)** |
| Polizza auto | ✅ | ✅ | ✅ | Solo deterministico/mock in pytest | ✅ (`map_polizza`) | pytest (E2E attach→consume); **AI Gemini reale NON verificata** per questo tipo |
| Finanziamento auto (prestito_auto) | ✅ | ✅ | ✅ (classificazione) | Non testato end-to-end | ✅ (`map_prestito_auto`, non esercitato in pytest E2E) | classificazione soltanto |

## Studio

| Documento | Caricabile | Testo estraibile | Classificato | **Capito dall'AI** | Mappato Life Profile | Davvero verificato |
|---|---|---|---|---|---|---|
| Piano di studi | ✅ | ✅ | ✅ | ✅ Gemini reale (conf. 0.98) | ✅ | **pytest + pytest+Gemini reale + Playwright** (fast-forward via API, upload non ripetuto in scenario dedicato) |
| Dispensa | ✅ | ✅ | ✅ (classificazione) | Non testato end-to-end con Gemini reale | ✅ (`map_dispensa`, non esercitato in pytest E2E) | classificazione soltanto |
| Calendario esami | ✅ | ✅ | ✅ (classificazione) | Non testato | Non testato (nessun mapper dedicato — passerebbe dal path generico) | classificazione soltanto |

## Amministrativo

| Documento | Caricabile | Testo estraibile | Classificato | **Capito dall'AI** | Mappato Life Profile | Davvero verificato |
|---|---|---|---|---|---|---|
| Contratto (generico) | ✅ | ✅ | ✅ (classificazione riconosciuta nel codice) | Non testato | Path generico, non esercitato in pytest | **non verificato in questa sessione** |
| Comunicazione | ✅ | ✅ | ✅ (classificazione riconosciuta nel codice) | Non testato | Path generico, non esercitato in pytest | **non verificato in questa sessione** |
| Fattura | ✅ | ✅ | ✅ | Testato con reasoning **mockato** (non Gemini reale) | ✅ (`finanze.importo_documento`, `finanze.scadenza_documento` via mapper generico) | pytest (mapping generico) |
| Ricevuta | ✅ | ✅ | ✅ (classificazione) | Non testato | Path generico, non esercitato in pytest | classificazione soltanto |

## Cosa significa onestamente

- **4 tipi con AI Document Understanding reale (Gemini) verificata**: rogito, bolletta (luce), libretto, piano di studi — esattamente i 4 richiesti esplicitamente per la verifica Gemini reale, con provider/model/confidenza/latenza registrati (vedi `AI_DOCUMENT_UNDERSTANDING.md`).
- **Altri 4 tipi con pipeline completa (upload→attach→consume→mapping) testata ma SENZA conferma Gemini reale dedicata**: contratto di locazione, mutuo, polizza auto, fattura (reasoning mockato/deterministico nei test, non una vera chiamata Gemini per questi specifici fixture).
- **5 tipi con classificazione riconosciuta nel codice ma senza test end-to-end di mapping/AI in questa sessione**: bolletta gas (mapper condiviso con bolletta luce, non testato separatamente), prestito auto, dispensa, calendario esami, contratto/comunicazione/ricevuta (questi ultimi tre passano dal path generico non specificamente esercitato).
- Questo **non è un difetto nascosto**: il fallback deterministico onesto (`ai_used=false`) si applica a qualunque documento se Gemini non è disponibile o l'output non valida — nessun tipo "si rompe" silenziosamente, ma solo 4 tipi hanno **evidenza reale** di comprensione Gemini in questa sessione.

## Backend test — conteggio

| Suite | Risultato |
|---|---|
| `backend/ai_life_strategist/tests/test_life_experience_documents.py` | **62 passed** (include regressione deadline → draft event + confirm) |
| `backend/tests/test_documents_v2.py` + suite sopra (focus reminder fix 2026-08-06) | **78 passed** |
| `python -m compileall life_setup documents ai_life_strategist tests` | OK, nessun errore di sintassi (sessione precedente) |

## Playwright — risultati reali

| Spec | Scenario | Esito |
|---|---|---|
| `frontend/e2e/life-experience-documents.spec.ts` | CASA: rogito → capito → correggi campo → conferma → re-plan → Home benefit → persistenza (reload + re-login) | ✅ passed (sessione feature) |
| `frontend/e2e/life-experience-documents.spec.ts` | AUTO: libretto → capito (targa `AB123CD` riconosciuta) → conferma → Home benefit auto | ✅ passed (sessione feature) |
| `frontend/e2e/life-experience-documents.spec.ts` | BOLLETTA: bolletta luce → fornitore/importo → **«Salva promemoria su ORA» obbligatorio** → confirm («Promemoria salvato su ORA.») → Home/Proactive | ✅ **re-passed 2026-08-06** (asserzione hard, non soft-if) |
| `frontend/e2e/life-experience-ai.spec.ts` (esistente, regressione) | Conversazione + upload rogito + explain + exit; conversazione→rogito→piano→interrupt→resume→Home→Proactive | ✅ 2/2 passed (sessione feature) |

Tutti e 3 gli scenari usano il **vero file picker Expo** (`expo-document-picker` → `<input type=file>` su web) intercettato da `page.waitForEvent('filechooser')` + `chooser.setFiles(...)` con fixture PDF/TXT sintetiche reali — non un percorso `synthetic_text` API-only per la parte di upload/analisi.

**Nota metodologica sulla navigazione conversazionale nei test:** poiché il Decision Engine sceglie ogni turno il gap con il maggior information-gain **tra tutti i domini** (non un wizard sequenziale per dominio), raggiungere deterministicamente la raccomandazione di un documento specifico richiede alcuni turni di `skip_domain` (lo stesso endpoint del bottone "Salta tema" della UI). Questi turni di navigazione sono guidati via API nei test per determinismo; **il file picker, l'upload, la comprensione AI, il pannello risultato, la conferma/correzione campi e gli effetti su Home/Proactive sono sempre esercitati tramite la UI reale**, mai stub.

## Fix scadenze bolletta (2026-08-06) — onesto

**Bug:** le bollette/fatture con `Scadenza pagamento:` estraevano `admin_analysis.due_date` e un `generic_action` testuale, ma **non** producevano un `event_candidate`. Inoltre, quando un candidate esiste, Documents V2 termina in `awaiting_confirmation`, e Life Experience **non** considerava quello stato `ready_for_consume` — l’UI restava su «In attesa di conferma» senza pannello risultato / «Salva promemoria su ORA».

**Fix:**
1. Estrazione label composta (`Scadenza pagamento:`) in `admin_extract.py`.
2. `_build_admin_deadline_event` in `analyzer.py` → `event_candidate` `category=deadline`, `status=proposed`.
3. `DOC_PIPELINE_TERMINAL` in Life Setup include `awaiting_confirmation` / `action_required`.
4. Playwright BOLLETTA richiede il bottone e il messaggio di conferma (non più soft-if).

**Non fatto / residuale:** sync Google Calendar reale dopo confirm (resta `sync_to_google=false` / draft ORA); bug preesistente `analysis_version` string `"2.0"` vs int può far fallire re-analyze di documenti stale in recovery worker.

## Limiti noti

- Nessun conteggio token esposto dal client Gemini in uso (solo latenza).
- Bolletta gas, contratto/comunicazione/ricevuta, dispensa, calendario esami, prestito auto: classificati nel codice ma non esercitati end-to-end con AI reale in questa sessione (vedi tabelle sopra).
- Mobile nativo (iOS/Android reale o emulatore): **non verificato** — vedi `LIFE_EXPERIENCE_REAL_DOCUMENTS.md` sezione compatibilità.
- Google Calendar: gli eventi da scadenza documento restano **draft-only** su conferma utente; la sync Google reale non è stata rieseguita in questa sessione.
