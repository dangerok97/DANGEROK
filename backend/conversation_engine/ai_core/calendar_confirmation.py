"""Extract governed pending calendar confirmation state.

Conversation semantics belong to the cognitive AI. This module does not read
"yes", "no" or any other user language. It only recognizes the exact
authority-required payload emitted by the calendar capability so the durable
pending action can be exposed back to AI on the next turn.
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
