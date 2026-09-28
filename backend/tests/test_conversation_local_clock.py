"""Local clock evidence, independent of server timezone and historical turns."""
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from timezone_service import ResolvedTimezone, user_clock_context
from conversation_engine.ai_core.prompt import build_user_payload


@pytest.mark.parametrize('instant,zone,expected', [
    ('2026-09-28T14:45:00+00:00', 'Europe/Rome', '2026-09-28T16:45:00+02:00'),
    ('2026-12-28T14:45:00+00:00', 'Europe/Rome', '2026-12-28T15:45:00+01:00'),
    ('2026-09-28T22:45:00+00:00', 'Europe/Rome', '2026-09-29T00:45:00+02:00'),
    ('2026-03-29T01:30:00+00:00', 'Europe/Rome', '2026-03-29T03:30:00+02:00'),
    ('2026-10-25T01:30:00+00:00', 'Europe/Rome', '2026-10-25T02:30:00+01:00'),
    ('2026-09-28T14:45:00+00:00', 'America/New_York', '2026-09-28T10:45:00-04:00'),
])
def test_local_clock_and_prompt_share_one_instant(instant, zone, expected):
    with patch('timezone_service.resolve_user_timezone', AsyncMock(return_value=ResolvedTimezone(zone, 'user_confirmed'))):
        clock = asyncio.run(user_clock_context(None, 'u', now=datetime.fromisoformat(instant)))
    assert clock['local_datetime'] == expected
    payload = json.loads(build_user_payload(user_message='Che ore sono?', recent_turns=[{'at': instant}],
        active_goal=None, context_facts=[], tools=[], observations=[], clock_context=clock))
    assert payload['current_clock']['local_time'] == expected[11:16]
    assert payload['today'] == expected[:10]
    assert payload['current_clock']['authority'] == 'user_confirmed'


def test_outage_uses_labelled_rome_fallback_not_utc():
    with patch('timezone_service.resolve_user_timezone', AsyncMock(side_effect=RuntimeError('offline'))):
        clock = asyncio.run(user_clock_context(None, 'u', now=datetime.fromisoformat('2026-09-28T14:45:00+00:00')))
    assert clock['local_time'] == '16:45'
    assert clock['authority'] == 'system_fallback'


def test_loop_delivers_fresh_clock_on_every_turn():
    from mongomock_motor import AsyncMongoMockClient
    from conversation_engine.models import ConversationSession
    from conversation_engine.ai_core.loop import run_cognitive_loop

    async def body():
        db = AsyncMongoMockClient().clock_test
        await db.users.insert_one({'id': 'clock-user', 'settings': {'timezone': 'Europe/Rome'}})
        sess = ConversationSession(user_id='clock-user')
        seen = []
        async def respond(system, user):
            payload = json.loads(user)
            seen.append(payload['current_clock'])
            assert payload['today'] == payload['current_clock']['local_date']
            return {'response_mode': 'answer', 'ora': 'Sono le ' + payload['current_clock']['local_time'], 'confidence': 1.0}
        with patch('timezone_service.user_clock_context', wraps=user_clock_context) as resolve:
            await run_cognitive_loop(sess=sess, user_message='Che ore sono?', db=db, decision_fn=respond)
            await run_cognitive_loop(sess=sess, user_message='E adesso?', db=db, decision_fn=respond)
            assert resolve.await_count == 2
        assert len(seen) == 2
        assert all(c['timezone'] == 'Europe/Rome' and c['authority'] == 'user_confirmed' for c in seen)
    asyncio.run(body())
