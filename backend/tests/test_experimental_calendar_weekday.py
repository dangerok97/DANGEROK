"""Selective salvage of #279: only sourced weekday display can be corrected.

Runs with synthetic events and no network/calendar writes. This belongs to
the unified experimental branch, NOT production.
"""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.grounding.calendar_weekday import guard_calendar_weekdays

EVIDENCE = [{
    'name': 'get_calendar_events', 'status': 'ok',
    'payload': {'status': 'ok', 'events': [
        {'start_datetime': '2026-10-15T10:30:00+02:00', 'timezone': 'Europe/Rome'},
    ]},
}]


@pytest.mark.parametrize('text,expected,count', [
    ('mercoledì 15 ottobre 2026 alle 10:30', 'giovedì 15 ottobre 2026 alle 10:30', 1),
    ('Mercoledi 15 ottobre 2026', 'Giovedì 15 ottobre 2026', 1),
    ('**mercoledì 15 ottobre 2026**', '**giovedì 15 ottobre 2026**', 1),
    ('mercoledì **15 ottobre 2026**', 'giovedì **15 ottobre 2026**', 1),
    ('giovedì 15 ottobre 2026', 'giovedì 15 ottobre 2026', 0),
    ('mercoledì 15 ottobre', 'mercoledì 15 ottobre', 0),
    ('mercoledì 16 ottobre 2026', 'mercoledì 16 ottobre 2026', 0),
    ('mercoledì 31 febbraio 2026', 'mercoledì 31 febbraio 2026', 0),
    ('«mercoledì 15 ottobre 2026»', '«mercoledì 15 ottobre 2026»', 0),
    ('`mercoledì 15 ottobre 2026`', '`mercoledì 15 ottobre 2026`', 0),
])
def test_only_explicit_verified_event_weekday_can_be_corrected(text, expected, count):
    assert guard_calendar_weekdays(text, EVIDENCE) == (expected, count)


@pytest.mark.parametrize('status', ['failed', 'partial', 'error', 'needs_client'])
def test_failed_read_cannot_support_calendar_wording(status):
    evidence = deepcopy(EVIDENCE)
    evidence[0]['status'] = status
    text = 'mercoledì 15 ottobre 2026'
    assert guard_calendar_weekdays(text, evidence) == (text, 0)


def test_prefetch_timezone_supports_a_date_but_unrelated_tools_do_not():
    text = 'giovedì 16 ottobre 2026'
    ahead = {'events': [{'start_datetime': '2026-10-15T22:30:00Z',
                         'timezone': 'Europe/Rome'}]}
    assert guard_calendar_weekdays(text, [], ahead) == ('venerdì 16 ottobre 2026', 1)
    evidence = deepcopy(EVIDENCE)
    evidence[0]['name'] = 'web_search'
    assert guard_calendar_weekdays('mercoledì 15 ottobre 2026', evidence)[1] == 0


@pytest.mark.asyncio
async def test_cognitive_core_history_shows_same_correct_day_as_final_answer(monkeypatch):
    from conversation_engine.ai_core import loop, calendar_ahead, state
    from conversation_engine.models import ConversationSession

    db = AsyncMongoMockClient().experimental_calendar_weekday
    user = 'synthetic-exp-calendar-user'
    await db.users.insert_one({'id': user, 'timezone': 'Europe/Rome'})
    monkeypatch.setattr(calendar_ahead, 'the_next_two_days', AsyncMock(return_value={
        'events': EVIDENCE[0]['payload']['events']
    }))
    async def decide(*args, **kwargs):
        return {
            'response_mode': 'answer', 'reasoning_status': 'enough_information',
            'message_to_user': 'La visita è mercoledì 15 ottobre 2026 alle 10:30.',
        }
    sess = ConversationSession(user_id=user)
    result = await loop.run_cognitive_loop(sess=sess, db=db,
                                            user_message='Quando è la visita?',
                                            decision_fn=decide)
    assert result.ora_text == 'La visita è giovedì 15 ottobre 2026 alle 10:30.'
    assert state.get_ai_state(sess)['recent_turns'][-1]['text'] == result.ora_text
    assert result.tool_calls == 0
