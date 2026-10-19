# Deployment-only preview for ORA Wardrobe PR #351

This branch is forked from `feat/ora-wardrobe-foundation-v1`, not deployed to
the normal production environment. It only adds a minimal Dockerfile and
isolated authentication gateway for the public pilot.

**Data & security**
- New Railway project `ORA Guardaroba 351 Pilot` + dedicated MongoDB instance;
  never point `MONGO_URL` at the existing ORA database.
- Credentials (`JWT_SECRET`, `TOKEN_VAULT_KEY`, `PILOT_BASIC_AUTH_PASSWORD`,
  `PILOT_COOKIE_TOKEN`) are Railway runtime variables, not source-controlled.
- The pilot web service builds the app with `EXPO_PUBLIC_BACKEND_URL=same-origin`.
- The pilot backend runs on private DNS `pilot-backend-351.railway.internal:8080`.
  Only web has a public domain. Nginx protects the SPA and `/api/` using a
  temporary HttpOnly cookie issued at `/pilot-unlock`.
- No production OAuth, Gmail, Calendar, WhatsApp or payment credentials copied.
- Use a disposable preview account, and no sensitive photos or personal data.
- No AI API key is installed by default, so manual wardrobe and rule-based outfit
  suggestions work, but AI photo tagging shows an explicit unavailable state.

**Review**: preview branch should not be merged into `staging/cloud`.
Production deployment stays pinned to its existing branch.
