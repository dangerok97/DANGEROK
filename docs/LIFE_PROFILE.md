# Life Profile

Ultimo aggiornamento: 2026-08-06

## Modello

Un Life Profile per utente, suddiviso per **dominio** (`casa`, `auto`, `finanze`, `studio`, `lavoro`, `salute`, `famiglia`, `animali`, `viaggi`, `documenti`, `assicurazioni`, `abbonamenti`, `internet`, `servizi`).

Per ogni dominio:

- `objects` — fatti con `confidence`, `source`, `updated_at`, `confirmed`, `linked_doc_ids`  
- `benefits_available` / `benefits_active`  
- `missing_info`  
- `linked_docs`  
- `goal_id` / `life_node_id` (sync)

Collection Mongo: `life_profiles` (unique `user_id`).

## Fonti

`user_said` | `user_confirmed` | `document_extract` | `semantic_extract` | `inferred` | `system`

Fatti **confermati** non vengono sovrascritti da inferenze AI/sistema. Solo l’utente può correggere/cancellare (API dedicate).

## Sync

- Life Graph node per dominio  
- Shadow Goal (idea) per domini rilevanti (es. Casa)  
- Knowledge link best-effort  
- Proactive/Home usano il profilo indirettamente via suggestion generator

## Non è

Una pagina Impostazioni «Life Setup». Il profilo è conoscenza interna; la UI espone conversazione e (futuro) correction paths, non un form permanente di setup.
