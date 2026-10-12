"""Code-owned goal origin must reach all autonomous model decisions.

An AI-proposed criterion is never silently promoted to a human instruction.
These tests make no external calls and do not add authority.
"""
import json

import pytest

from agent import reasoning
from agent.models import AutonomousGoal


def goal(origin="agent_initiated", provenance="model"):
    return AutonomousGoal(
        owner_id="synthetic-goal-origin-owner",
        origin=origin, decision_provenance=provenance,
        objective="Confrontare due alternative annotante",
        desired_outcome="Un confronto scritto che esplicita premesse e limiti",
        success_criteria=["Confrontare valori di 12 mesi"],
        stop_conditions=["Fermarsi se la fonte viene ritirata"],
        source_kind="memory", source_refs=["mem_synthetic_source"],
    )


def test_agent_criteria_are_explicitly_not_extra_user_authority():
    agent = goal()
    context = agent.for_ai()
    assert context["origin"] == "agent_initiated"
    assert context["decision_provenance"] == "model"
    assert context["criteria_source"] == "ora_inferred_not_user_instruction"
    assert context["source_refs"] == ["mem_synthetic_source"]
    assert context["success_criteria"] == ["Confrontare valori di 12 mesi"]


def test_user_requested_goal_is_not_automatically_credited_with_user_authored_criteria():
    user = goal(origin="user_requested", provenance="model")
    context = user.for_ai()
    assert context["origin"] == "user_requested"
    assert context["criteria_source"] == "check_explicit_user_requirements"
    assert context["decision_provenance"] == "model"


@pytest.mark.asyncio
async def test_origin_survives_planning_verification_and_reconsideration(monkeypatch):
    seen = []

    async def fake_model(system, encoded, **_kwargs):
        payload = json.loads(encoded)
        seen.append(payload["goal"])
        if "what_was_done" in payload:
            return {"outcome": "uncertain", "reasoning": "Serve una verifica mirata",
                    "what_is_missing": "", "relied_on": [], "criteria_met": []}
        if "what_happened" in payload:
            return {"decision": "continue", "reasoning": "La nota resta valida"}
        return {"planning_outcome": "plan", "reasoning": "Leggere la nota",
                "steps": [{"intent": "Leggere la fonte", "step_type": "inspect",
                           "capability_needed": "information.read"}]}

    monkeypatch.setattr(reasoning, "_ask_model", fake_model)
    data = goal().for_ai()
    await reasoning.make_plan(data, capabilities=[], context={})
    await reasoning.verify_goal(data, evidence={"what_was_found": [], "steps": []})
    await reasoning.reconsider(data, plan={"steps": []}, what_happened={},
                               capabilities=[])
    assert len(seen) == 3
    assert all(item["origin"] == "agent_initiated" for item in seen)
    assert all(item["criteria_source"] == "ora_inferred_not_user_instruction"
               for item in seen)


def test_bounded_dump_keeps_code_owned_origin_even_when_other_context_does_not_fit():
    data = goal().for_ai()
    encoded = reasoning._dump({
        "goal": data,
        "source_refs": ["S" * 200 for _ in range(65)],
    })
    result = json.loads(encoded)
    assert result["context_truncated"] is True
    assert result["goal"]["origin"] == "agent_initiated"
    assert result["goal"]["decision_provenance"] == "model"
    assert result["goal"]["criteria_source"] == "ora_inferred_not_user_instruction"


def test_verifier_rejects_reducer_that_loses_goal_origin(monkeypatch):
    data = goal().for_ai()
    truncated = {"goal": {key: data[key] for key in (
        "objective", "desired_outcome", "success_criteria",
        "stop_conditions", "user_clarifications_not_authority"
    ) if key in data}}
    monkeypatch.setattr(reasoning, "_dump", lambda _: json.dumps(truncated))
    assert reasoning._verification_dump({
        "goal": data, "what_was_done": {"what_was_found": [], "steps": []},
    }) is None
