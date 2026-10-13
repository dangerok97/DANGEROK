"""Exact live regression and adversarial checks, no real account/provider."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.calendar_assent import confirms_named_cancellation, cancellation_confirmation
from agent.commanded import reads_as_an_approval
from conversation_engine.ai_core.tools import calendar_caps
from home import manual_event
from home.calendar_event import event_detail

TITLE = 'ORA COLLAUDO CAL163'
OWNER = 'cal163-bound-owner'
OTHER = 'cal163-other-owner'
EXACT = "Sì, confermo: elimina soltanto l'appuntamento 'ORA COLLAUDO CAL163' appena indicato."


@pytest.mark.parametrize('reply', [EXACT,
    "Si confermo, cancella solo l'evento ORA COLLAUDO CAL163 appena proposto.",
    "Confermo: rimuovi l'appuntamento «ORA COLLAUDO CAL163»."])
def test_full_named_assent_is_supported_without_changing_global_approval(reply):
    assert confirms_named_cancellation(reply, TITLE)
    assert not reads_as_an_approval(reply)
    assert reads_as_an_approval('Sì, confermo')


@pytest.mark.parametrize('reply', [
    'No, ' + EXACT, 'Non ' + EXACT, EXACT + ' Se è domani.',
    EXACT + ' Ma non subito.', EXACT + ' E cancella anche gli altri.',
    EXACT.replace(TITLE, 'ALTRO EVENTO'), EXACT.replace('elimina', 'sposta'),
    EXACT + ' Alle 12.', 'Forse ' + EXACT, 'La mail dice: ' + EXACT,
    '"' + EXACT + '"', EXACT[:-1] + '?', EXACT + '\n',
    "Sì, confermo", "Sì, confermo la ricezione della proposta",
    "Sì, confermo: non eliminare l'appuntamento ORA COLLAUDO CAL163.",
])
def test_ambiguous_conditional_quoted_or_different_effect_never_grants_assent(reply):
    assert not confirms_named_cancellation(reply, TITLE)


@pytest.fixture
async def world(monkeypatch):
    db = AsyncMongoMockClient().cal163_bound_confirmation
    async def tz(*_args):
        return SimpleNamespace(tz_name='Europe/Rome', authority='user_stated')
    monkeypatch.setattr(calendar_caps, 'resolve_user_timezone', tz)
    monkeypatch.setattr(manual_event, '_wake', AsyncMock())
    async def no_google(*args, **kwargs):
        raise AssertionError('No Google client in a native-calendar test')
    monkeypatch.setattr(calendar_caps, '_sync_service', no_google)
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    for uid in (OWNER, OTHER):
        await db.users.insert_one({'id': uid, 'user_id': uid, 'settings': {'timezone': 'Europe/Rome'}})
    own = await manual_event.create_manual_event(db, OWNER, title=TITLE,
        start=start.isoformat(), end=(start + timedelta(minutes=45)).isoformat(),
        tz_name='Europe/Rome', request_id='owned-fixture')
    other = await manual_event.create_manual_event(db, OTHER, title=TITLE,
        start=start.isoformat(), end=(start + timedelta(minutes=45)).isoformat(),
        tz_name='Europe/Rome', request_id='canary-fixture')
    ref = 'calendar:' + own['id']
    request = await calendar_caps.cancel_calendar_event({'calendar_ref': ref},
        {'db': db, 'user_id': OWNER, 'user_message': 'Cancella ' + TITLE})
    assert request.payload['status'] == 'authority_required'
    assert request.payload['confirmation_request']['owner_id'] == OWNER
    runtime = {'db': db, 'user_id': OWNER, 'user_message': EXACT,
        'pending_act': {'at': datetime.now(timezone.utc).isoformat(),
            'asked': request.payload['confirmation_request']['question'],
            'calendar_cancel': request.payload['confirmation_request']}}
    return db, own['id'], other['id'], runtime


@pytest.mark.asyncio
async def test_exact_live_reply_deletes_same_event_and_audits_original_words(world):
    db, own, other, runtime = world
    result = await calendar_caps.continue_calendar_action({}, runtime)
    assert result.status == 'ok', result.payload
    assert result.payload['verified'] is True
    assert (await db.life_nodes.find_one({'id': own, 'user_id': OWNER}))['status'] != 'active'
    assert (await db.life_nodes.find_one({'id': other, 'user_id': OTHER}))['status'] == 'active'
    consent = await db.autonomy_consents.find_one({'owner_id': OWNER, 'confirmation_evidence.user_utterance': EXACT})
    assert consent and consent['used_at']
    assert consent['confirmation_evidence']['calendar_ref'] == 'calendar:' + own
    assert await db.autonomy_consents.count_documents({'owner_id': OTHER}) == 0
    count = await db.agent_execution_receipts.count_documents({'owner_id': OWNER})
    await calendar_caps.continue_calendar_action({}, runtime)
    assert await db.agent_execution_receipts.count_documents({'owner_id': OWNER}) == count
    assert (await db.life_nodes.find_one({'id': other}))['status'] == 'active'


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['refusal', 'condition', 'other_title', 'expired', 'future',
    'wrong_owner', 'wrong_proposal_owner', 'wrong_ref', 'missing_snapshot', 'changed_snapshot', 'changed_target'])
async def test_bound_confirmation_cannot_authorize_a_different_or_stale_effect(world, mutation):
    db, own, other, original = world
    runtime = {**original, 'pending_act': deepcopy(original['pending_act'])}
    pending = runtime['pending_act']
    if mutation == 'refusal': runtime['user_message'] = 'No, non eliminarlo'
    elif mutation == 'condition': runtime['user_message'] = EXACT + ' Se non ha invitati.'
    elif mutation == 'other_title': runtime['user_message'] = EXACT.replace(TITLE, 'ALTRO')
    elif mutation == 'expired': pending['at'] = (datetime.now(timezone.utc) - timedelta(seconds=901)).isoformat()
    elif mutation == 'future': pending['at'] = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    elif mutation == 'wrong_owner': runtime['user_id'] = OTHER
    elif mutation == 'wrong_proposal_owner': pending['calendar_cancel']['owner_id'] = OTHER
    elif mutation == 'wrong_ref': pending['calendar_cancel']['arguments']['calendar_ref'] = 'calendar:' + other
    elif mutation == 'missing_snapshot': pending['calendar_cancel']['arguments'].pop('confirmation_snapshot')
    elif mutation == 'changed_snapshot': pending['calendar_cancel']['arguments']['confirmation_snapshot']['location'] = 'Elsewhere'
    elif mutation == 'changed_target': await db.life_nodes.update_one({'id': own}, {'$set': {'label': 'CHANGED'}})
    result = await calendar_caps.continue_calendar_action({}, runtime)
    assert result.status != 'ok', (mutation, result.payload)
    assert (await db.life_nodes.find_one({'id': own}))['status'] == 'active'
    assert (await db.life_nodes.find_one({'id': other}))['status'] == 'active'
    assert await db.autonomy_consents.count_documents({'confirmation_evidence': {'$exists': True}}) == 0


@pytest.mark.asyncio
async def test_proof_cannot_be_reused_for_other_intent_or_changed_original_message(world):
    from agent import commanded
    db, own, other, runtime = world
    proof = cancellation_confirmation(runtime)
    assert proof is not None
    intent = commanded.intent_for_request(OWNER, capability='calendar.local.write',
        effect=commanded.calendar_effect({'title': TITLE, 'delete': True}),
        parameters={'calendar_ref': own, 'starts_at': proof.starts_at, 'operation': 'delete'}, summary=TITLE)
    assert proof.permits(OWNER, intent, EXACT)
    assert not proof.permits(OTHER, intent, EXACT)
    assert not proof.permits(OWNER, intent, EXACT + ' se vuoi')
    assert not proof.permits(OWNER, intent.model_copy(update={'capability': 'calendar.write'}), EXACT)
    assert not proof.permits(OWNER, intent.model_copy(update={'parameters': {**intent.parameters, 'calendar_ref': other}}), EXACT)


@pytest.mark.asyncio
async def test_core_stops_on_first_authority_request_and_preserves_frozen_proposal(world, monkeypatch):
    from conversation_engine.ai_core import loop
    from conversation_engine.ai_core.context_broker import ContextBroker
    from conversation_engine.models import ConversationSession
    from conversation_engine.ai_core import state
    db, own, other, runtime = world
    monkeypatch.setattr(ContextBroker, 'retrieve', AsyncMock(return_value=[]))
    monkeypatch.setattr(loop, 'report_activity', AsyncMock())
    calls = 0
    async def repeats_cancel(_system, _user):
        nonlocal calls
        calls += 1
        return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
            'tool_call': {'capability': 'cancel_calendar_event', 'arguments': {'calendar_ref': 'calendar:' + own}},
            'skill_plan': {'objective': 'Eliminare soltanto il test', 'required_capabilities': ['cancel_calendar_event']},
            'situation_update': {'operation': 'none'}}
    session = ConversationSession(user_id=OWNER, meta={'ui_mode': 'ai_core', 'ai_core': {}})
    result = await loop.run_cognitive_loop(sess=session, user_message='Cancella ' + TITLE,
        db=db, decision_fn=repeats_cancel, max_steps=8)
    assert result.mode == 'ask'
    assert calls == 2 and result.tool_calls == 1
    assert result.ora_text.count('Elimino') == 1
    saved = state.get_ai_state(session)
    assert saved['pending_act']['calendar_cancel']['owner_id'] == OWNER
    assert saved['pending_act']['calendar_cancel']['arguments']['calendar_ref'] == 'calendar:' + own
    assert (await db.life_nodes.find_one({'id': own}))['status'] == 'active'
