# DATABASE

## Role

Own MongoDB collections, indexes, relationships, integrity, rollback thinking.

## Rules

- Additive changes first.
- Register indexes in startup or `ensure_ready()`.
- Preserve unique constraints on `id` / `user_id` compounds.
- Never drop data without consent.
- Document new collections/fields in ARCHITECTURE.md and DEVELOPMENT_STATE.md.

## Verify

- Startup completes without index errors
- Queries used by the feature remain indexed
- Rollback/forward notes written when schema changes
