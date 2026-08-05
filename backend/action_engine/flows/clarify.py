"""Clarify flow — low-confidence Intent: ask user, never open wrong flow."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    options_raw = ctx.get("clarify_options") or []
    options = []
    for o in options_raw:
        if isinstance(o, dict):
            oid = o.get("id") or f"clarify_{o.get('intent')}"
            label = o.get("label") or o.get("intent") or "Altro"
            options.append(opt(oid, label, {
                "intent": o.get("intent"),
                "subtype": o.get("subtype"),
            }))
    if not options:
        options = [
            opt("clarify_study", "Preparare un esame", {"intent": "study", "subtype": "exam_preparation"}),
            opt("clarify_event", "Creare un evento", {"intent": "event"}),
        ]
    return [
        turn(
            "clarify_intent",
            "Non sono sicuro. Vuoi preparare un esame oppure creare un evento?",
            explanation="Scelgo il percorso giusto in base alla tua risposta — niente indovinelli.",
            options=options,
            brain_key="clarified_intent",
        ),
    ]
