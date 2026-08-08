# ORA — Development State

Last updated: 2026-08-08 (Sprint 3 — Minimum Life Context V1)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- No push / no merge unless requested

## Sprint 3 — Minimum Life Context V1 (this batch)

| Item | Stato |
|------|--------|
| `minimum_life_context.py` coverage model | **yes** |
| `plan_next` wrap only when MLC sufficient | **yes** |
| Multi-nucleus infer from natural language | **yes** |
| Persist coverage via `known_facts` + `meta.mlc_coverage` | **yes** |
| Documents not required for done | **yes** |
| Gate Sprint 2B / Home untouched | **yes** |
| Backend tests MLC + strategist | **38 passed** |
| Commit | **pending review** |

## Sprint 2B — Life Setup Conversation behind Gate

| Item | Stato |
|------|--------|
| `/life-setup` mounts `LifeSetupConversationScreen` | **yes** |
| Raw `/(tabs)` bypasses removed from conversation | **yes** |
| Complete → `lifeSetupComplete` then `completeLifeSetupGate` | **yes** |
| Exit / Più tardi do not open Home | **yes** |
| Gate unlocks Home only on `session.status === completed` | **yes** |
| Tabs guard kept (2nd defense) | **yes** |
| Home / Documents pipeline untouched | **yes** |
| Commit | **pending review** |

### Resume limits (documented)

- Active session: cold start resumes via `lifeSetupStart(false)`.
- After Esci (`lifeSetupCancel`): session terminal → in-place `start(force=true)` (new turn, not mid-thread restore).
- “Più tardi” no longer calls `postpone_all` (that marked `skipped` and unlocked Home under old `should_show` semantics).

## Sprint 1 — Life Setup Gate

| Item | Stato |
|------|--------|
| Persistent `ora.lifeSetupCompleted.<userId>` | **yes** |
| Gate module `src/life-setup/gate.ts` | **yes** |
| Placeholder Completa Setup | **rollback only** (not normal path) |
| Home unaware / unchanged | **yes** |

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
