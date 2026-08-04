# FRONTEND

## Role

Own Expo UI: screens, components, accessibility, loading/empty/error states, visual consistency.

## Rules

- Follow `tokens.ts` and `design_guidelines.json`.
- Use `src/api/client.ts` for network I/O.
- expo-router file routes under `frontend/app/`.
- Touch target ≥ 44; Italian copy consistent with existing screens.
- Responsive / multi-platform: iOS, Android, web as applicable.
- No dead buttons; Apple auth remains explicitly “in arrivo” until implemented.

## Verify

- `yarn lint` (or npm)
- Manual navigation of the changed flow with backend running when required
