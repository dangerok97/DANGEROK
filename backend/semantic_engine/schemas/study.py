from __future__ import annotations

from semantic_engine.models import QuestionChip
from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

STUDY_SCHEMA = FlowSlotSchema(
    flow="study",
    description="Preparazione esame / studio",
    completion=["subject", "exam_date"],
    slots=[
        SlotDef(
            name="subject",
            kind="required",
            ui_label="Materia",
            question_template="Quale esame vuoi preparare?",
            question_reason="Serve la materia.",
            aliases=["exam", "confirm_subject"],
        ),
        SlotDef(
            name="exam_date",
            kind="required",
            ui_label="Data esame",
            question_template="Quando è l'esame di {subject}?",
            question_reason="Data esame per il piano.",
            aliases=["date", "deadline"],
            chips=[
                QuestionChip(id="in_2_weeks", label="Tra 2 settimane", value="in_2_weeks"),
                QuestionChip(id="in_1_month", label="Tra 1 mese", value="in_1_month"),
            ],
        ),
        SlotDef(
            name="materials",
            kind="conditional",
            ui_label="Materiali",
            question_template="Hai già documenti o appunti per {subject}?",
            question_reason="Materia e data note — chiedi i materiali, non ripetere subject/date.",
            aliases=["select_materials", "documents"],
            when="core_study_known",
            chips=[
                QuestionChip(id="yes_docs", label="Sì, ho documenti", value="yes_docs"),
                QuestionChip(id="no_docs", label="Non ancora", value="no_docs"),
            ],
        ),
        SlotDef(
            name="daily_time",
            kind="optional",
            ui_label="Tempo giornaliero",
            question_template="Quanto tempo al giorno puoi dedicare?",
            question_reason="Opzionale per intensità piano.",
        ),
        SlotDef(
            name="intensity",
            kind="optional",
            ui_label="Intensità",
            question_template="Che ritmo preferisci?",
            question_reason="Opzionale.",
        ),
    ],
)
