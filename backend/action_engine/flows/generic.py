"""Generic flow — always helps; never empty screen."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("title") or "questa priorità"
    return [
        turn(
            "intent",
            f"Cosa vuoi fare con «{title}»?",
            explanation="Una domanda alla volta — ti guido senza chat infinita.",
            options=[
                opt("organize", "Organizzala", "organize"),
                opt("remind", "Solo un promemoria", "remind"),
                opt("calendar", "Mettila in calendario", "calendar"),
                opt("done", "Segna come fatta", "done"),
                opt("clarify", "Capire meglio", "clarify"),
            ],
            brain_key="generic_intent",
        ),
        turn(
            "when",
            "Quando la affronti?",
            options=[
                opt("now", "Adesso", "now"),
                opt("today", "Oggi", "today"),
                opt("this_week", "Questa settimana", "this_week"),
                opt("later", "Più avanti", "later"),
            ],
            brain_key="generic_when",
        ),
        turn(
            "support",
            "Come ti aiuto nel concreto?",
            options=[
                opt("checklist", "Checklist breve", "checklist"),
                opt("reminder", "Promemoria", "reminder"),
                opt("project", "Crea un mini-progetto", "project"),
                opt("none", "Basta così", "none"),
            ],
            brain_key="generic_support",
        ),
    ]
