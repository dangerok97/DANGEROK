"""No invented identity or side effects from terminal model repair."""
from copy import deepcopy
import pytest
from conversation_engine.ai_core.declaration_recovery import recover_incomplete_create as recover


def candidate():
    return {"response_mode": "tool",
            "tool_call": {"capability": "schedule_situation_check",
                          "arguments": {"situation_id": "place:inventato"}},
            "situation_update": {
                "operation": "create", "summary": "Attività in corso",
                "desired_outcome": "Sapere quando intervenire",
                "attention_intent": "Valutare le condizioni",
                "location_label": "Tarquinia",
                "started_at": "2026-10-12T22:23:24+02:00"},
            "memory_candidates": [{"summary": "Untrusted"}]}


def test_recovers_declaration_without_schedule_or_memory():
    original = candidate()
    before = deepcopy(original)
    result = recover(original, ["situation_create_missing_source_refs",
                                "situation_create_missing_linked_object_refs"])
    assert result["response_mode"] == "answer" and result["tool_call"] is None
    assert result["situation_update"]["source_refs"] == []
    assert result["situation_update"]["linked_object_refs"] == []
    assert result["situation_update"]["started_at"] == before["situation_update"]["started_at"]
    assert result["situation_update"]["location_label"] == "Tarquinia"
    assert "memory_candidates" not in result and original == before


@pytest.mark.parametrize("errors", [
    [], ["situation_create_missing_location_label"],
    ["situation_create_missing_source_refs", "bad_situation_update"],
    ["consequential_write_blocked"],
])
def test_does_not_mask_another_governance_error(errors):
    assert recover(candidate(), errors) is None


@pytest.mark.parametrize("mutation", [
    {"summary": ""}, {"desired_outcome": None}, {"attention_intent": ""},
    {"situation_id": "sit_fake"}, {"operation": "update"}, {"source": "inferred"},
])
def test_declines_unverified_create(mutation):
    item = candidate()
    item["situation_update"].update(mutation)
    assert recover(item, ["situation_create_missing_source_refs"]) is None


@pytest.mark.parametrize("mutation", [
    {"response_mode": "answer"}, {"tool_call": None},
    {"tool_call": {"capability": "call_phone"}},
])
def test_does_not_rewrite_other_tools(mutation):
    item = candidate()
    item.update(mutation)
    assert recover(item, ["situation_create_missing_source_refs"]) is None


def test_missing_location_label_does_not_qualify():
    item = candidate()
    del item["situation_update"]["location_label"]
    assert recover(item, ["situation_create_missing_source_refs"]) is None


def test_complete_context_does_not_qualify():
    item = candidate()
    item["situation_update"].update(source_refs=[], linked_object_refs=[])
    assert recover(item, ["situation_create_missing_source_refs"]) is None
