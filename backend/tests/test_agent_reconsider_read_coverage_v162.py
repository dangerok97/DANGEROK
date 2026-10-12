"""The replanner must know that a completed read is not a future event."""
import json

import pytest

from agent import reasoning


@pytest.mark.asyncio
async def test_replanning_instructions_distinguish_source_coverage_from_wait(monkeypatch):
    captured = {}

    async def fake_model(system, user, **_kwargs):
        captured["system"] = system
        captured["user"] = json.loads(user)
        return {"decision": "continue", "reasoning": "La lettura è completa"}

    monkeypatch.setattr(reasoning, "_ask_model", fake_model)
    result = await reasoning.reconsider(
        goal={"id": "synthetic-goal"},
        plan={"steps": [{"step_type": "inspect", "status": "succeeded"}]},
        what_happened={"what_was_found": [{"what_happened": "start=0, end=565, total=565, next_offset=null"}]},
        capabilities=[], clock_context={"timezone": "Europe/Rome"},
    )
    assert result["decision"] == "continue"
    system = captured["system"]
    assert "next_offset is null was read to its stated end" in system
    assert "A truncated *display*" in system
    assert "Never wait merely for an already available internal source" in system
    assert "Wait is for a future external condition" in system
    assert "ORA-generated success_criteria and stop_conditions" in system
    assert "Abandon a goal only when its actual useful outcome" in system
    assert "unknown third-party terms must remain labelled unknown" in system
    assert "work.\\n\\nWhen what_happened.result.problem" not in system
    assert "work.\n\nWhen what_happened.result.problem" in system
    assert captured["user"]["goal"]["id"] == "synthetic-goal"
