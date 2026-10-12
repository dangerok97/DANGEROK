"""The model-facing examples must be accepted by the unchanged declaration gate.

These are format checks, not a claim that a live model follows the examples.
No capability is selected, executed or authorized by these tests.
"""
import json

import pytest

from agent import reasoning
from agent.service import AgentService


def test_default_step_example_is_valid_without_an_inapplicable_effect():
    example = json.loads(reasoning._STEP_DECLARATION_JSON)
    errors = []
    step = AgentService._read_step(example, 0, validation_errors=errors)
    assert step is not None, errors
    assert step.step_type != "execute" and step.external_effect is False
    assert "effect_type" not in example and "effect_target" not in example
    assert "asks" not in example and "ask_kind" not in example
    assert "parameters" in example and "input_refs" in example


@pytest.mark.parametrize("kind", ["execute", "ask_user"])
def test_specialized_example_is_a_complete_valid_declaration(kind):
    name = "_EXECUTE_STEP_DECLARATION_JSON" if kind == "execute" else "_ASK_STEP_DECLARATION_JSON"
    example = json.loads(getattr(reasoning, name))
    errors = []
    step = AgentService._read_step(example, 0, validation_errors=errors)
    assert step is not None, errors
    assert step.step_type == kind
    if kind == "execute":
        assert all(key in example for key in ("effect_type", "effect_target", "external_effect",
            "reaches_somebody_else", "reversibility", "parameters"))
        assert step.effect_target and step.external_effect is True
    else:
        assert step.asks and step.ask_kind == "knowledge"
        assert step.external_effect is False


@pytest.mark.parametrize("bad", [None, [], {}, False, 1])
def test_wrong_type_effect_is_still_rejected_in_any_step(bad):
    for kind in ("inspect", "prepare", "execute"):
        errors = []
        assert AgentService._read_step({"intent": "Synthetic declaration", "step_type": kind,
            "effect_type": bad}, 0, validation_errors=errors) is None
        assert errors == [{"field": "effect_type", "issue": "wrong_type"}]
