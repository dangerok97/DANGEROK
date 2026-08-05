"""Travel flow — ask only missing pieces."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("title") or "viaggio"
    loc = (ctx.get("location") or "").strip()
    turns: List[QuestionTurn] = []
    if not loc:
        turns.append(turn(
            "destination",
            "Qual è la destinazione?",
            explanation=f"Parto da «{title}» e completo solo ciò che manca.",
            options=[
                opt("from_title", f"Usa «{title}»", "from_title"),
            ],
            input_kind="chips_or_text",
            brain_key="travel_destination",
        ))
    turns.extend([
        turn(
            "transport",
            "Come ti sposti?",
            explanation="Adatto checklist e orari (treno/aereo/auto).",
            options=[
                opt("train", "Treno", "train"),
                opt("plane", "Aereo", "plane"),
                opt("car", "Auto", "car"),
                opt("other", "Altro", "other"),
            ],
            brain_key="travel_transport",
        ),
        turn(
            "bookings",
            "Hai già prenotazioni (biglietti / hotel)?",
            options=[
                opt("all", "Sì, tutto", "all"),
                opt("partial", "Parziali", "partial"),
                opt("none", "Ancora no", "none"),
            ],
            brain_key="travel_bookings",
        ),
        turn(
            "people",
            "Quante persone?",
            options=[
                opt("solo", "Solo io", 1),
                opt("2", "2", 2),
                opt("family", "3+", 3),
            ],
            brain_key="travel_people",
        ),
        turn(
            "prep",
            "Cosa preparo per primo?",
            explanation="Proposte reali: calendario, lista bagagli, documenti, meteo (se disponibile).",
            options=[
                opt("calendar", "Calendario + promemoria", "calendar"),
                opt("luggage", "Lista bagagli", "luggage"),
                opt("docs", "Documenti da portare", "docs"),
                opt("all", "Tutto il pacchetto base", "all"),
            ],
            brain_key="travel_prep_focus",
        ),
    ])
    return turns
