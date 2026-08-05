# Documents V2 — Verification

Branch: `feature/documents-v2-completion` (base `3ff825d`)

## Automated

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_documents_v2.py -q
```

**Result (2026-08-05):** **15 passed**

Coverage includes: pipeline states, migration stamp, auto-add off/0.89/multi/ambiguous, hub upload, fixtures concerto/visita/dispensa/admin/ambigua, flashcards+quiz, corrections survive reanalyze, search+isolation+delete, local parsing, provider-fail→local, HTTP auth gates.

```powershell
cd frontend
.\node_modules\.bin\tsc.cmd --noEmit
```

**Result:** OK (exit 0)

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall documents\intelligence -q
```

**Result:** OK

## Browser E2E (Expo web + Chromium)

Script: `backend/scripts/e2e_documents_v2_browser.py`  
Evidence: `backend/data/e2e_documents_v2_browser.json` + `.png`

| Step | Result |
|------|--------|
| Login email/password | **verified browser** |
| Documenti hub | **verified browser** |
| Search Bourdieu | **verified browser** |
| Dynamic study detail | **verified browser** |
| Genera flashcard / Interrogami / Spiegamelo | **verified browser** |
| Flashcards UI | **verified browser** |
| Quiz answer | **verified browser** |
| Ask document | **verified browser** |
| Event detail + panel | **verified browser** |
| Upload via file chooser | **verified browser** |
| Logout + re-login persistence | **verified browser** |
| Refresh after logout path | partial (`refresh_ok` false once; persistence via re-login OK) |

**cursor-ide-browser MCP:** unavailable/unstable in this session → Playwright Chromium used against Expo web `:8081`.

## Status matrix

| Area | Implemented | Verified API | Verified browser | Verified Google | Verified Gemini | Mobile |
|------|-------------|--------------|------------------|-----------------|-----------------|--------|
| Dynamic detail by macro | yes | yes | yes | — | — | **not verified** |
| Flashcards | yes | yes | yes | — | — | **not verified** |
| Interrogami quiz | yes | yes | yes | — | — | **not verified** |
| Admin actions + edit fields | yes | yes | partial (API+UI wired) | deadline path mocked/fake in tests | — | **not verified** |
| Auto-add gates | yes | yes | prefs UI prior | auto uses confirm+sync | — | **not verified** |
| Google Calendar confirm sync | yes (prior session) | yes | prior | **yes (prior real account)** | — | **not verified** |
| Maps links | yes | yes | event panel shown | — | — | **not verified** |
| Brain merge | yes | soft (no LG in unit svc) | — | — | — | **not verified** |
| Intelligent search | yes | yes | yes | — | — | **not verified** |
| User corrections provenance | yes | yes | UI save admin fields | — | — | **not verified** |
| Synthetic fixtures A–F | yes | yes | study+event | — | — | **not verified** |
| Gemini real smoke | optional | not run this session | — | — | **not this session** | — |

## Manual procedure (supervisor)

1. Start Mongo + `uvicorn` on `:8000` (restart after router changes).
2. Start Expo web on `:8081`.
3. Register/login email.
4. Upload `caso_b_concerto.txt` → confirm event ORA / ORA+Google; open Maps.
5. Upload `caso_d_dispensa.txt` → Utilità → Genera flashcard → Interrogami → answer → Chiedi.
6. Upload `caso_e_admin.txt` → edit oggetto/importo/scadenza → Salva correzioni → completa azione.
7. Upload `caso_f_ambigua.txt` → expect needs review / no auto-add.
8. Search: antropologia, Bourdieu, da verificare.
9. Toggle auto-add off/on; with confidence 0.89 ensure no auto.
10. Logout/login → documents still present.
11. Optional: connect Google Calendar and confirm one synthetic event.

## Limits

- Mobile native (iOS/Android) **not verified**.
- Gemini live enrichment **not re-run** in this completion session (local `force_local` path verified).
- Google live create **not re-run** here; relies on prior `feature/google-calendar-sync` verification.
- Brain Life Graph edges soft-fail when LG not wired in unit tests.
- Browser MCP Glass tab flaky; Playwright is the recorded browser evidence.
