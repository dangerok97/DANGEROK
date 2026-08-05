"""Medical / visit flow — logistics only. NEVER medical advice."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn

MEDICAL_DISCLAIMER = (
    "ORA organizza solo logistica (calendario, percorso, documenti, promemoria). "
    "Non fornisce consigli medici né diagnosi."
)


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("title") or "visita"
    has_loc = bool(ctx.get("location"))
    turns = [
        turn(
            "confirm_visit",
            f"Confermi la visita «{title}»?",
            explanation=MEDICAL_DISCLAIMER,
            options=[
                opt("yes", "Sì, organizziamo", True),
                opt("reschedule", "Devo riprogrammare", "reschedule"),
                opt("cancel", "Non serve più", "cancel"),
            ],
            brain_key="visit_confirm",
        ),
        turn(
            "add_calendar",
            "La metto in calendario?",
            explanation="Solo impegno e orario — nessun contenuto clinico.",
            options=[
                opt("yes", "Sì", True),
                opt("already", "Già in calendario", "already"),
                opt("no", "Non ora", False),
            ],
            brain_key="visit_calendar",
        ),
    ]
    if not has_loc:
        turns.append(turn(
            "location",
            "Dove si svolge la visita?",
            explanation="Per Maps e tempo di viaggio. Puoi scrivere il nome della struttura.",
            options=[
                opt("clinic", "Ambulatorio / clinica", "clinic"),
                opt("hospital", "Ospedale", "hospital"),
                opt("home", "A domicilio", "home"),
            ],
            input_kind="chips_or_text",
            brain_key="visit_location_kind",
        ))
    turns.extend([
        turn(
            "need_maps",
            "Vuoi indicazioni?",
            options=[
                opt("yes", "Sì, Maps", True),
                opt("no", "No", False),
            ],
            brain_key="visit_maps",
        ),
        turn(
            "documents",
            "Hai documenti da portare (impegnativa, tessera, referti)?",
            explanation="Ti creo un promemoria checklist — non interpreto referti.",
            options=[
                opt("yes", "Sì, ricordamelo", True),
                opt("on_ora", "Sono già su ORA", "on_ora"),
                opt("no", "Niente di particolare", False),
            ],
            brain_key="visit_docs",
        ),
        turn(
            "reminder",
            "Quando il promemoria?",
            options=[
                opt("2h", "2 ore prima", "2h"),
                opt("1d", "1 giorno prima", "1d"),
                opt("morning", "La mattina stessa", "morning"),
                opt("none", "Nessuno", "none"),
            ],
            brain_key="visit_reminder",
        ),
    ])
    return turns
