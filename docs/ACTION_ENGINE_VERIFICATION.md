# Action Engine — Verification

Last updated: 2026-08-05

## Automated

```powershell
cd backend
python -m pytest tests/test_action_engine.py -q
python -m pytest tests/test_home_v2.py -q
python -m pytest tests/test_documents_v2.py -q
```

```powershell
cd frontend
npx tsc --noEmit
```

```powershell
python -m compileall backend/action_engine backend/home
```

## Manual (collaborative feel)

1. Start backend + Expo (`scripts/dev` or local uvicorn + `npx expo start`).
2. Home with a study / bill / event priority.
3. Tap **Inizia** / **Organizza** / **Apri** or the Adesso card.
4. Expect: conversational screen with **one question** and chips — not an empty page.
5. Answer chips until complete.
6. Expect completion summary with calendar/reminder actions.
7. Return to Home → pull to refresh → primary focus / priorities reflect sessions or next hint.
8. Medical item: confirm disclaimer text (no medical advice).

## Platforms not verified in this pass

- iOS / Android device builds  
- Playwright E2E (optional; not required for backend green)  
- Google Calendar live sync of Action Engine events (Life Graph events are written; Google write is separate)

## Known limits

- No dedicated Projects product domain — `action_projects` is the aggregator.
- Weather / live traffic blocked without credentials.
- Flashcard/quiz generation depends on document intelligence readiness.
"""