# Travel Action Flow — Verification

Last updated: 2026-08-05

## Backend pytest

```text
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_travel_action_flow.py tests/test_action_engine.py::test_travel_flow -q
```

**Result (2026-08-05): 12 passed**

Coverage includes: period parse, intent vacation+period, missing-only questions, destination/departure, transport/bookings/companions, project create, calendar propose + Google absent, Maps links, Home phase, Brain links, resume/draft, isolation, confirm gate (no silent calendar create).

## Playwright

```text
cd frontend
npx playwright test e2e/travel-action-flow.spec.ts
```

Requires local backend + Expo web. Evidence dir: `frontend/test-results/travel-action-flow/`.

**Status:** authored; run when servers up (see CHANGELOG for result).

## Google Calendar (optional live)

When connector `calendar_google` is connected for a test user:

1. Run travel flow with calendar sync = yes → confirm  
2. Expect Google event ids on vacation_block and/or outbound/return  
3. Cleanup: `DELETE /api/travel-projects/{id}?cleanup_google=true`  

**Live create for francesconicolocefala@gmail.com:** run manually when connected — not claimed in this commit unless evidence recorded.

## Honest gaps

| Item | Verified? |
|------|-----------|
| Weather | No — skipped honestly |
| Email auto-find | No — stub only |
| Native iOS/Android | No |
| Nominatim distance | Soft; tests use `skip_maps_network` |
| Google live travel sync | Pending optional manual |
