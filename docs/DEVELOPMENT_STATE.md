# ORA — Development State

Last updated: 2026-08-08 (ORA Home Quiet Premium Polish 2.1)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- No push / no merge unless requested

## ORA Home Quiet Premium Polish 2.1 (this batch)

**Scope:** Home UI polish only — no new features, no backend/engines.

| Item | Stato |
|------|--------|
| Daily Focus less “card”, felt Focus Glow | **yes** |
| CTA hierarchy (filled / outline / ghost) | **yes** (`FocusActions`) |
| Perché adesso editorial (not a second card) | **yes** |
| Ask Bar Apple-Search calm | **yes** |
| Header + Horizon rewrite | **yes** |
| Quieter priorities / borders / motion | **yes** |
| Desktop column ~860 | **yes** |
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
