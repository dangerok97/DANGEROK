"""Study flow — exam prep intake → project + sessions."""
from __future__ import annotations

from typing import Any, Dict, List

from action_engine.flows.base import opt, turn
from action_engine.models import QuestionTurn


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    entities = ctx.get("intent_entities") or {}
    title = (
        entities.get("subject")
        or ctx.get("display_title")
        or ctx.get("title")
        or "esame"
    )
    has_doc = bool(ctx.get("source_id") and ctx.get("source_type") in (
        "document", "study", "document_action", "quiz_session",
    )) or bool(entities.get("document"))
    turns = [
        turn(
            "exam_date",
            f"Quando è l'esame «{title}»?",
            explanation="Serve per costruire sessioni e ripassi nel calendario.",
            options=[
                opt("in_3_days", "Tra 3 giorni", "in_3_days"),
                opt("in_1_week", "Tra 1 settimana", "in_1_week"),
                opt("in_2_weeks", "Tra 2 settimane", "in_2_weeks"),
                opt("in_1_month", "Tra 1 mese", "in_1_month"),
                opt("already_set", "Ho già una data", "already_set"),
            ],
            brain_key="exam_date_window",
        ),
        turn(
            "has_material",
            "Hai già materiale da studiare?",
            explanation="Appunti, slide, PDF caricati su ORA o da caricare.",
            options=[
                opt("yes_uploaded", "Sì, già su ORA", "yes_uploaded") if has_doc else opt("yes_elsewhere", "Sì, altrove", "yes_elsewhere"),
                opt("partial", "Qualcosa, incompleto", "partial"),
                opt("no", "Non ancora", "no"),
            ],
            brain_key="study_material_status",
        ),
    ]
    if has_doc:
        turns.append(turn(
            "use_uploaded",
            "Vuoi usare il documento già collegato a questa priorità?",
            explanation="Posso generare flashcard e un piano basato su quel materiale.",
            options=[
                opt("yes", "Sì, usalo", True),
                opt("no", "No, altro materiale", False),
            ],
            brain_key="use_linked_document",
        ))
    turns.extend([
        turn(
            "hours_per_day",
            "Quante ore al giorno puoi dedicare?",
            explanation="Adatto intensità e numero di sessioni.",
            options=[
                opt("30m", "30 minuti", 0.5),
                opt("1h", "1 ora", 1),
                opt("2h", "2 ore", 2),
                opt("3h_plus", "3+ ore", 3),
            ],
            brain_key="study_hours_per_day",
        ),
        turn(
            "pace",
            "Preferisci uno studio intenso o distribuito?",
            explanation="Intenso = sessioni più lunghe vicino all'esame. Distribuito = ripassi regolari.",
            options=[
                opt("intense", "Intenso", "intense"),
                opt("distributed", "Distribuito", "distributed"),
                opt("mixed", "Misto", "mixed"),
            ],
            brain_key="study_pace",
        ),
        turn(
            "tools",
            "Cosa vuoi che prepari subito?",
            explanation="Puoi cambiare dopo; parto da questa scelta.",
            options=[
                opt("plan_flash", "Piano + flashcard", "plan_flash"),
                opt("plan_only", "Solo piano e calendario", "plan_only"),
                opt("quiz", "Interrogami dopo il piano", "quiz"),
            ],
            brain_key="study_tools_pref",
        ),
    ])
    return turns
