from __future__ import annotations

from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

GENERIC_SCHEMA = FlowSlotSchema(
    flow="generic",
    description="Flusso generico",
    completion=["goal"],
    slots=[
        SlotDef(
            name="goal",
            kind="required",
            ui_label="Obiettivo",
            question_template="Cosa vuoi organizzare?",
            question_reason="Serve un obiettivo chiaro.",
        ),
        SlotDef(
            name="date",
            kind="optional",
            ui_label="Data",
            question_template="Hai una data di riferimento?",
        ),
    ],
)
