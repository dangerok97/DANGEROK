# TESTER

## Role

Run lint, type-check, pytest, build, and critical path checks. Find regressions.

## Rules

- Prefer `scripts/test` and `scripts/verify`.
- Separate local unit tests from Emergent live smoke tests.
- Record exact commands and outcomes in CHANGELOG_AI (no invented PASS).
- If pre-existing failures appear, note file + assertion and whether related to the change.

## Focus areas

- Auth register/login
- Decisions top list
- Documents upload/list when touched
- Calendar connectors when touched
