"""The verifier must complete a bounded comparison without inventing terms."""
import json

import pytest

from agent import reasoning


@pytest.mark.asyncio
async def test_verifier_requires_useful_supported_delta_without_unknown_contract_inventions(monkeypatch):
    calls = []

    async def model(system, user, **_kwargs):
        calls.append((system, json.loads(user)))
        return {
            "outcome": "achieved",
            "reasoning": "Il confronto basato sulla nota è completo, con condizioni ignote dichiarate.",
            "what_is_missing": "", "revisit_in_hours": None,
            "relied_on": ["evd_owned"], "criteria_met": ["Confronto annuale e mensile"],
        }

    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await reasoning.verify_goal(
        {"objective": "Confrontare i costi", "desired_outcome": "Confronto scritto di 12 mesi",
         "success_criteria": ["Costi e vincoli della fonte"], "stop_conditions": []},
        evidence={
            "what_was_found": [{"evidence_id": "evd_owned",
                                "what_was_found": "Nota dell'utente: 15 al mese, 120 annuali."}],
            "prepared_result": "La nota dell'utente riporta 180 annui o 120 anticipati: differenza 60.",
            "prepared_source_refs": ["evd_owned"], "steps": [],
        },
    )
    assert result["outcome"] == "achieved"
    prompt, payload = calls[0]
    assert "unknown provider condition is an uncertainty to disclose" in prompt
    # Adjacent prompt fragments read "Equally, do NOT"; enforce the
    # substantive refusal rather than a punctuation-dependent prefix.
    assert "NOT mark achieved if the saved comparison omitted a material difference" in prompt
    assert "misstated its horizon, hid provenance, or asserted an unsupported condition" in prompt
    assert "Do not demand knowledge of hypothetical penalties" in prompt
    assert payload["what_was_done"]["prepared_result"].endswith("differenza 60.")
    assert payload["what_was_done"]["prepared_source_refs"] == ["evd_owned"]
