# Intent Classification Engine — Product

Last updated: 2026-08-05

## Why

ORA must choose the **right guided flow** from a free-text priority (Home, Parla, Documents, …) without guessing from wrong source labels like EVENT/GENERIC.

Bug fixed: *“devo studiare l'esame di psicologia”* opened the event flow (“Hai già il biglietto?”). Root cause: flow selection trusted home item type instead of meaning.

## User-facing rule

```
Home → Priority → Intent Classification → Intent → Action Engine → Flow
```

- High confidence → open the correct flow immediately.
- Low confidence → ask: *“Non sono sicuro. Vuoi preparare un esame oppure creare un evento?”* — never open the wrong flow.
- Action Engine never parses free text for routing; it only consumes an **Intent** object.

## Recognized intents (v1)

study (+ subtype `exam_preparation`), travel (+ `vacation`), event, medical, payment, financial, administrative, document_review, task, communication, shopping, project, generic.

## Psychology exam example

| Input | Intent | Flow first question |
|-------|--------|---------------------|
| devo studiare l'esame di psicologia | study / exam_preparation, subject=Psicologia | Quando è l'esame «Psicologia»? |

Never: “Hai già il biglietto?”.

## Future consumers

Same Intent brain is designed for Home, Parla, Documents, Notifications, Email, WhatsApp, Open Banking, Projects, Brain.
