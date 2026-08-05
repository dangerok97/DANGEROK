# ORA — AI Provider Manager

Branch: `chore/migrate-gemini-sdk`  
Data: 2026-08-05

## Architettura

```
App / Document Intelligence / Memory / Decisions
        │
        ▼
  llm.manager.ProviderManager
        │
   ┌────┼────┬────┐
   ▼    ▼    ▼    ▼
 Gemini OpenAI Ollama Emergent
```

- Interfaccia comune: `BaseLLMProvider` (`chat`, `analyze_document`, `classify_document`, `summarize`, `ask_document`, `extract_event`, `extract_education`, `embeddings`)
- L’app non importa SDK provider-specific
- Upload e parsing locale restano indipendenti dall’AI

## Priorità e fallback

1. Gemini  
2. OpenAI  
3. Ollama  
4. Emergent  

Su `quota` / `rate_limit` / `timeout` / errore server → provider successivo.  
Se nessuno è disponibile → parsing locale + warning (upload non bloccato).

### Fallback modelli Gemini (dentro il provider)

1. `GEMINI_MODEL` (default `gemini-flash-lite-latest`)
2. `GEMINI_FALLBACK_MODEL` (default `gemini-2.0-flash`) su model unavailable / blocked / invalid / empty / temporary
3. Poi failover Provider Manager verso OpenAI → Ollama → Emergent

Telemetry `usage` (senza prompt/testo/chiavi): `provider`, `model`, `latency_ms`, `outcome`, `fallback_used`, `models_tried`, token se disponibili.

## Configurazione

| Env | Ruolo |
| --- | --- |
| `LLM_PROVIDER` | Preferenza processo (`gemini` default consigliato, o `auto`) |
| `GEMINI_API_KEY` | Chiave Google AI Studio (unica fonte auth Gemini) |
| `GEMINI_MODEL` | default `gemini-flash-lite-latest` (free-tier friendly; `gemini-2.0-flash` may 429 sooner) |
| `GEMINI_FALLBACK_MODEL` | opzionale alternate model |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI |
| `OLLAMA_ENABLED` / `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Locale |
| `EMERGENT_LLM_KEY` | Opzionale |

Preferenza utente (senza riavvio): `PATCH /api/llm/preferences` → `users.preferences.llm_provider`.  
Stato: `GET /api/llm/providers`.

## SDK Gemini

| | |
| --- | --- |
| **Attuale** | `google-genai` (`from google import genai` → `Client`) |
| **Rimosso** | `google-generativeai` (deprecato: `genai.configure` / `GenerativeModel`) |

Adapter: `backend/llm/providers/gemini.py`. JSON mode via `response_mime_type=application/json`.

## Costi (indicativi sviluppo)

| Provider | Costo tipico dev | Note |
| --- | --- | --- |
| Gemini Flash Lite | quota gratuita | **verificato** post-migrazione SDK |
| Gemini 2.0 Flash | free tier | alternate / può 429 |
| OpenAI | a consumo / quota account | failover |
| Ollama | gratis (locale) | richiede demone |
| Emergent | dipende dal piano | opzionale |

## Verifica reale (2026-08-05, post `google-genai`)

- Provider attivo: `gemini` / modello `gemini-flash-lite-latest`
- Fixture: concerto, dispensa, admin, visita → `ai_used=true` (4/4)
- Latenza tipica: ~2.0–3.4 s per enrich
- `fallback_used=false` sul path di successo

## Privacy

- Chiavi solo in `.env` backend, mai in FE o git
- Nessun prompt/documento nei log
- Testo a provider esterni solo con consenso AI documenti + flag `DOCUMENT_AI_ENABLED`
