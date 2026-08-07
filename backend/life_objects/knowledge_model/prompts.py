"""Gemini consultant prompts — always separate Facts / Hypotheses / Questions / Recommendations / Decisions.

Never mix sections. Never auto-promote Hypothesis → Fact.
Backend remains authority.
"""
from __future__ import annotations

from typing import Any, Dict, List

KNOWLEDGE_SECTION_RULES = """
Sezioni OBBLIGATORIE e SEPARATE (non mischiare):
1. Facts — solo informazioni già confermate (documento verificato, utente, calendario, edit manuale).
2. Hypotheses — ciò che ORA pensa; mai trattarle come Facts; mai auto-promuovere.
3. Questions — domande per confermare ipotesi o colmare lacune.
4. Recommendations — suggerimenti utili (non sono Decisions finché non elevate).
5. Decisions — raccomandazioni importanti con outcome utente (accepted/rejected/never_ask_again…).

Regole dure:
- invented_facts=false sempre.
- Non inventare valori assenti dal contesto.
- Non promuovere Hypothesis → Fact.
- Gemini = consultant; backend = autorità.
""".strip()


def knowledge_reasoning_system_prompt() -> str:
    return (
        "Sei il consulente Digital Twin di ORA (Life Object Knowledge Model). "
        "Rispondi SOLO con JSON che separa Facts, Hypotheses, Questions, "
        "Recommendations, Decisions. " + KNOWLEDGE_SECTION_RULES
    )


def build_knowledge_prompt_payload(obj_public: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal context for Gemini — never send secrets."""
    return {
        "task": "digital_twin_knowledge_pass",
        "rules": KNOWLEDGE_SECTION_RULES,
        "object": {
            "id": obj_public.get("id"),
            "type": obj_public.get("type"),
            "title": obj_public.get("title"),
            "identity": obj_public.get("identity") or {},
            "state": {
                k: v for k, v in (obj_public.get("state") or {}).items()
                if not str(k).startswith("_")
            },
            "facts_count": len(obj_public.get("facts") or []),
            "hypotheses_count": len(obj_public.get("hypotheses") or []),
            "decisions_count": len(obj_public.get("decisions") or []),
            "memory_count": len(obj_public.get("memory") or []),
        },
        "output_schema": {
            "facts": [{"type": "str", "value": "any", "confidence": 0.0, "explanation": "str"}],
            "hypotheses": [{
                "type": "str", "value": "any", "confidence": 0.0,
                "reason": "str", "question_to_confirm": "str",
                "missing_information": ["str"], "evidence": ["str"],
            }],
            "questions": [{"question": "str", "why": "str"}],
            "recommendations": [{"title": "str", "benefit": "str", "risk": "str"}],
            "decisions": [{
                "title": "str", "reason": "str", "benefit": "str",
                "risk": "str", "alternatives": ["str"], "ai_reasoning": "str",
            }],
        },
        "hard_blocks": [
            "never_auto_promote_hypothesis_to_fact",
            "never_delete_facts",
            "never_invent",
        ],
    }


def separate_ai_sections(raw: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Normalize AI output into five clean buckets (backend authority)."""
    if not isinstance(raw, dict):
        return {
            "facts": [], "hypotheses": [], "questions": [],
            "recommendations": [], "decisions": [],
        }
    return {
        "facts": list(raw.get("facts") or []) if isinstance(raw.get("facts"), list) else [],
        "hypotheses": list(raw.get("hypotheses") or []) if isinstance(raw.get("hypotheses"), list) else [],
        "questions": list(raw.get("questions") or []) if isinstance(raw.get("questions"), list) else [],
        "recommendations": list(raw.get("recommendations") or []) if isinstance(raw.get("recommendations"), list) else [],
        "decisions": list(raw.get("decisions") or []) if isinstance(raw.get("decisions"), list) else [],
    }
