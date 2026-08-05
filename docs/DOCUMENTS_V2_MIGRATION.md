# Documents V2 — Migration (non-destructive)

Branch: `feature/rebuild-intelligent-documents`  
Base: `feature/google-calendar-sync` @ `213ea4f`

## Principle

Replace archival UX + extend intelligence pipeline. **Never** delete user files, Mongo documents, analyses, calendar drafts, or Brain links.

## Version fields (added, never wipe)

| Field | Meaning |
|-------|---------|
| `document_schema_version` | Document record shape (`2.0`) |
| `analysis_version` | Analysis payload shape |
| `processing_version` | Pipeline engine (`intel-docs-2.0`) |
| `legacy_data_preserved` | `true` if upgraded from pre-v2 |

## Preserved collections

- `documents` (all fields + binary via storage)
- `calendar_event_drafts`
- `life_nodes` / `life_edges`
- `node_knowledge`
- User prefs (`document_ai_analysis`, new calendar auto-add)

## Map of pre-rebuild module

See `docs/DOCUMENTS_V2_ARCHITECTURE.md` § “Legacy map”.

## Transform rules

1. On read/upload/analyze: stamp missing version fields.
2. Old `pipeline_status` values remain valid; new aliases map in UI.
3. `user_title` always wins over AI title.
4. Confirmed/dismissed event candidates preserved on reanalyze (existing merge).
