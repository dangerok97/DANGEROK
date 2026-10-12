"""A source preview must not be mistaken for a performed read in planning."""
import json

import pytest

from agent import reasoning


@pytest.mark.asyncio
async def test_planner_instruction_requires_owned_read_before_grounded_draft(monkeypatch):
    observed = {}

    async def model(system, user, **_kwargs):
        observed["system"] = system
        observed["payload"] = json.loads(user)
        return {
            "planning_outcome": "plan",
            "reasoning": "Read the referenced note first",
            "steps": [{"intent": "Read the owned note", "step_type": "inspect",
                       "capability_needed": "information.read"}],
        }

    monkeypatch.setattr(reasoning, "_ask_model", model)
    plan = await reasoning.make_plan(
        goal={"source_refs": ["mem_synthetic"], "desired_outcome": "A comparison"},
        capabilities=[{"name": "information.read"}, {"name": "document.create"}],
        context={"current_source_context": {"sources": [{"ref": "mem_synthetic"}]}},
    )
    assert plan["planning_outcome"] == "plan"
    prompt = observed["system"]
    assert "the plan must contain a separate inspect/read step" in prompt
    assert "a source_context preview, stored Memory reference" in prompt
    assert "Do not replace an available owned-source read with speculative web research" in prompt
    assert "never send a wrong-type effect_type" in prompt
    assert "real effect_type, target, external impact and authority requirements" in prompt
    assert observed["payload"]["goal"]["source_refs"] == ["mem_synthetic"]
