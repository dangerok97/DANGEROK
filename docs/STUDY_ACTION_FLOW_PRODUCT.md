# Study Action Flow — Product

ORA turns a study / exam-preparation priority into a confirmed study plan with sessions, materials, and real tools — never a chatbot.

## User journey

1. Home shows a study priority (e.g. «Preparazione esame di Psicologia»).
2. User taps Inizia / Organizza / Apri → Action Engine opens.
3. One question at a time; known Intent fields (subject) are skipped.
4. User sets exam date, materials, daily time, days, time range, intensity, tools, calendar preference.
5. Preview of the plan (editable).
6. Confirm → real plan + sessions created (not before).
7. Home shows the active plan (countdown, next session, flashcards / Interrogami when available).
8. Plan screen: start / complete / snooze sessions, pause, regenerate future, delete.

## Plan states

`draft` → `awaiting_confirmation` → `active` | `paused` | `completed` | `cancelled`

## Intensity

`light` | `distributed` | `intensive` | `custom`

## Tools (real only)

- Study sessions
- Review
- Flashcards (link existing or generate on confirm from selected docs)
- Interrogami (same)
- Exam questions (via Interrogami path when selected)

No fake tools.

## Resume

Draft answers persist on close / refresh / logout. Home shows «Continua piano» for drafts. Active Action Engine sessions resume by home item.

## Duplicate plans

Same user + priority + exam name + exam date → Apri / Aggiorna / Unisci / Sostituisci / Crea comunque.
