"""Conversation planner — Life Experience turns (not a wizard)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ai_life_strategist.models import StrategistPlan

PHILOSOPHY_GREETING = (
    "Ciao — sono ORA. Non ti farò un questionario: "
    "voglio capire la tua vita abbastanza da aiutarti davvero, "
    "con scadenze, documenti e priorità. "
    "Possiamo parlarne 10–15 minuti, oppure saltare e riprendere più avanti "
    "quando ti fa comodo. Puoi uscire in qualsiasi momento."
)

INTERRUPT_HOME_HINT = (
    "ORA può aiutarti ancora di più — quando vuoi, raccontami un pezzo della tua vita "
    "o carica un documento utile."
)

# Forbidden UX copy (wizard smell)
FORBIDDEN_PHRASES = (
    "completa il profilo",
    "life setup",
    "completa la configurazione",
    "wizard",
    "questionario obbligatorio",
    "completa il questionario",
)


def build_greeting_turn(plan: StrategistPlan) -> Dict[str, Any]:
    return {
        "kind": "conversation_turn",
        "role": "ora",
        "text": PHILOSOPHY_GREETING,
        "question": plan.next_best_question,
        "explain": plan.explain_for_user(),
        "expected_benefit": plan.expected_benefit,
        "recommended_document": plan.recommended_document.model_dump() if plan.recommended_document else None,
        "actions": [
            {"id": "answer", "label": "Rispondi"},
            {"id": "skip_domain", "label": "Salta questo tema"},
            {"id": "postpone", "label": "Più tardi"},
            {"id": "exit", "label": "Esci"},
        ],
        "ui": {
            "mode": "natural_conversation",
            "wizard": False,
            "form": False,
            "progress_bar": False,
            "indicative_minutes": "10–15",
            "experience": "life_experience",
        },
        "plan": plan.public(),
    }


def build_active_turn(plan: StrategistPlan, *, ack: Optional[str] = None) -> Dict[str, Any]:
    text_parts = []
    if ack:
        text_parts.append(ack)
    text_parts.append(plan.next_best_question)
    actions = [
        {"id": "answer", "label": "Rispondi"},
        {"id": "skip_domain", "label": "Salta questo tema"},
        {"id": "explain", "label": "Perché me lo chiedi?"},
        {"id": "exit", "label": "Esci"},
    ]
    if plan.prefer_document and plan.recommended_document:
        actions.insert(0, {
            "id": "upload_doc",
            "label": f"Carica {plan.recommended_document.label}",
            "doc_type": plan.recommended_document.doc_type,
        })
    return {
        "kind": "conversation_turn",
        "role": "ora",
        "text": " ".join(text_parts),
        "question": plan.next_best_question,
        "explain": plan.explain_for_user(),
        "expected_benefit": plan.expected_benefit,
        "recommended_document": plan.recommended_document.model_dump() if plan.recommended_document else None,
        "alternative_question": plan.alternative_question,
        "actions": actions,
        "ui": {
            "mode": "natural_conversation",
            "wizard": False,
            "form": False,
            "progress_bar": False,
            "experience": "life_experience",
        },
        "plan": plan.public(),
    }


def build_resume_suggestion() -> Dict[str, Any]:
    """ONE intelligent Home/Proactive suggestion after interrupt — never wizard copy."""
    return {
        "title": "ORA può aiutarti ancora di più",
        "description": INTERRUPT_HOME_HINT,
        "reason": "Hai interrotto la prima conversazione; un solo suggerimento gentile, senza moduli.",
        "type": "life",
        "source": "life_experience_interrupt",
        "action": {
            "kind": "resume_life_conversation",
            "label": "Continua con ORA",
            "route": "/life-setup?resume=1",
        },
        "forbidden_copy_check": list(FORBIDDEN_PHRASES),
    }


def assert_not_wizard_copy(text: str) -> bool:
    low = (text or "").lower()
    return not any(p in low for p in FORBIDDEN_PHRASES)


def wrap_up_turn(*, domains: List[str], benefits: List[str]) -> Dict[str, Any]:
    ben = benefits[0] if benefits else "iniziare ad aiutarti in concreto"
    return {
        "kind": "conversation_turn",
        "role": "ora",
        "text": (
            "Adesso conosco abbastanza della tua situazione per iniziare ad aiutarti. "
            f"Userò questo contesto minimo — {ben} — e continuerò a conoscerti nel tempo, "
            "senza moduli da completare."
        ),
        "question": None,
        "ui": {
            "mode": "natural_conversation",
            "wizard": False,
            "done": True,
            "experience": "life_experience",
        },
        "actions": [{"id": "done", "label": "Vai alla Home"}],
    }
