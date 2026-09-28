"""Resume a prepared calendar cancellation after a plain approval.

The target and displayed question come from the owned event, never from a
new interpretation of 'yes'. The calendar tool rechecks snapshot and authority.
"""
from datetime import datetime, timezone
from agent.commanded import reads_as_an_approval


def pending_request(observations):
    if not observations:
        return None
    last = observations[-1]
    if last.get("name") != "cancel_calendar_event":
        return None
    payload = last.get("payload") or {}
    if payload.get("status") != "authority_required":
        return None
    request = payload.get("confirmation_request")
    return request if isinstance(request, dict) and request.get("question") and request.get("arguments") else None


def next_decision(pending, message, observations, step):
    if step == 0 and isinstance(pending, dict) and reads_as_an_approval(message):
        request = pending.get("calendar_cancel")
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(pending["at"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = float("inf")
        if isinstance(request, dict) and 0 <= age <= 900:
            return {"response_mode": "tool", "confidence": 1.0,
                    "tool_call": {"capability": "cancel_calendar_event", "arguments": request["arguments"]}}
    if step == 0:
        return None
    request = pending_request(observations)
    if request:
        return {"response_mode": "act", "reasoning_status": "needs_user_input",
                "confidence": 1.0, "message_to_user": request["question"]}
    if observations:
        last = observations[-1]
        payload = last.get("payload") or {}
        if last.get("name") == "cancel_calendar_event" and last.get("status") == "ok" and payload.get("verified"):
            title = str(payload.get("what_was_removed") or "L’impegno")
            return {"response_mode": "answer", "confidence": 1.0,
                    "message_to_user": f"Ho eliminato «{title}» dal calendario."}
    return None
