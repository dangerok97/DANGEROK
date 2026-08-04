# ORA — Agent Operating Manual

Cursor is the primary development environment for **ORA** (Life Operating System).
Act as an autonomous product engineer: implement, run, verify, document. Do not stop at suggestions.

## Product in one line

ORA removes cognitive load by turning personal information streams into ranked, resolvable actions. Never a chatbot. Never a generic task manager.

## Stack (do not replace without strong technical reason)

| Layer | Technology |
|-------|------------|
| Frontend | Expo 54 + React Native + TypeScript + expo-router |
| Backend | FastAPI + Uvicorn |
| Database | MongoDB (Motor async) |
| Auth | JWT + bcrypt email/password; Google OAuth (currently Emergent-bridged) |
| AI | LLM via `emergentintegrations` / `EMERGENT_LLM_KEY` (migration path documented in DEVELOPMENT_STATE) |
| Design | Dark-first, Apple HIG, monochrome — `design_guidelines.json` + `frontend/src/theme/tokens.ts` |

## Repository layout

```
backend/          FastAPI app (server.py thin entry; routers/; domain packages)
frontend/         Expo app (app/ routes; src/ components, api, theme)
docs/             Product & engineering docs (keep updated)
scripts/          setup / dev / test / verify / build
memory/PRD.md     Historical product iterations
.emergent/        Legacy Emergent runtime (do not depend on for local Cursor work)
.cursor/          Rules, agents, hooks for autonomous Cursor work
```

## Mandatory workflow (every user request)

1. Interpret the request in product terms.
2. Analyze the involved code and architecture.
3. Check whether a similar feature already exists.
4. Write a short plan and list risks.
5. Implement the smallest robust change that fits the architecture.
6. Install dependencies only when needed.
7. Update `.env.example` if new configuration is required.
8. Update Mongo indexes / migrations when schema changes (non-destructive by default).
9. Run lint, type-check (where available), tests, and build.
10. Start the app (or relevant servers) and verify the feature.
11. Read errors, fix them, re-run checks.
12. Update `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STATE.md`, `docs/CHANGELOG_AI.md`.
13. Return the standard final summary (see below).

A feature is **done** only when: code compiles, build succeeds, no blocking errors, main tests pass, the flow was verified, and docs are updated.

## Autonomy rules (Emergent-like)

- Infer reasonable technical details; prefer simple, robust solutions.
- Stay consistent with existing modules, naming, and UI tokens.
- Do not invent mock data when real data paths exist.
- Do not ship dead buttons or fake “working” integrations.
- Placeholders are allowed only for missing real credentials — declare them clearly.
- When credentials are missing: implement structure, update `.env.example`, document where to get values, never commit secrets.
- When an error appears: read it, fix root cause, re-run until resolved or blocked by external info.

## Consent required (stop and ask)

- Destructive DB operations / wiping data
- Production deploys, DNS, domain, paid services
- Sending real email / real push notifications to users
- Rotating keys, force-push, merge to main/master without approval
- Deleting large parts of the project
- Using real end-user personal data outside local/dev fixtures

## Allowed without asking

- Read/create/edit files, install deps, lint, type-check, test, build
- Start local servers, fix errors, non-destructive index/schema updates
- Update documentation, create local branches and local commits

## Git

- Before major work: `git status`; do not clobber uncommitted user changes.
- Prefer descriptive branches (`ora/...` or `feat/...`).
- Small readable commits. No push / force-push / history rewrite without consent.

## Security

Never commit passwords, tokens, API keys, secrets, or real personal data.
Validate inputs, protect endpoints, avoid leaking secrets in logs or summaries.

## Design

Before new UI: reuse `tokens.ts` and `design_guidelines.json`.
No new UI libraries if the current system suffices.
Every new screen needs desktop/tablet/mobile (or RN responsive), loading, empty, error, and clear feedback.

## Specialized agents

See `.cursor/agents/` for ARCHITECT, FRONTEND, BACKEND, DATABASE, TESTER, REVIEWER, DEVOPS instructions.
Use them as role playbooks when scoping work.

## Final summary template

1. What was done  
2. Files changed  
3. Dependencies installed  
4. Database changes  
5. Tests run  
6. Build result  
7. How to verify  
8. Missing credentials / config  
9. Open issues  
10. Suggested next step  

Use simple language. The human supervises; the agent executes.
