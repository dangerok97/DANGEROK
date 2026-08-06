# Life Object Architecture

## Framing

Life Objects = **modello canonico** della realtà utente.  
Gemini = **consultant**; backend = **autorità finale** su type, title, merge, fields.  
Goal / Documents / Brain / Conversation / Proactive / Home / Travel / Study restano satelliti R/W.

## Pipeline

```
Document → OCR → Document AI → Life Object AI → Semantic Validator → Canonical Object → (future Home)
```

Il Validator gira **sempre** prima del persist.

## Package

```
backend/life_objects/
  models.py               # LifeObject + Health 2.0 + provenance
  types.py                # type catalog + DOC_TYPE_TO_OBJECT
  repository.py           # Mongo life_objects
  deduplication.py        # strong keys + soft address
  identity_state.py       # identity vs state (+ registry map)
  property_registry.py    # canonical fields + aliases
  title_generator.py      # titoli deterministici
  semantic_validator.py   # autorità pre-persist
  assimilation.py         # mutuo/bolletta → HOME.state
  link_states.py          # 4 stati link/merge
  knowledge_gaps.py       # gap su concetti
  provenance.py           # fonti tipizzate
  reasoner.py             # Gemini consultant + fallback
  enrichment.py           # narrative/questions/insights/temporal/health 2.0
  linking.py / memory.py
  home_v3.py              # DTO PREDISPOSTO (flag OFF)
  service.py              # CRUD + shadow + validator
  shadow.py / router.py
  tests/
```

## Collection Mongo

`life_objects` — indexes su `id`, `(user_id, type, status)`, identity_keys sparse.

Campi v2: `identity`, `state`, `narrative`, `insights`, `temporal`, `health` (Health 2.0),  
`document_sources` / `conversation_sources` / `goal_sources` / `calendar_sources` / `brain_sources` / `manual_sources` / `total_sources`  
(`source_count` = alias di `total_sources`), `assimilated_kinds`, `last_validation`, `pending_links`, `merge_proposals` (solo REAL_CONFLICT user-facing).

## Assimilation

Quando identity è LINK_CONFIRMED / LINK_PROBABLE:

- **mutuo** → aggiorna `state` (lender, monthly_installment, loan_number…)  
- **bolletta** → aggiorna `state` (utility_supplier, utility_amount, POD…)  

L’oggetto cresce; **non** si accumulano merge_proposals per aggiornamenti chiari.

## Home V3 DTO

`life_object_id`, `life_domain`, `health`, `next_action`, `benefits`, `questions`, `insights`, `timeline`, `related_documents`, `related_goals`, `related_projects`.  
Flag `LIFE_OBJECT_HOME_UI_ENABLED=0` — UX Home invariata.

## API

Auth Bearer. Prefisso `/api/life-objects` — CRUD, enrich, narrative/questions/insights/health/history/relationships/temporal, `GET /home-v3-feed` (OFF).
