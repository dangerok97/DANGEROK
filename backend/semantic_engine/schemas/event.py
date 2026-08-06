from __future__ import annotations

from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

EVENT_SCHEMA = FlowSlotSchema(
    flow="event",
    description="Evento generico",
    completion=["title", "event_date"],
    slots=[
        SlotDef(
            name="title",
            kind="required",
            ui_label="Evento",
            question_template="Di che evento si tratta?",
            question_reason="Serve un titolo.",
        ),
        SlotDef(
            name="event_date",
            kind="required",
            ui_label="Data",
            question_template="Quando si svolge?",
            question_reason="Data evento.",
            aliases=["date"],
        ),
        SlotDef(
            name="event_time",
            kind="optional",
            ui_label="Ora",
            question_template="A che ora?",
            aliases=["time"],
        ),
        SlotDef(
            name="place",
            kind="optional",
            ui_label="Luogo",
            question_template="Dove?",
        ),
    ],
)
