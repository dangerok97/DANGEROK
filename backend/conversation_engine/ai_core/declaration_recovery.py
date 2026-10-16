"""Recover only a reversible CREATE after a failed second model declaration."""
from copy import deepcopy

_ALLOWED = frozenset({
    "situation_create_missing_source_refs",
    "situation_create_missing_linked_object_refs",
})


def recover_incomplete_create(raw, errors):
    if (not isinstance(raw, dict) or not errors
            or not set(errors).issubset(_ALLOWED)
            or raw.get("response_mode") != "tool"):
        return None
    update, tool = raw.get("situation_update"), raw.get("tool_call")
    if (not isinstance(update, dict) or not isinstance(tool, dict)
            or update.get("operation") != "create"
            or update.get("situation_id") not in (None, "")
            or (tool.get("capability") or tool.get("name")) != "schedule_situation_check"):
        return None
    if ("location_label" not in update
            or not str(update.get("summary") or "").strip()
            or not str(update.get("desired_outcome") or "").strip()
            or not str(update.get("attention_intent") or "").strip()
            or update.get("source", "user_conversation") != "user_conversation"):
        return None
    missing = {"source_refs", "linked_object_refs"} - set(update)
    if not missing or not all(f"situation_create_missing_{field}" in errors
                              for field in missing):
        return None
    restored = deepcopy(update)
    for field in missing:
        restored[field] = []
    restored.update(current_state_summary=None, expected_outcome_summary=None,
                    next_check_summary=None)
    return {
        "response_mode": "answer",
        "message_to_user": "Ho registrato la situazione, ma il prossimo controllo non risulta ancora programmato.",
        "situation_update": restored,
        "tool_call": None,
        "question": None,
    }
