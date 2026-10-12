"""Effect metadata can be N/A only for genuinely non-effect plan steps.

The normalizer must never infer permissions, targets or effect types for
a write to the outside world. These regressions preserve the strict
execute/alias contract while allowing optional JSON null on pure reads.
"""
import pytest

from agent.service import AgentService, _step_declaration


@pytest.mark.parametrize("step_type", [
    "inspect", "research", "compare", "prepare", "ask_user", "verify", "wait",
])
def test_optional_null_effect_fields_are_absent_for_internal_steps(step_type):
    raw = {
        "intent": "Una verifica senza effetti esterni",
        "step_type": step_type,
        "capability_needed": "information.read" if step_type == "inspect" else "",
        "input_refs": [],
        "external_effect": False,
        "reaches_somebody_else": False,
        "effect_target": "",
        "effect_type": None,
        "reversibility": None,
        "asks": "Quale dettaglio manca?" if step_type == "ask_user" else "",
        "ask_kind": "knowledge" if step_type == "ask_user" else None,
    }
    parsed, error = _step_declaration(raw)
    assert error is None
    assert "effect_type" not in parsed and "reversibility" not in parsed
    step = AgentService._read_step(raw, 0)
    assert step is not None and step.external_effect is False
    assert step.effect_type == "create"


@pytest.mark.parametrize("extra", [
    {"step_type": "execute"},
    {"external_effect": True},
    {"reaches_somebody_else": True},
    {"effect_target": "calendar:synthetic-event"},
])
def test_null_effect_type_is_never_repaired_for_external_or_ambiguous_steps(extra):
    raw = {
        "intent": "Non creare alcuna autorizzazione da un campo nullo",
        "step_type": "inspect", "effect_type": None,
        "external_effect": False, "reaches_somebody_else": False,
        "effect_target": "",
    }
    raw.update(extra)
    parsed, error = _step_declaration(raw)
    assert parsed is None
    assert error == {"field": "effect_type", "issue": "wrong_type"}


def test_null_effect_type_conflicting_with_a_different_alias_is_rejected():
    raw = {
        "intent": "Un alias non crea una nuova autorizzazione",
        "step_type": "inspect", "effect_type": None,
        "what_kind_of_change": "modify",
        "external_effect": False, "effect_target": "",
    }
    parsed, error = _step_declaration(raw)
    assert parsed is None
    assert error == {"field": "effect_type", "issue": "conflicting_alias"}


def test_non_null_invalid_effect_metadata_remains_rejected():
    raw = {"intent": "Solo lettura", "step_type": "inspect",
           "external_effect": False, "effect_type": ["modify"]}
    parsed, error = _step_declaration(raw)
    assert parsed is None and error == {"field": "effect_type", "issue": "wrong_type"}
