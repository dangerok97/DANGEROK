"""Admin / payment / invoice flow."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("title") or "pratica"
    amount = ctx.get("amount")
    amount_hint = f" Importo indicato: {amount}." if amount else ""
    return [
        turn(
            "understand",
            f"Hai chiaro di cosa si tratta («{title}»)?",
            explanation=f"Posso spiegare in sintesi dal documento, senza inventare scadenze.{amount_hint}",
            options=[
                opt("clear", "Sì, chiaro", "clear"),
                opt("explain", "Spiegami in breve", "explain"),
                opt("unsure", "Non sono sicuro", "unsure"),
            ],
            brain_key="admin_understanding",
        ),
        turn(
            "payment_status",
            "Stato del pagamento / adempimento?",
            options=[
                opt("pay_now", "Devo pagare / fare ora", "pay_now"),
                opt("scheduled", "Già programmato", "scheduled"),
                opt("done", "Già fatto", "done"),
                opt("na", "Non è un pagamento", "na"),
            ],
            brain_key="admin_payment_status",
        ),
        turn(
            "reminder",
            "Vuoi un promemoria?",
            options=[
                opt("1d", "1 giorno prima", "1d"),
                opt("3d", "3 giorni prima", "3d"),
                opt("due_morning", "La mattina della scadenza", "due_morning"),
                opt("none", "No", "none"),
            ],
            brain_key="admin_reminder",
        ),
        turn(
            "calendar",
            "La metto in calendario come scadenza?",
            options=[
                opt("yes", "Sì", True),
                opt("already", "Già c'è", "already"),
                opt("no", "No", False),
            ],
            brain_key="admin_calendar",
        ),
        turn(
            "open_doc",
            "Vuoi tenere il documento collegato a questa pratica?",
            explanation="Resta accessibile dal progetto ORA creato per questo flusso.",
            options=[
                opt("yes", "Sì", True),
                opt("no", "Non serve", False),
            ],
            brain_key="admin_keep_doc",
        ),
    ]
