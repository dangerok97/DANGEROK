from __future__ import annotations

from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

DOCUMENT_REVIEW_SCHEMA = FlowSlotSchema(
    flow="document_review",
    description="Revisione documento",
    completion=["document"],
    slots=[
        SlotDef(
            name="document",
            kind="required",
            ui_label="Documento",
            question_template="Quale documento vuoi rivedere?",
            question_reason="Serve il documento.",
        ),
        SlotDef(
            name="focus",
            kind="optional",
            ui_label="Focus",
            question_template="Cosa ti interessa nel documento?",
        ),
    ],
)
