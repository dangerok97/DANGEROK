"""Conversation planner — Life Experience turns (not a wizard)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ai_life_strategist.conversational_voice import (
    render_conversational_turn,
    render_wrap_synthesis,
    resolve_turn_question,
    synthesize_first_picture,
    validate_rendered_text,
)
from ai_life_strategist.models import StrategistPlan

LIFE_PLACES_GAP_KEYS = frozenset({
    "mlc.life_places.home",
    "mlc.life_places",
})

PHILOSOPHY_GREETING = (
    "Ciao, sono ORA.\n\n"
    "Prima di iniziare vorrei conoscerti un po’. "
    "Non serve raccontarmi tutto: partiamo da quello che conta per te adesso."
)

INTERRUPT_HOME_HINT = (
    "ORA può aiutarti ancora di più — quando vuoi, raccontami un pezzo della tua vita "
    "o carica un documento utile."
)

# Forbidden UX copy (wizard smell + internal jargon)
FORBIDDEN_PHRASES = (
    "completa il profilo",
    "life setup",
    "completa la configurazione",
    "wizard",
    "questionario obbligatorio",
    "completa il questionario",
    "minimum life context",
    "mlc",
    "life graph",
    "coverage",
)


def build_greeting_turn(plan: StrategistPlan) -> Dict[str, Any]:
    # First contact shell stays deterministic; question may use validated spoken_question
    q = validate_rendered_text(plan.spoken_question, kind="question") or (
        plan.next_best_question or ""
    ).strip()
    body = f"{PHILOSOPHY_GREETING}\n\n{q}"
    return {
        "kind": "conversation_turn",
        "role": "ora",
        "text": body,
        "question": q or plan.next_best_question,
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
            "experience": "life_experience",
        },
        "plan": plan.public(),
    }


def build_active_turn(
    plan: StrategistPlan,
    *,
    ack: Optional[str] = None,
    last_bridge: Optional[str] = None,
    known_facts: Optional[Dict[str, Any]] = None,
    spoken_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Assemble active turn. Prefer validated Gemini spoken fields (Architecture A)
    via render_conversational_turn; SAFE deterministic fallback otherwise.
    """
    if spoken_text and spoken_text.strip():
        text = spoken_text.strip()
        used_bridge = None
    else:
        text = render_conversational_turn(
            {
                "plan": plan,
                "ack": ack,
                "last_bridge": last_bridge,
                "known_facts": known_facts or {},
            }
        )
        used_bridge = None
        bridge = plan.conversational_bridge or (plan.meta or {}).get("conversational_bridge")
        if (
            bridge
            and not (plan.acknowledgement or ack)
            and bridge.strip() in text
            and (not last_bridge or bridge.strip() != str(last_bridge).strip())
        ):
            used_bridge = str(bridge).strip()

    actions = [
        {"id": "answer", "label": "Rispondi"},
        {"id": "skip_domain", "label": "Salta questo tema"},
        {"id": "explain", "label": "Perché me lo chiedi?"},
        # exit/postpone remain in contract for resume paths; FE hides on first-run pre-MLC
        {"id": "exit", "label": "Esci"},
    ]
    gap_key = str((plan.meta or {}).get("gap_key") or "")
    nucleus = str((plan.meta or {}).get("mlc_nucleus") or "")
    if gap_key in LIFE_PLACES_GAP_KEYS or nucleus == "life_places" or gap_key.startswith(
        "mlc.life_places"
    ):
        actions.insert(
            0,
            {"id": "use_current_location", "label": "Usa la mia posizione"},
        )
    if plan.prefer_document and plan.recommended_document:
        actions.insert(0, {
            "id": "upload_doc",
            "label": f"Carica {plan.recommended_document.label}",
            "doc_type": plan.recommended_document.doc_type,
        })
        actions.append({"id": "doc_not_now", "label": "Non ora"})
        actions.append({"id": "doc_prefer_answer", "label": "Preferisco rispondere"})

    question = resolve_turn_question(plan) or plan.next_best_question
    return {
        "kind": "conversation_turn",
        "role": "ora",
        "text": text,
        "question": question,
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
        "meta": {"used_bridge": used_bridge} if used_bridge else {},
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


async def wrap_up_turn(
    *,
    known_facts: Optional[Dict[str, Any]] = None,
    domains: Optional[List[str]] = None,
    benefits: Optional[List[str]] = None,
    force_fallback: bool = False,
) -> Dict[str, Any]:
    """Final moment — AI wrap synthesis (optional) or SAFE/hardened deterministic. CTA: Entra in ORA."""
    _ = domains, benefits  # kept for call-site compatibility; synthesis uses facts
    text = await render_wrap_synthesis(known_facts or {}, force_fallback=force_fallback)
    # Absolute last resort
    if not (text or "").strip():
        text = synthesize_first_picture(known_facts or {})
    return {
        "kind": "conversation_turn",
        "role": "ora",
        "text": text,
        "question": None,
        "ui": {
            "mode": "natural_conversation",
            "wizard": False,
            "done": True,
            "experience": "life_experience",
        },
        "actions": [{"id": "done", "label": "Entra in ORA"}],
    }
