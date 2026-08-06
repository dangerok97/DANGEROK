# AI Document Understanding

Branch: `feature/life-experience-ai-documents` (from `feature/life-experience-ai` @ `c518a23`)

## Cos'è

Un livello di ragionamento AI **aggiuntivo** sopra Documents V2 (OCR/estrazione/classificazione invariati). Dopo che Documents V2 produce `extracted_text` + `analysis`, questo modulo chiama Gemini (via Provider Manager) per capire il documento a livello "life": tipo, dominio, entità, date con ruolo, importi con ruolo, obblighi ricorrenti, ambiguità, azioni consigliate — output **strutturato Pydantic**, mai JSON libero, mai chain-of-thought (solo `reason_summary` breve).

Il risultato è scritto come `doc["life_reasoning"]` **sullo stesso documento Documents V2** — nessuna seconda pipeline, nessun secondo storage.

## Modulo

`backend/documents/intelligence/life_reasoning.py`

| Funzione | Ruolo |
|---|---|
| `guess_document_type(text)` | Euristica di tipo documento da testo, usata come hint pre-Gemini |
| `content_fingerprint(text)` | Hash SHA-256 del testo → cache/dedup per `analysis_version` |
| `run_life_document_reasoning(doc, user, doc_type_hint, force)` | Entry point: cache → Gemini → fallback deterministico |
| `_system_prompt(...)` | Prompt di sistema IT, contesto minimo (mai credenziali/PIN/OTP) |
| `_llm_reason(...)` | Chiamata Gemini con chunking (max N chunk, skip pagine vuote/duplicate) |
| `_deterministic_fallback(...)` | Estrazione locale (regex/euristica) quando Gemini non è disponibile o l'output non valida |

## Modello `DocumentReasoning` (Pydantic)

Campi principali: `document_type`, `document_subtype`, `domain`, `purpose`, `title`, `summary`, `entities[]`, `relationships[]`, `dates[]` (con `role`: `reference|deadline|contract_start|contract_end`), `amounts[]` (con `role`: `total|installment|fee|recurring`), `recurring_obligations[]`, `recommended_actions[]`, `linked_life_objects[]`, `ambiguities[]`, `type_specific` (schema per tipo — vedi sotto), `confidence`, `reason_summary`, `provider`, `model`, `analysis_version`, `ai_used`.

Validazione difensiva: Gemini a volte restituisce numeri JSON dove lo schema si aspetta stringhe (es. importi `87.40` invece di `"87,40"`) — un validator `_coerce_optional_str` normalizza questi campi prima della validazione Pydantic, evitando fallback spurii.

## Schema per tipo documento (`type_specific`)

| `document_type` | Campi chiave |
|---|---|
| `rogito` | `address`, `price`, `deed_date`, `property_type`, `parties` |
| `contratto_locazione` | `address`, `monthly_rent`, `landlord`, `tenant` |
| `mutuo` | `lender`, `principal_amount`, `monthly_installment`, `interest_rate`, `end_date`, `property_address` |
| `bolletta` | `supplier`, `utility_type`, `amount_total`, `due_date`, `address`, `contract_code` |
| `libretto` | `plate`, `brand`, `model`, `vin`, `first_registration_date`, `fuel_type` |
| `polizza_auto` / `polizza_casa` | `company`, `policy_number`, `end_date`, `coverage_type`, `premium` |
| `piano_di_studi` | `institution`, `course_name`, `academic_year`, `exams[]`, `total_cfu` |

## Fallback onesto

Se Gemini non è configurato, è irraggiungibile, oppure il suo output non valida contro `DocumentReasoning` dopo i tentativi di normalizzazione: si usa `_deterministic_fallback` (regex/euristica locale). Il risultato porta sempre `ai_used=False`, `provider="local-deterministic"`, `model="local-deterministic"`, confidenza tipicamente bassa (~0.3–0.5). **La UI non mostra mai "Compreso da Gemini" se `ai_used` è falso** — mostra invece "Analisi locale — Gemini non disponibile in questo momento".

## Cache / dedup / telemetria

- Chiave cache: `content_fingerprint(text)` + `analysis_version` + `doc_type_hint`
- `force=True` (retry esplicito) bypassa la cache
- Telemetria salvata in `doc["life_reasoning_telemetry"]`: `latency_ms`, provider/model — **mai** testo del documento, mai prompt completo, mai segreti
- Chunking: testo lungo diviso in blocchi con un tetto massimo di chunk; pagine vuote o duplicate scartate prima dell'invio

## Verifica reale (Gemini live, questa sessione)

Query diretta su MongoDB (`documents.life_reasoning`) dopo le run E2E/pytest con `GEMINI_API_KEY` presente in `backend/.env`:

| `document_type` | `ai_used` | `provider` | `model` | `confidence` | `latency_ms` |
|---|---|---|---|---|---|
| rogito | true | gemini | gemini-flash-lite-latest | 0.99 | ~5820 |
| libretto | true | gemini | gemini-flash-lite-latest | 1.00 | ~4550–5510 |
| bolletta | true | gemini | gemini-flash-lite-latest | 1.00 | ~5740 |
| piano_di_studi | true | gemini | gemini-flash-lite-latest | 0.98 | ~5350 |
| (documento ambiguo/`altro`) | false | local-deterministic | local-deterministic | 0.35 | ~0.3 |

Nessun conteggio token esposto dal client `google-genai` in uso in questa versione — latenza sì.

## Privacy

- **Onestà sui limiti:** per capire un documento, il suo testo estratto (OCR/parsing di Documents V2) viene inviato a Gemini — non esiste redazione automatica di eventuali IBAN/PIN presenti nel testo sorgente stesso. Il guard `user_text_is_credential_dump` (usato lato chat conversazionale) qui **non** si applica in input, perché l'input è un documento intero, non testo libero digitato dall'utente.
- Cosa è realmente garantito lato **output**: il system prompt istruisce Gemini a non riportare mai password/PIN/OTP/IBAN completi/dati carta nei campi strutturati restituiti (`entities`, `type_specific`, ecc.) — questi valori vengono omessi anche se presenti nel testo.
- Contesto minimo: solo testo del documento corrente + hint di tipo, **mai** altri documenti dell'utente nello stesso prompt (no cross-document leakage all'AI).
- Raccomandazione prodotto: i tipi di documento supportati (rogito, bolletta, libretto, polizza, piano di studi, ecc.) non sono pensati per contenere credenziali; l'utente resta responsabile di non caricare documenti con dati di accesso.
- Log/telemetria: solo provider/model/latenza/esito — mai contenuto del documento, mai prompt completo, mai segreti.
