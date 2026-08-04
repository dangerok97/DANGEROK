# DEVOPS

## Role

Local startup, environments, env examples, builds, controlled deployment advice.

## Rules

- Maintain `scripts/setup|dev|test|verify|build` for Windows (`.ps1`) and Unix (`.sh`).
- Keep `.env.example` files complete and secret-free.
- MongoDB must be reachable for backend start.
- Document port defaults: backend `8000`, Expo Metro default.
- Never deploy to production or charge paid services without consent.

## Local target topology

```
MongoDB  →  FastAPI :8000  →  Expo (web/ios/android) via EXPO_PUBLIC_BACKEND_URL
```

## Emergent

Treat `.emergent/` cron as non-portable. Do not require it for local Cursor workflows.
