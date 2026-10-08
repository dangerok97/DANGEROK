# ORA — Fase 1: prova del cervello AI reale in isolamento

**Checkpoint verificato:** 8 ottobre 2026 · v125 · ramo `staging/cloud` come destinazione.

## Che cosa abbiamo misurato

Per la prima volta in questa fase abbiamo fatto scegliere le skill al **modello
LLM reale configurato per ORA**, usando la stessa `llm.manager`, lo stesso
prompt cognitivo, il registro effettivo delle capability, la governance, la
sessione e il loop multi-skill impiegati nel backend.

Le richieste sono tre, formulate naturalmente in italiano:

1. **Spostamento:** pianificare la visita a un familiare, verificando calendario,
   percorso con traffico e condizioni meteorologiche.
2. **Situation temporanea:** panni stesi, verifica meteo e controllo successivo
   soltanto quando realmente programmato.
3. **Memo annuale:** compleanno di una zia fittizia il 13 marzo; memoria
   permanente e promemoria ricorrente da registrare prima della promessa.

Le decisioni AI e gli strumenti scelti non sono scriptati nel test *live*:
il modello vede il catalogo effettivo delle skill e decide come usarle.

## Il confine di sicurezza del test

- L'account è **inventato**; il database è creato ogni volta con
  `AsyncMongoMockClient` e vive soltanto nella memoria del processo.
- Calendario, tragitto, posizione e meteo rispondono tramite **fixture
  sintetiche**, mai da Google, Mapbox o Open-Meteo reale.
- `ToolRegistry.execute` è intercettato: email, telefonate, acquisti,
  calendari reali, conti, sensori del telefono e ogni altro effetto esterno
  sono **negati**. Non è un'opzione dell'LLM, ma un vincolo del runtime.
- Solo due scritture sono consentite: `schedule_situation_check` e
  `save_recurring_memo`, attraverso gli handler veri ma limitati a Mongo
  sintetico. Il controllo finale legge le registrazioni effettive.
- `research_available` è disabilitato: nessuna ricerca web aggiuntiva viene
  avviata dal modello per questi casi.
- Nessuna credenziale viene copiata in GitHub o nei file di risultato.
  Il servizio Railway di valutazione referenziava le credenziali già
  configurate nell'ambiente, non aveva dominio pubblico e **è stato eliminato
  al termine della prova**.

## Esito osservato con il modello reale

| Scenario | Decisioni AI | Skill / prove osservate | Esito |
|---|---:|---|---|
| Spostamento | 5 | `get_calendar_events`, `get_weather_forecast`, `get_route` | **PASS** |
| Panni e meteo | 5 | Meteo letto, Situation salvata, `schedule_situation_check` riuscito e confermato con read-back | **PASS** |
| Compleanno | 6 | Fatto salvato in `memories`, `save_recurring_memo` riuscito, ricorrenza in `recurring_memos` | **PASS** |

**Totale: 3 scenari su 3 superati** secondo i criteri di questo banco di prova.
La registrazione anonimizzata degli esiti è in
[`docs/evidence/phase1_real_model_synthetic_2026-10-08.json`](evidence/phase1_real_model_synthetic_2026-10-08.json).

Il primo tentativo in GitHub Actions aveva completato i test del runner ma
non era riuscito a chiamare un LLM, poiché GitHub non possiede una credenziale
di valutazione configurata. Un primo giro su Railway ha superato lo
spostamento, ma ha bloccato le scritture sintetiche e poi ha incontrato
indisponibilità del provider. Abbiamo corretto l'isolamento delle sole
scritture interne e usato la catena di provider esistente: il secondo giro
è quello dei risultati riportati qui.

**Nessun test ha creato un evento, inviato un messaggio, effettuato una
chiamata o modificato le memorie di un utente reale.**

## Come rieseguire la prova

Dalla cartella `backend`, con dipendenze presenti:

```bash
python -m pip install -r requirements-cloud.txt
python -m pip install mongomock-motor==0.0.36
python -m pytest -q tests/test_phase1_real_eval_runner_v125.py
python -m scripts.phase1_cognitive_live_eval --mode scripted --scenario trip
```

Il vero modello si usa **soltanto con una credenziale LLM esplicita**
nell'ambiente isolato:

```bash
python -m scripts.phase1_cognitive_live_eval --mode live --scenario all \
  --max-steps 7 --delay-between 12 --output /tmp/ora-phase1-eval.json
```

Il workflow
[`phase1-real-model-eval.yml`](../.github/workflows/phase1-real-model-eval.yml)
si attiva soltanto con push sul ramo di audit indicato o tramite
`workflow_dispatch`. Non è orario e non parte da un push su
`staging/cloud`. Se mancano le credenziali in GitHub, registra
`LIVE_MODEL_BLOCKED` e **non** attribuisce una prova live a quel workflow.

Il test CI obbligatorio del repository esegue le verifiche **scriptate**
del banco di prova, senza rete LLM. Il risultato live su Railway è una prova
separata, attribuita ai log del deployment temporaneo riportato nel JSON.

## Cosa NON è dimostrato da questi tre PASS

1. Che Google Calendar, routing e meteo restituiscano dati reali corretti
   sul telefono della persona.
2. Che il promemoria annuale venga effettivamente consegnato come push sul
   dispositivo nel giorno e all'ora previsti.
3. Che le conclusioni linguistiche del modello siano sempre le migliori:
   questa prima matrice controlla scelta delle skill, osservazioni e scritture,
   non attribuisce un punteggio semantico a orari di partenza o consigli.
4. Che errori intermittenti, provider diversi, più utenti o riavvii reali
   non creino perdita del piano o duplicati. La copertura attuale resta limitata
   a tre sessioni sintetiche e a un giro live riuscito.

**La Fase 1 non è ancora da dichiarare chiusa.** Il passaggio seguente è un
collaudo di integrazione su *account tecnico*, con credenziali e provider di
lettura reali, controlli di idempotenza, ripresa e audit delle conclusioni
dell'AI. La prova finale su dispositivi e utenti reali resta nelle fasi 5–6.

Le modifiche avvengono solo quando richieste dall'utente. Nessuna automazione
di sviluppo periodica è stata attivata.
