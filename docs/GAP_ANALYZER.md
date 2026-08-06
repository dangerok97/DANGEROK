# Gap Analyzer

Declares required / conditional / optional slots per flow schema. Outputs:

- `known_slots`
- `missing_required` / `missing_conditional` / `missing_optional`
- `ambiguous_slots`
- `next_best_question` + `next_slot` + `question_reason` + `suggested_chips`
- `completion_ready`

## Travel rules (product-critical)

| Required | Conditional | Optional |
|----------|-------------|---------|
| destination, departure_date | return_date, departure_place, transport, lodging, companions | budget, stops, preferences |

Special ordering:

1. Departure known, destination missing → **Dove andrai?** (never combo date question)
2. Destination + both dates + transport known → **lodging** first
3. Return template: «Perfetto, partirai il {date}. Quando pensi di rientrare?»

Action Engine must not use a static question sequence when these slots are already known.
