# ORA — Development State

Last updated: 2026-08-07 (ORA Home Quiet Premium V1)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- No push / no merge unless requested

## ORA Home Quiet Premium V1 (this batch)

**Scope:** Home presentation/UX only. Backend, ranking, engines, APIs **unchanged**.

| Item | Stato |
|------|--------|
| AppScreen + useTheme on Home | **yes** |
| Daily Focus + Focus Glow | **yes** |
| OraInput (Ask Bar → Conversation Engine) | **yes** |
| Focus Horizon (real temporal fields only) | **yes** (hidden if empty) |
| Light PrioritySection | **yes** |
| Unified Aggiornamenti | **yes** |
| Situation / Continua / Google notice | **yes** (light) |
| testIDs e2e preserved | **yes** |
| Home V3 Life Objects UI | **still OFF** |

## Prior — Design System + Life Objects

| Item | Stato |
|------|--------|
| Quiet Premium tokens / ThemeProvider / primitives | **implemented** |
| Life Object Engine + Knowledge Model | **implemented** (shadow) |
| `LIFE_OBJECT_HOME_UI_ENABLED=0` | **yes** |

## Open / next

1. **Prompt 3** — tab bar glass + Login Quiet Premium (no Home logic)
2. Theme toggle in Profilo
3. Playwright Home full stack when API+Expo up
4. Home V3 UI — solo con flag=1

## Credentials / safety

- Never commit `.env` / tokens
- No new UI libraries
- No backend changes in this batch
