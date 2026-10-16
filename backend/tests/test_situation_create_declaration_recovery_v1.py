"""Isolated v162 recovery: preserve a memory CREATE without inventing its wake.

A failed model retry must never make an external write or schedule a fake job.
"""
from copy import deepcopy
import pytest

from conversation_engine.ai_core.declaration_recovery import recover_incomplete_create


INPUT = {
    "response_mode": "tool",
    "situation_update": {
        "operation": "create",
        "source": "user_conversation",
        "location_label": "Tarquinia",
        "summary": "Panni all'aperto — TEST",
        "desired_outcome": "Capire quando conviene ritirare i panni",
        "attention_intent": "Monitorare la situazione in modo limitato",
    },
    "tool_call": {
        "capability": "schedule_situation_check",
        "arguments": {"check_at": "unknown-unverified"},
    },
}
MISSING = [
    "situation_create_missing_source_refs",
    "situation_create_missing_linked_object_refs",
]


def test_missing_empty_references_allow_memory_create_but_no_false_check():
    original = deepcopy(INPUT)
    result = recover_incomplete_create(original, MISSING)
    assert result["response_mode"] == "answer"
    assert result["tool_call"] is None
    assert result["situation_update"]["operation"] == "create"
    assert result["situation_update"]["source_refs"] == []
    assert result["situation_update"]["linked_object_refs"] == []
    assert result["situation_update"]["attention_intent"] == INPUT["situation_update"]["attention_intent"]
    assert result["message_to_user"].endswith("non risulta ancora programmato.")
    assert original == INPUT


@pytest.mark.parametrize("extra_error", [
    "calendar_mutation_unauthorized",
    "situation_update_wrong_owner",
    "situation_create_invalid_place",
])
def test_unrelated_governance_error_cannot_be_silently_recovered(extra_error):
    assert recover_incomplete_create(INPUT, [*MISSING, extra_error]) is None


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(response_mode="answer"),
    lambda x: x["tool_call"].update(capability="create_calendar_event"),
    lambda x: x["situation_update"].update(operation="update", situation_id="other"),
    lambda x: x["situation_update"].update(source="inferred"),
    lambda x: x["situation_update"].pop("desired_outcome"),
    lambda x: x["situation_update"].pop("location_label"),
])
def test_only_literal_user_create_and_one_expected_tool_can_be_recovered(mutate):
    payload = deepcopy(INPUT)
    mutate(payload)
    assert recover_incomplete_create(payload, MISSING) is None


def test_already_supplied_references_are_not_changed_by_missing_ref_errors():
    payload = deepcopy(INPUT)
    payload["situation_update"]["source_refs"] = ["user:given"]
    assert recover_incomplete_create(payload, ["situation_create_missing_source_refs"]) is None
