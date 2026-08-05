"""Event flow — ticket, calendar, route, reminder, leave time."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("title") or "evento"
    has_loc = bool(ctx.get("location"))
    turns = [
        turn(
            "has_ticket",
            f"Hai già il biglietto per «{title}»?",
            explanation="Se sì, posso solo organizzare calendario e partenza.",
            options=[
                opt("yes", "Sì", True),
                opt("no", "No", False),
                opt("na", "Non serve", "na"),
            ],
            brain_key="event_ticket",
        ),
        turn(
            "add_calendar",
            "Lo metto in calendario?",
            explanation="Creo un impegno ORA (e sync Google se collegato, in seguito).",
            options=[
                opt("yes", "Sì", True),
                opt("already", "È già in calendario", "already"),
                opt("no", "Non ora", False),
            ],
            brain_key="event_calendar",
        ),
    ]
    if not has_loc:
        turns.append(turn(
            "location",
            "Dove si svolge?",
            explanation="Serve per indicazioni e orario di partenza.",
            options=[
                opt("home_area", "Vicino a casa", "home_area"),
                opt("city", "In città", "city"),
                opt("far", "Fuori città", "far"),
                opt("online", "Online / da remoto", "online"),
            ],
            input_kind="chips_or_text",
            brain_key="event_location_kind",
        ))
    turns.extend([
        turn(
            "need_route",
            "Vuoi indicazioni / percorso?",
            explanation="Apro Maps quando serve; non invento traffico in tempo reale senza dati.",
            options=[
                opt("yes", "Sì, Maps", True),
                opt("no", "No", False),
            ],
            allow_skip=True,
            brain_key="event_need_route",
        ),
        turn(
            "reminder",
            "Quando vuoi il promemoria?",
            explanation="Ti ricordo in tempo per prepararti e partire.",
            options=[
                opt("1h", "1 ora prima", "1h"),
                opt("3h", "3 ore prima", "3h"),
                opt("1d", "1 giorno prima", "1d"),
                opt("none", "Nessun promemoria", "none"),
            ],
            brain_key="event_reminder",
        ),
        turn(
            "leave_time",
            "Vuoi calcolare un orario di partenza?",
            explanation="Stima semplice in base alla distanza indicata; senza GPS live.",
            options=[
                opt("yes_30", "Sì, ~30 min di viaggio", "30"),
                opt("yes_60", "Sì, ~60 min di viaggio", "60"),
                opt("no", "No", "no"),
            ],
            brain_key="event_leave_buffer",
        ),
    ])
    return turns
