"""V88b — live temporary situations surface urgent action before monitoring."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_conversation_prompt_leads_with_current_actionable_risk():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")

    assert "LEAD with the concrete action the person should take now" in prompt
    assert "urgent action now" in prompt
    assert "Give them a usable first expectation now" in prompt
    assert "A current risk is not" in prompt
    assert "future monitoring" in prompt


def test_background_reasoning_does_not_wait_on_already_active_risk():
    source = (ROOT / "agent" / "reasoning.py").read_text(encoding="utf-8")

    assert "do NOT choose wait merely to observe it later" in source
    assert "lead the headline with the concrete action now" in source
    assert "Do not lead with 'sto monitorando'" in source
    assert "bounded future estimate" in source


def test_behavior_remains_domain_neutral():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    reasoning = (ROOT / "agent" / "reasoning.py").read_text(encoding="utf-8")

    # Laundry is the acceptance example, never a production router/category.
    assert "panni" not in prompt.lower()
    assert "laundry" not in prompt.lower()
    assert "panni" not in reasoning.lower()
    assert "laundry" not in reasoning.lower()
