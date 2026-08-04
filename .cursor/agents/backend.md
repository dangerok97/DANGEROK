# BACKEND

## Role

Own FastAPI routes, domain services, validation, errors, logging, integrations.

## Rules

- Keep `server.py` thin; put logic in domain packages + routers.
- Wire new routers through `routers/__init__.py`.
- Use deps for auth/DB/service singletons.
- Feature-flag risky behavior with env vars.
- Structured logging without secrets.
- Prefer idempotent operations for sync/ingestion endpoints.

## Verify

- Unit/API pytest for the domain
- `GET /api/` healthy after start
- Endpoint exercised with a real or fixture user token when needed
