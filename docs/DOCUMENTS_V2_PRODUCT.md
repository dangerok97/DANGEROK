# Documents V2 — Product

ORA Documents turns personal files into ranked, resolvable outcomes — never a generic drive.

## User promise

1. Upload anything useful (PDF, image, Office, text).
2. ORA reads and classifies it.
3. You see a smart title, category, and **what you can do next**.
4. Events go to calendar (confirm or optional auto-add).
5. Study docs get explanations, flashcards, Interrogami quiz, and grounded Q&A.
6. Admin docs surface deadlines, amounts, actions, reminders, editable fields.
7. Everything stays linked to the original file and the Brain.

## Home

Upload · recent · needs review · events · study · deadlines/actions · search · smart filters.

## Detail (dynamic by macro)

| Macro | What changes |
|-------|----------------|
| EVENT / travel | Title, datetime, venue, maps, confirm ORA / ORA+Google, remind later |
| STUDIO / education | Subject, concepts, summaries, outline, flashcards, Interrogami, ask document |
| ADMIN / financial | Sender, amount, due date, required actions, complete, deadline calendar, disclaimer |
| MEDICAL | Appointment fields only — **no** generated diagnoses/therapies/clinical interpretation |
| GENERIC | Classification, summary, keywords, resolved fields |

Empty sections are hidden. Original file always under Originale / File.

## Study tools (grounded on document text)

- Spiegamelo semplice, riassunto breve/dettagliato, schema
- Domande ripasso / esame
- Flashcard (`question`, `answer`, `source_ref`, `difficulty`, `review_status`)
- Interrogami: ask → user answers → evaluate vs document → explain gaps → next (no arbitrary grades)
- Chiedi al documento (grounded)

## Admin

Deadlines, amounts, required actions, reminders, calendar deadline, completed status, simple explanation, editable extracted fields. Disclaimer: not professional advice.

## Auto-add calendar

- Default **off** (safe mode: draft → confirm → ORA / ORA+Google)
- Auto only when: enabled + confidence **>** threshold (default 0.90) + clear datetime + single event + no critical missing + not ambiguous
- 0.89 never auto-adds; multi-event / ambiguous blocked; duplicate drafts prevented
