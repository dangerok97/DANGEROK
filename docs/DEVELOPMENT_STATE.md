# ORA — Development State

Last updated: 2026-08-08 (Sprint 1 — Life Setup Gate)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- No push / no merge unless requested

## Sprint 1 — Life Setup Gate (this batch)

| Item | Stato |
|------|--------|
| Persistent `ora.lifeSetupCompleted.<userId>` | **yes** |
| Gate module `src/life-setup/gate.ts` | **yes** |
| Placeholder Completa Setup | **yes** (`/life-setup`) |
| Home unaware / unchanged | **yes** |
| Conversation Life Experience preserved (unmounted) | **yes** |
| Commit | **pending review** |

## Prior — Home Quiet Premium V1 — technical consolidation (2.2)

**Scope:** code quality only — **no intentional visual change**. Preparing Frozen V1.

| Item | Stato |
|------|--------|
| `getFocusGlow(scheme)` in theme | **yes** |
| CTA busy disables sibling actions | **yes** |
| Nav+action dual-step documented (intentional) | **yes** |
| Redundant surface ternaries removed | **yes** |
| `focusPresentation` helpers | **yes** |
| Visual design (polish 2.1) | **frozen intent** |

## Prior — Home Quiet Premium Polish 2.1

| Item | Stato |
|------|--------|
| Daily Focus / CTA hierarchy / Horizon / Ask Bar | **yes** |
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
