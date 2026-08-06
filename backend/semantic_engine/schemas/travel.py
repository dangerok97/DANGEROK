"""Travel slot schema — never ask both dates when departure is known."""
from __future__ import annotations

from semantic_engine.models import QuestionChip
from semantic_engine.schemas.base import FlowSlotSchema, SlotDef

TRAVEL_SCHEMA = FlowSlotSchema(
    flow="travel",
    description="Vacanza / viaggio — destinazione, partenza, ritorno, alloggio…",
    completion=["destination", "departure_date"],
    slots=[
        SlotDef(
            name="destination",
            kind="required",
            ui_label="Destinazione",
            question_template="Dove andrai?",
            question_reason="Serve la destinazione per organizzare il viaggio.",
            aliases=["travel", "place", "location"],
            chips=[
                QuestionChip(id="vibo", label="Vibo Marina", value="Vibo Marina"),
                QuestionChip(id="roma", label="Roma", value="Roma"),
                QuestionChip(id="milano", label="Milano", value="Milano"),
            ],
        ),
        SlotDef(
            name="departure_date",
            kind="required",
            ui_label="Partenza",
            question_template="Quando parti?",
            question_reason="Serve la data di partenza.",
            aliases=["start_date", "period_start"],
            chips=[
                QuestionChip(id="this_weekend", label="Questo weekend", value="this_weekend"),
                QuestionChip(id="in_2_weeks", label="Tra 2 settimane", value="in_2_weeks"),
            ],
        ),
        SlotDef(
            name="return_date",
            kind="conditional",
            ui_label="Ritorno",
            question_template="Perfetto, partirai il {departure_date_label}. Quando pensi di rientrare?",
            question_reason="La partenza è nota; manca solo il rientro — non richiedere entrambe le date.",
            aliases=["end_date", "period_end"],
            when="departure_known_return_missing",
        ),
        SlotDef(
            name="lodging",
            kind="conditional",
            ui_label="Alloggio",
            question_template="Hai già un alloggio o prenotazioni?",
            question_reason="Date, destinazione e trasporto noti — prossimo pezzo utile: alloggio.",
            when="core_travel_known",
            aliases=["accommodation", "bookings"],
            chips=[
                QuestionChip(id="booked", label="Già prenotato", value="booked"),
                QuestionChip(id="need", label="Da cercare", value="need"),
                QuestionChip(id="host", label="Ospiti / casa", value="host"),
            ],
        ),
        SlotDef(
            name="departure_place",
            kind="conditional",
            ui_label="Partenza da",
            question_template="Da dove parti?",
            question_reason="Origine per Maps e orario.",
            aliases=["departure", "from"],
            when="core_travel_known",
        ),
        SlotDef(
            name="transport",
            kind="conditional",
            ui_label="Trasporto",
            question_template="Come ti sposti?",
            question_reason="Trasporto utile per Maps e preparazione.",
            when="core_travel_known",
            chips=[
                QuestionChip(id="car", label="Auto", value="car"),
                QuestionChip(id="train", label="Treno", value="train"),
                QuestionChip(id="plane", label="Aereo", value="plane"),
            ],
        ),
        SlotDef(
            name="companions",
            kind="conditional",
            ui_label="Compagni",
            question_template="Con chi viaggi?",
            question_reason="Viaggiatori per pianificazione.",
            aliases=["travelers"],
            when="core_travel_known",
        ),
        SlotDef(
            name="budget",
            kind="optional",
            ui_label="Budget",
            question_template="Hai un budget in mente? (opzionale)",
            question_reason="Opzionale.",
        ),
        SlotDef(
            name="stops",
            kind="optional",
            ui_label="Tappe",
            question_template="Hai tappe intermedie? (opzionale)",
            question_reason="Opzionale.",
        ),
        SlotDef(
            name="preferences",
            kind="optional",
            ui_label="Preferenze",
            question_template="Preferenze o preparativi? (opzionale)",
            question_reason="Opzionale.",
        ),
    ],
)
