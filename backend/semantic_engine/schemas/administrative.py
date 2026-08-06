from __future__ import annotations

from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

ADMINISTRATIVE_SCHEMA = FlowSlotSchema(
    flow="administrative",
    description="Pratiche amministrative",
    completion=["task_type"],
    slots=[
        SlotDef(
            name="task_type",
            kind="required",
            ui_label="Pratica",
            question_template="Di che pratica si tratta?",
            question_reason="Serve il tipo di pratica.",
        ),
        SlotDef(
            name="deadline",
            kind="optional",
            ui_label="Scadenza",
            question_template="Entro quando?",
            aliases=["date", "due_date"],
        ),
        SlotDef(
            name="document",
            kind="optional",
            ui_label="Documento",
            question_template="Hai già un documento collegato?",
        ),
        SlotDef(
            name="office",
            kind="optional",
            ui_label="Ente",
            question_template="Presso quale ente?",
        ),
    ],
)
