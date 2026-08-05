# Travel Action Flow — Verification

Last updated: 2026-08-05

## Backend pytest

```text
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_travel_action_flow.py tests/test_action_engine.py::test_travel_flow -q
```

**Result: 12 passed** (feature commit `ed332c2`)

## Playwright (browser E2E)

```text
# Backend with travel routes (this branch). Used :8001 when :8000 held a stale process.
# Expo web on :8081 with EXPO_PUBLIC_BACKEND_URL pointing at that backend.
cd frontend
$env:E2E_API_URL="http://127.0.0.1:8001"
$env:EXPO_PUBLIC_BACKEND_URL="http://127.0.0.1:8001"
$env:E2E_BASE_URL="http://127.0.0.1:8081"
npx playwright test e2e/travel-action-flow.spec.ts
```

**Result (2026-08-05): PASS (1/1, ~29–45s)**

Evidence (outside Playwright wipe dir):

- `frontend/e2e-evidence/travel-action-flow/run-log.json`
- Screenshots: `00-home.png` … `10-turn.png`, `99-complete.png`, `100-travel-project.png`

## Google Calendar live sync

```text
cd backend
.\.venv\Scripts\python.exe scripts\verify_travel_google_sync.py
```

**Result (2026-08-05): PASS**

| Field | Value |
|-------|--------|
| Connector | `calendar_google` + vault |
| Calendar | `francesconicolocefala@gmail.com` (primary) |
| Travel project | `trp_909806018a814b` |
| vacation_block | `pak7nvaer40p9v6b9cji5hl8o4` → cancelled |
| outbound | `7gj9vqeu21lb74qp2ekn0s0h2g` → cancelled |
| return | `f0m3kb7sahnkk19e54ctblltr8` → cancelled |
| Duplicates | unique ids (no dupes) |
| Cleanup | `delete_project(cleanup_google=True)` deleted 3; GET status `cancelled` |

Report: `frontend/e2e-evidence/travel-action-flow/google-verify-report.json`

### Fix during verify

Positional Mongo `$` updates did not persist `google_event_id` on `calendar_events`; sync now writes the full events array, and delete falls back to `google_sync.synced` ids. Confirm re-reads `calendar_sync` from answers.

## Honest gaps remaining

| Item | Status |
|------|--------|
| Weather API | not implemented |
| Email auto-find | stub only |
| Native iOS/Android | not verified |
| Nominatim distance in E2E | skipped (`skip_maps_network`) |
| Stale uvicorn on :8000 | may lack travel routes — prefer clean process / :8001 |
