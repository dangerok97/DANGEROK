"""Selective CAL164 recovery against the current ORA Core.

No external calendar, model requests, user account or side effects. This is
only a verified weekday rendering correction, not a time-zone or write fix.
"""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.grounding.calendar_weekday import guard_calendar_weekdays


PROVEN = [{
    "name": "get_calendar_events", "status": "ok",
    "payload": {
        "status": "ok",
        "events": [{
            "start_datetime": "2026-10-20T18:00:00+02:00",
            "timezone": "Europe/Rome",
        }],
    },
}]


@pytest.mark.parametrize("said,expected,n", [
    ("lunedì 20 ottobre 2026 alle 18:00", "martedì 20 ottobre 2026 alle 18:00", 1),
    ("Martedi 20 ottobre 2026 alle 18:00", "Martedi 20 ottobre 2026 alle 18:00", 0),
    ("martedì 20 ottobre 2026 alle 18:00", "martedì 20 ottobre 2026 alle 18:00", 0),
    ("lunedì 20 ottobre", "lunedì 20 ottobre", 0),
    ("lunedì 19 ottobre 2026", "lunedì 19 ottobre 2026", 0),
    ("«lunedì 20 ottobre 2026»", "«lunedì 20 ottobre 2026»", 0),
    ("`lunedì 20 ottobre 2026`", "`lunedì 20 ottobre 2026`", 0),
])
def test_only_calendar_proven_unquoted_full_date_can_change(said, expected, n):
    assert guard_calendar_weekdays(said, PROVEN) == (expected, n)


@pytest.mark.parametrize("status", ["failed", "error", "partial", "needs_client"])
def test_failed_calendar_observation_does_not_rewrite_text(status):
    evidence = deepcopy(PROVEN)
    evidence[0]["status"] = status
    said = "lunedì 20 ottobre 2026 alle 18:00"
    assert guard_calendar_weekdays(said, evidence) == (said, 0)


def test_prefetch_time_zone_and_unrelated_source_are_not_authority():
    payload = {
        "events": [{
            "start_datetime": "2026-10-19T22:30:00Z",
            "timezone": "Europe/Rome",
        }],
    }
    assert guard_calendar_weekdays(
        "lunedì 20 ottobre 2026 alle 18:00", [], payload,
    ) == ("martedì 20 ottobre 2026 alle 18:00", 1)
    evidence = deepcopy(PROVEN)
    evidence[0]["name"] = "web_search"
    assert guard_calendar_weekdays(
        "lunedì 20 ottobre 2026 alle 18:00", evidence,
    ) == ("lunedì 20 ottobre 2026 alle 18:00", 0)


@pytest.mark.asyncio
async def test_current_core_saves_same_correct_date_to_chat(monkeypatch):
    from conversation_engine.ai_core import loop, calendar_ahead, state
    from conversation_engine.models import ConversationSession
    db = AsyncMongoMockClient().calendar_reconciliation
    user = "cal-reconcile-synthetic-owner"
    await db.users.insert_one({"id": user, "timezone": "Europe/Rome"})
    monkeypatch.setattr(calendar_ahead, "the_next_two_days", AsyncMock(
        return_value={"events": PROVEN[0]["payload"]["events"]}
    ))
    async def decide(*args, **kwargs):
        return {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "L'impegno è lunedì 20 ottobre 2026 alle 18:00.",
        }
    session = ConversationSession(user_id=user)
    outcome = await loop.run_cognitive_loop(
        sess=session, db=db,
        user_message="Qual è il giorno e l'ora dell'impegno?",
        decision_fn=decide,
    )
    assert outcome.ora_text == "L'impegno è martedì 20 ottobre 2026 alle 18:00."
    assert state.get_ai_state(session)["recent_turns"][-1]["text"] == outcome.ora_text
    assert outcome.tool_calls == 0
