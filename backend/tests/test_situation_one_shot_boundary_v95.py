"""V95 — a one-shot capability is not temporary Situation state."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prompt_requires_situation_to_outlive_current_action():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")

    assert "PERSISTENCE BOUNDARY (critical)" in prompt
    assert "a Situation must represent contextual state that still matters" in prompt
    assert "AFTER the current turn's requested action has been carried out" in prompt
    assert 'situation_update.operation="none"' in prompt
    assert "A capability invocation is not" in prompt
    assert "a destination named only because the user asks to be taken" in prompt
    assert "input to navigation, not something to keep in temporary memory" in prompt
    assert "real user-relevant state remains unresolved beyond the" in prompt
    assert "semantic lifecycle test, not a keyword/domain router" in prompt


def test_prompt_resolves_completed_execution_artifacts_instead_of_monitoring_them():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")

    assert "execution artifact of a completed" in prompt
    assert "resolve it instead of extending or monitoring it" in prompt
