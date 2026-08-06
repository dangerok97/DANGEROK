from __future__ import annotations

from semantic_engine.models import QuestionChip
from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

MEDICAL_SCHEMA = FlowSlotSchema(
    flow="medical",
    description="Visita medica / dentista",
    completion=["appointment_type", "appointment_date"],
    slots=[
        SlotDef(
            name="appointment_type",
            kind="required",
            ui_label="Tipo visita",
            question_template="Che tipo di visita è?",
            question_reason="Serve il tipo di appuntamento.",
            aliases=["visit_type", "specialty"],
        ),
        SlotDef(
            name="appointment_date",
            kind="required",
            ui_label="Data",
            question_template="Quando è l'appuntamento?",
            question_reason="Data visita.",
            aliases=["date"],
        ),
        SlotDef(
            name="appointment_time",
            kind="conditional",
            ui_label="Ora",
            question_template="A che ora?",
            question_reason="Ora mancante.",
            aliases=["time"],
            when="date_known_time_missing",
        ),
        SlotDef(
            name="calendar_sync",
            kind="conditional",
            ui_label="Calendario",
            question_template="Vuoi aggiungerlo al calendario?",
            question_reason="Appuntamento noto — proponi sync calendario.",
            when="core_medical_known",
            chips=[
                QuestionChip(id="yes", label="Sì, in calendario", value=True),
                QuestionChip(id="no", label="No grazie", value=False),
            ],
        ),
        SlotDef(
            name="provider",
            kind="optional",
            ui_label="Medico",
            question_template="Da chi hai l'appuntamento?",
            question_reason="Opzionale.",
            aliases=["person", "doctor"],
        ),
        SlotDef(
            name="place",
            kind="optional",
            ui_label="Luogo",
            question_template="Dove si svolge la visita?",
            question_reason="Opzionale.",
        ),
    ],
)
