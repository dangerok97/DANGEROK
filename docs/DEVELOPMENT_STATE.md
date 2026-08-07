# ORA — Development State

Last updated: 2026-08-07 (ORA Quiet Premium Design System v1)

## Branch

- Active: `feature/ora-quiet-premium-design-system`
- Base: `feature/life-object-engine`
- No push / no merge unless requested

## ORA Quiet Premium Design System (this batch)

**Scope:** frontend design system only. Backend / ranking / Action / Conversation / Home logic **not** modified.

| Item | Stato |
|------|--------|
| Semantic color system (light + dark) | **implemented** |
| Accent Deep Indigo | **yes** (`#3D4A8C`) |
| Typography / spacing / radius / shadows / motion / haptics / icons | **implemented** |
| ThemeProvider (light / dark / system) | **wired** in `app/_layout.tsx` |
| Legacy token aliases (`brand`, `onSurface`, …) | **kept** — existing screens compile |
| UI primitives (`src/components/ui/*`) | **available**, not adopted everywhere |
| `design_guidelines.json` Quiet Premium | **updated** |
| Screen restyle (Home, Login, …) | **Prompt 2** — not this PR |

## Prior — Digital Twin / Life Object Engine (ancora valido)

| Item | Stato |
|------|--------|
| Life Object Engine + Knowledge Model | **implemented** (shadow) |
| `LIFE_OBJECT_HOME_UI_ENABLED=0` | **yes** — Home UX invariata lato prodotto |
| Facts never deleted | **yes** |

## Open / next

1. **Prompt 2** — adopt Quiet Premium primitives on Login / Home chrome / tab bar (no business logic)
2. Theme toggle in Profilo settings
3. Migrate StyleSheet.create screens from static `tokens` → `useTheme()` gradually
4. Home V3 UI — solo con flag=1 — **non fare ora**

## Credentials / safety

- Never commit `.env` / tokens
- CI green senza secret; Gemini gated / fallback
- No new UI libraries added
