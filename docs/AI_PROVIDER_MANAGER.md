# ORA — AI Provider Manager

Branch: `feature/ai-provider-manager`  
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

## Configurazione

| Env | Ruolo |
| --- | --- |
| `LLM_PROVIDER` | Preferenza processo (`gemini` default consigliato, o `auto`) |
| `GEMINI_API_KEY` | Chiave Google AI Studio / Cloud |
| `GEMINI_MODEL` | default `gemini-flash-lite-latest` (free-tier friendly; `gemini-2.0-flash` may 429 sooner) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI |
| `OLLAMA_ENABLED` / `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Locale |
| `EMERGENT_LLM_KEY` | Opzionale |

Preferenza utente (senza riavvio): `PATCH /api/llm/preferences` → `users.preferences.llm_provider`.  
Stato: `GET /api/llm/providers`.

## Costi (indicativi sviluppo)

| Provider | Costo tipico dev | Note |
| --- | --- | --- |
| Gemini Flash Lite | quota gratuita | **verificato** in locale su fixture sintetiche |
| Gemini 2.0 Flash | free tier | osservato 429 quota sullo stesso account |
| OpenAI | a consumo / quota account | failover (quota esaurita in test) |
| Ollama | gratis (locale) | richiede demone |
| Emergent | dipende dal piano | opzionale |

## Verifica reale (2026-08-05)

- Provider attivo: `gemini` / modello `gemini-flash-lite-latest`
- Fixture: concerto, dispensa, admin, visita → `ai_used=true`
- Latenza tipica: ~1.2–2.6 s per enrich
- Failover: attivato solo quando Flash standard era in 429; con lite non necessario

## Privacy

- Chiavi solo in `.env` backend, mai in FE o git
- Nessun prompt/documento nei log
- Testo a provider esterni solo con consenso AI documenti + flag `DOCUMENT_AI_ENABLED`
