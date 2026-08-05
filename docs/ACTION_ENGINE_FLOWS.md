# Action Engine — Flows

Last updated: 2026-08-05 (Study Action Flow)

## Study

Stable step ids (one question at a time; skip known subject from Intent):

1. `confirm_subject` (skip if Intent subject known)
2. `exam_date` (+ `exam_date_confirm` if ambiguous)
3. Auto Documents V2 search → `select_materials` (upload resume supported)
4. `daily_time`
5. `available_days` (multi)
6. `preferred_time_ranges`
7. `intensity` (light / distributed / intensive / custom)
8. `tools` (study / review / flashcards / interrogami / exam_questions — real only)
9. `calendar_sync`
10. `duplicate_resolution` (if similar plan)
11. `preview` (editable)
12. `confirm` → creates `study_plans` + `study_sessions`

**Effects (only after confirm):** study sessions, Life Graph events, review reminder, flashcards/Interrogami on selected docs, Brain links, optional Google sync, Home plan card.

See `docs/STUDY_ACTION_FLOW_*.md`.

## Event

1. Ticket?  
2. Add to calendar?  
3. Location kind (if missing)  
4. Need route / Maps?  
5. Reminder offset  
6. Leave-time buffer  

## Travel

Asks only missing pieces: destination, transport, bookings, people, prep focus.  
Weather proposal is **blocked** until a weather integration exists.

## Medical

Logistics only. Disclaimer on first turn and UI.  
Calendar, Maps, document checklist reminder, visit reminder.  
Never diagnoses or treatment suggestions.

## Admin

Understanding → payment status → reminder → calendar → keep document.

## Generic

Intent → when → support (checklist / reminder / mini-project).  
Always produces at least one real next step.
