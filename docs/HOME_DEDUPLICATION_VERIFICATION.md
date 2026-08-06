# Home Goal Deduplication — Verification

**Date:** 2026-08-06  
**Branch:** `feature/home-goal-presentation-dedupe`  
**Feature:** Presentation Aggregation Layer (`home-pres-1.0`)

## Pass criteria (ruthless)

Home **FAILS** if the same `goal_id` appears as more than one card across primary focus + priorities (resume for the same Goal also fails unless a truly distinct motivated action exists).

## Backend checklist

| # | Case | Expected |
|---|------|----------|
| 1 | Study Goal: plan + 4 sessions + 2 reviews + event + suggestion | **1** card |
| 2 | Travel: vacation + outbound + return + project | **1** card |
| 3 | Two distinct study Goals | **2** cards |
| 4 | Similar titles, different Goals | **not** merged |
| 5 | Artifact without `goal_id` | safe fallback, no invented merge |
| 6 | Primary Goal | not also in priorities |
| 7 | Resume | not duplicated for same Goal |
| 8 | Suggestion | incorporated into Goal card; not duplicate ORA TI CONSIGLIA |
| 9 | Conversation | action on Goal card, not new card |
| 10 | User isolation | user A never sees user B Goals |
| 11 | Refresh | still one card |
| 12 | Logout/login (Playwright) | still one card |
| 13 | Legacy data | audit/migrate attach; no deletes |

### Commands

```powershell
cd backend
python -m pytest tests/test_home_presentation_aggregation.py -q
python -m pytest tests/test_home_goal_aware.py -q
python scripts/audit_home_goal_links.py --report --out ../docs/home_goal_link_audit.json
```

## Playwright checklist

```powershell
cd frontend
npx playwright test e2e/home-presentation-dedupe.spec.ts
```

| Scenario | Assert |
|----------|--------|
| Psicologia multi-artifact | Exactly one surface card matching Psicologia; open card → details/actions reachable |
| Vacanza Vibo Marina | Exactly one surface card matching Vibo |
| Relogin | Aggregation still holds |

Evidence: `frontend/e2e-evidence/home-presentation-dedupe/`

## Manual spot-check

1. Seed / confirm a study plan for Psicologia with multiple sessions.  
2. `GET /api/home` → count items with that `goal_id` in `primary_focus` + `priorities[*].items` → must be **1**.  
3. Inspect `supporting_details` / `hidden_artifact_count` / `actions`.  
4. Repeat for travel to Vibo Marina.

## Known limits

- Aggregation requires attachable `goal_id` (or reconstructible persistent refs). Pure orphan calendar titles without refs stay ungrouped.  
- Title similarity alone never merges Goals.  
- Source data is not deleted by this feature.
