# Life Object Engine

**Stato:** SHADOW + Semantic Integrity v2 + **Digital Twin Knowledge Model** (2026-08-07)  
**Branch:** `feature/life-object-engine`  
**Home V3 Life Objects UI:** PREDISPOSTO (`LIFE_OBJECT_HOME_UI_ENABLED=0`) — **non shippato**. Home resta Goal-aware.

## Digital Twin Knowledge Model

Layer interno (`life_objects/knowledge_model/`): **facts | hypotheses | decisions | goals(link) | memory** + timeline semantica.  
**Fact mai cancellato** (solo supersede/archive). Hypothesis mai auto-promossa a Fact.  
Dettaglio: `LIFE_KNOWLEDGE_MODEL.md`, `DIGITAL_TWIN_MODEL.md`, `FACTS_HYPOTHESES_DECISIONS.md`.

## Visione

Il Life Object Engine è il **modello vivente della realtà dell’utente**.  
Nuovi documenti e conversazioni arricchiscono entità reali; l’AI interpreta/collega/propone; il **backend garantisce coerenza, integrità e assenza di invenzioni**.

```
Document → OCR → Document AI → Life Object AI → Semantic Validator → Canonical Object → (future Home)
```

Il **Semantic Validator** gira **sempre** prima del persist.

## AI = consultant; Backend = autorità

| Ruolo | Può | Non può |
|-------|-----|---------|
| **Gemini** | suggerire, classificare, spiegare, estrarre, proporre merge | decidere titolo/tipo finale, auto-merge, cancellare, inventare campi, creare conflitti |
| **Backend** | tipo, titolo canonico, assimilazione, campi, link state, persist | — |

## Feature flags

| Flag | Default | Effetto |
|------|---------|---------|
| `LIFE_OBJECT_ENGINE_ENABLED` | `1` | Shadow writes ON |
| `LIFE_OBJECT_HOME_UI_ENABLED` | `0` | Home V3 oggetti OFF (UX invariata) |
| `LIFE_OBJECT_GEMINI` | `1` | Reasoning + enrichment Gemini; fallback IT se assente |

## Componenti v2

| Modulo | Ruolo |
|--------|-------|
| `semantic_validator.py` | Coerenza type/title/fields; blocca HOME+«Lavoro» |
| `title_generator.py` | Titoli deterministici (mai testo AI finale) |
| `property_registry.py` | Campi canonici + alias + mapper |
| `knowledge_gaps.py` | Domande su CONCETTI (non nomi grezzi) |
| `assimilation.py` | Mutuo/bolletta aggiornano HOME.state (no pile merge) |
| `link_states.py` | LINK_CONFIRMED / PROBABLE / UNCERTAIN / REAL_CONFLICT |
| Health 2.0 | Dimensioni spiegabili; mai 100% con conflitti/mutuo non assimilato |
| Provenance | `document_sources`, `goal_sources`, … + `total_sources` |

## Identity vs State

| Piano | Significato | Esempi |
|-------|-------------|--------|
| **Identity** | Cosa definisce l’oggetto | indirizzo, catastale, POD/PDR, targa, VIN |
| **State** | Cosa cambia nel tempo | fornitore, importi, rata, compagnia |

## Link states

- **LINK_CONFIRMED / LINK_PROBABLE** — silenziosi; assimilazione consentita  
- **LINK_UNCERTAIN** — backend trattiene; no seconda Casa silenziosa  
- **REAL_CONFLICT** — **unico** user-facing / home-disturbing  

## Home V3 DTO (flag OFF)

Campi: `life_object_id`, `life_domain`, `health`, `next_action`, `benefits`, `questions`, `insights`, `timeline`, `related_documents`, `related_goals`, `related_projects`.

## Cosa NON fa ancora

- Nessuna modifica UX Home  
- Nessuna schermata Life Objects  
- Home V3 non attiva (solo serializer interno)  
- Gemini live opzionale: CI verde con fallback  
