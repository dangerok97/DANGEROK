# Study Plan Generation

## Primary algorithm (deterministic)

Inputs: exam date, daily minutes, available weekdays, preferred time range, intensity, tools, document ids, topics.

1. Compute local days until exam (`Europe/Rome` default).
2. Filter calendar days matching `available_days`.
3. Choose session count by intensity:
   - light → fewer, spaced
   - distributed → ~every few days
   - intensive → pack toward exam
   - custom → mid density
4. Place sessions at preferred local start time; duration = `daily_minutes` (15–180).
5. Assign session types from tools (study / review / flashcards / interrogami / exam_questions).
6. Never schedule on/after exam day morning without shifting back.

Fails clearly when: no days, exam past/too soon, daily &lt; 15 min.

## Optional Gemini

If `EMERGENT_LLM_KEY` or `GEMINI_API_KEY` present, may split topics only.  
Absence never blocks plan creation (deterministic topics from subject / doc titles).

## Preview vs confirm

- Preview builds draft sessions in `study_plans` with status `awaiting_confirmation`.
- Confirm persists `study_sessions`, Life Graph events, reminder, tools, Brain links, optional Google sync.
- No side effects before confirm.
