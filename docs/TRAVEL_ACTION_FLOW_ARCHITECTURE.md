# Travel Action Flow — Architecture

Last updated: 2026-08-05

## Role

First real **Life Planner** slice: conversational assistant that builds a living **Travel Project** (not a checklist or task manager). Reuses Intent Classification Engine (`travel` / `vacation`) and Action Engine patterns from Study.

## Package layout

```
backend/action_engine/travel/
  models.py           TravelProject, calendar events, maps, prep
  period_parser.py    Italian periods («dal 9 al 24 agosto»)
  flow.py             Turns + normalize + preview explanation
  maps.py             Google Maps deep links + Nominatim/haversine (optional)
  documents.py        Soft search hotel/ticket PDFs in Documents V2
  prep.py             Optional prep suggestions
  google_sync.py      calendar_google create after confirm only
  brain_links.py      trip ↔ destination ↔ docs ↔ people
  project_service.py  draft → preview → confirm
flows/travel.py       Thin registry delegate
```

## Flow steps (ask only missing)

1. `period` — skipped if Intent extracted dates  
2. `destination` — skipped if known  
3. `departure_place` — Brain/home confirm (e.g. Tarquinia)  
4. `transport` · `bookings` · `companions`  
5. `calendar_sync` — propose Google events (create only on confirm)  
6. `prep` — optional multi / skip  
7. `preview` · `confirm`

## Confirm gate

- `complete` / silent API cannot create Google events  
- Google sync uses connector id **`calendar_google`** (same fix as study)  
- Proposes: vacation block (all-day) + outbound + return  

## Home

- Adapter `home/adapters/travel.py` → phases: upcoming → days_until → departure_day → during → welcome_back  
- Catalog: open `/travel-project/{id}`, Maps deep link  

## API

- Action Engine: open/answer/preview/confirm (shared)  
- `GET/DELETE /api/travel-projects`, `POST .../retry-sync`  

## Frontend

- Shared conversational UI `app/action/[sessionId].tsx` (travel preview panel)  
- Detail `app/travel-project/[id].tsx`  

## Honesty

| Capability | Status |
|------------|--------|
| Weather | unavailable without API — never invented |
| Email auto-find | stub hook `not_implemented` |
| Traffic | not used; departure advice is heuristic |
| Pedaggi/soste | labeled heuristic suggestions |
| Photos / expenses | empty lists on model for future |
| Native mobile | not verified |
