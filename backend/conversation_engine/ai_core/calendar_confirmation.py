"""Extract frozen pending calendar confirmation state from tool observations.

Conversation semantics belong to the cognitive model. This module only copies
the exact confirmation request produced by the governed calendar capability so
it can survive into the next turn.
"""


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
    return (
        request
        if isinstance(request, dict)
        and request.get("question")
        and request.get("arguments")
        else None
    )
