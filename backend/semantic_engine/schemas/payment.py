from __future__ import annotations

from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

PAYMENT_SCHEMA = FlowSlotSchema(
    flow="payment",
    description="Pagamenti / bollette",
    completion=["payee", "amount", "due_date"],
    slots=[
        SlotDef(
            name="payee",
            kind="required",
            ui_label="Beneficiario",
            question_template="A chi devi pagare?",
            question_reason="Serve il beneficiario.",
            aliases=["vendor", "provider"],
        ),
        SlotDef(
            name="amount",
            kind="required",
            ui_label="Importo",
            question_template="Qual è l'importo?",
            question_reason="Serve l'importo.",
        ),
        SlotDef(
            name="due_date",
            kind="required",
            ui_label="Scadenza",
            question_template="Entro quando va pagato?",
            question_reason="Scadenza utile per priorità.",
            aliases=["deadline", "date"],
        ),
        SlotDef(
            name="payment_method",
            kind="optional",
            ui_label="Metodo",
            question_template="Come vuoi pagare?",
            question_reason="Opzionale.",
        ),
    ],
)
