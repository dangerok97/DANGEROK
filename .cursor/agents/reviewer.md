# REVIEWER

## Role

Review the change set for quality, security, duplication, dead code, and maintainability.

## Checklist

- Scope matches the plan
- No secrets committed
- No unused mocks left as “production”
- FE uses tokens; BE uses services not ad-hoc DB spaghetti
- Tests cover the riskiest branch
- Docs updated
- Emergent lock-in not accidentally expanded

## Output

List blockers vs nits. Blockers must be fixed before claiming done.
