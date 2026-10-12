"""Typed diagnostics observe rejected declarations without repairing them."""
from copy import deepcopy
import json

import pytest

from scripts import autonomy_completion_eval_v162 as gate


PRIVATE = "synthetic-private-effect-target-and-parameters"


@pytest.mark.parametrize("stage,field", [("make_plan", "steps"), ("reconsider", "revised_steps")])
@pytest.mark.parametrize("value,kind", [
    (None, "null"), (False, "boolean"), (1, "integer"), (1.5, "number"),
    (PRIVATE, "text"), ([PRIVATE], "array"), ({PRIVATE: PRIVATE}, "object"),
])
def test_effect_type_is_observed_without_exporting_or_modifying_its_value(stage, field, value, kind):
    response = {field: [{"intent": "Read the owned source", "step_type": "inspect",
        "capability_needed": "information.read", "effect_type": value,
        "effect_target": PRIVATE, "parameters": {PRIVATE: PRIVATE}}]}
    original = deepcopy(response)
    report = gate._decision_result(stage, response)
    observed, = report[field]
    assert observed["declaration_field_kinds"]["effect_type"] == kind
    assert observed["declaration_field_kinds"]["parameters"] == "object"
    assert observed["declaration_field_kinds"]["effect_target"] == "text"
    assert observed["capability_needed"] == "information.read"
    assert "effect_type" not in observed and "effect_target" not in observed
    assert "parameters" not in observed and PRIVATE not in json.dumps(report)
    assert response == original


def test_missing_effect_is_distinct_from_null_and_legacy_aliases_remain_separate():
    raw = {"revised_steps": [{"type": "inspect", "intent": "Read the cited note",
        "what_kind_of_change": None, "execution_parameters": {PRIVATE: PRIVATE}}]}
    report = gate._decision_result("reconsider", raw)
    kinds = report["revised_steps"][0]["declaration_field_kinds"]
    assert kinds["effect_type"] == "absent" and kinds["what_kind_of_change"] == "null"
    assert kinds["step_type"] == "absent" and kinds["type"] == "text"
    assert kinds["parameters"] == "absent" and kinds["execution_parameters"] == "object"
    assert PRIVATE not in json.dumps(report)


def test_diagnostics_keep_the_existing_step_bound_and_omit_malformed_values():
    response = {"steps": [{"intent": "A bounded observation", "effect_type": {PRIVATE: PRIVATE}}]
        * (gate.MAX_DIAGNOSTIC_PLAN_STEPS + 3)}
    report = gate._decision_result("make_plan", response)
    assert len(report["steps"]) == gate.MAX_DIAGNOSTIC_PLAN_STEPS
    assert report["steps_omitted"] == 3 and PRIVATE not in json.dumps(report)
    assert gate._step_declaration_diagnostic([PRIVATE]) == {"response_kind": "array"}
    assert gate._step_declaration_diagnostic(None) == {"response_kind": "none"}
