"""Same Core with a source trigger; no merchant/scenario-specific production rules."""
import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
from agent.authority import AuthorityService
from connected.models import ConnectedSignal, FieldChange
from connected.signals import SignalService
from connected.source_read import read_connected_source, redact_private_source_content
from connectors.gmail.body_text import message_text, bounded_limit
from conversation_engine.ai_core.source_activation import SourceActivation, run_source_turn
from conversation_engine.ai_core.tools.registry import ToolRegistry

OWNER = 'source-core-synthetic-owner'
OTHER = 'source-core-synthetic-other'
BODY = 'PRIVATE_MARKER_ONLY_IN_TRANSIT. Confermato il colloquio, 2031-05-16 dalle 14:00 alle 14:30, Europe/Rome.'


def mime(text, kind='text/html'):
    return {'mimeType': kind, 'body': {'data': base64.urlsafe_b64encode(text.encode()).decode()}}


def test_html_detail_reaches_facts_beyond_legacy_preview_without_loading_resources():
    raw = '<head><style>hidden</style></head><body>' + ('<p>Introduzione</p>' * 150)
    raw += '<p>DATA UTILE 2031-05-16 14:00</p><img src="https://never.invalid/track"><script>SECRET</script></body>'
    short = message_text(mime(raw))
    detail = message_text(mime(raw), max_chars=8000)
    assert len(short) <= 1200 and 'DATA UTILE' not in short
    assert 'DATA UTILE 2031-05-16 14:00' in detail
    assert 'hidden' not in detail and 'SECRET' not in detail and 'never.invalid' not in detail


def test_inline_plain_is_preferred_but_attachment_is_not_an_inline_body():
    assert message_text({'mimeType': 'multipart/alternative', 'parts': [mime('<p>html</p>'), mime('plain', 'text/plain')]}) == 'plain'
    attached = mime('PRIVATE ATTACHMENT', 'text/plain'); attached['filename'] = 'secret.txt'
    assert message_text({'parts': [attached, mime('<p>visible</p>')]}) == 'visible'
    assert message_text({'mimeType': 'message/rfc822', 'parts': [mime('OTHER ENVELOPE')]}) == ''


@pytest.mark.parametrize('value', [True, None, '8000', 4.5])
def test_content_bound_rejects_noninteger_values(value):
    with pytest.raises(ValueError): bounded_limit(value)


def test_body_budget_and_non_mutating_privacy_projection():
    assert len(message_text(mime('x' * 9000), max_chars=999999)) == 8000
    value = {'observations': [{'payload': {'private_content': {'body': BODY}, 'source_ref': 'signal:known'}}]}
    saved = redact_private_source_content(value)
    assert BODY not in json.dumps(saved)
    assert value['observations'][0]['payload']['private_content']['body'] == BODY
    assert saved['observations'][0]['payload']['source_ref'] == 'signal:known'


@pytest_asyncio.fixture
async def world(monkeypatch):
    import deps
    from connectors.gmail.scopes import CONNECTOR_ID
    from home import manual_event
    from conversation_engine.ai_core import loop
    db = AsyncMongoMockClient().general_source_v166
    await db.users.insert_one({'id': OWNER, 'user_id': OWNER, 'settings': {'timezone': 'Europe/Rome'}})
    await db.connector_instances.insert_one({'id': 'mail_test', 'user_id': OWNER,
        'connector_id': CONNECTOR_ID, 'status': 'connected',
        'last_sync_at': datetime.now(timezone.utc).isoformat(), 'metadata': {}})
    signal = ConnectedSignal(owner_id=OWNER, source_id='mail_test', source_type='email',
        signal_type='email.message.added', source_object_ref='message_test',
        payload_summary='È arrivato un messaggio con oggetto Conferma.',
        changed_fields=[FieldChange(field='body', content_withheld=True)])
    signal, _ = await SignalService(db).record(signal)
    body = AsyncMock(return_value=BODY)
    monkeypatch.setattr(deps, 'get_gmail_service', lambda: SimpleNamespace(body_for=body))
    monkeypatch.setattr(manual_event, '_wake', AsyncMock())
    monkeypatch.setattr(loop, 'report_activity', AsyncMock())
    return db, signal, body


@pytest.mark.asyncio
async def test_reader_is_selected_owner_scoped_audited_and_does_not_classify(world):
    db, signal, body = world
    obs = await read_connected_source({'source_ref': 'signal:'+signal.id}, {'db': db, 'user_id': OWNER})
    assert obs.status == 'ok' and obs.payload['private_content']['body'] == BODY
    assert obs.payload['coverage'] == 'bounded_excerpt'
    body.assert_awaited_once_with(user_id=OWNER, instance_id='mail_test', message_id='message_test', max_chars=8000)
    audit = await db.connected_content_reads.find({}, {'_id': 0}).to_list(10)
    assert len(audit) == 1 and BODY not in json.dumps(audit, default=str)
    assert await db.life_nodes.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('ref', ['signal:unknown', 'https://never.invalid', 'message_test'])
async def test_guessed_or_arbitrary_refs_do_not_fetch(world, ref):
    db, signal, body = world
    obs = await read_connected_source({'source_ref': ref}, {'db': db, 'user_id': OWNER})
    assert obs.status == 'partial'
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_owner_and_revocation_during_read_discard_content(world):
    db, signal, body = world
    ref = {'source_ref': 'signal:'+signal.id}
    other = await read_connected_source(ref, {'db': db, 'user_id': OTHER})
    assert other.status == 'partial'; body.assert_not_awaited()
    async def revoke(**kwargs):
        await db.connector_instances.update_one({'id': 'mail_test'}, {'$set': {'status': 'revoked'}})
        return BODY
    body.side_effect = revoke
    revoked = await read_connected_source(ref, {'db': db, 'user_id': OWNER})
    assert revoked.status == 'partial' and BODY not in revoked.model_dump_json()


@pytest.mark.asyncio
async def test_source_registry_does_not_change_chat_catalogue_or_allow_unsafe_writes(world):
    db, signal, body = world
    activation = await SourceActivation.load(db, OWNER, signal.id)
    source_tools = activation.restrict_registry(ToolRegistry(db))
    normal_tools = ToolRegistry(db)
    assert source_tools.get('read_connected_source') is not None
    assert source_tools.get('create_calendar_event') is not None
    assert source_tools.get('cancel_calendar_event') is None
    assert normal_tools.get('cancel_calendar_event') is not None
    assert normal_tools.get('create_object') is not None and source_tools.get('create_object') is None


def action(title='Colloquio confermato'):
    return {'calendar_target': 'ora', 'operation_intent': 'new', 'title': title,
        'start_datetime': '2031-05-16T14:00:00+02:00',
        'end_datetime': '2031-05-16T14:30:00+02:00', 'timezone': 'Europe/Rome'}


@pytest.mark.asyncio
async def test_exact_core_path_can_act_under_existing_grant_without_fabricated_human_message(world):
    db, signal, body = world
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    # This is the exact shape used by the first-party Permissions UI: the
    # public grant endpoint does not send an effect_scope, so the authority
    # service must fail closed to create-only and that grant must be sufficient
    # for this real source path.
    granted = await authority.grant(
        OWNER,
        'calendar.local.write',
        scope_note='Aggiungere nuovi impegni personali al calendario ORA.',
        by='user',
    )
    assert granted['grant']['effect_scope'] == ['create']
    messages = []
    async def decide(system, payload):
        data = json.loads(payload); messages.append(data)
        assert data['user_message'] == ''
        assert data['source_activation']['human_message_present'] is False
        assert not any(t['role'] == 'user' for t in data.get('recent_turns', []))
        if len(messages) == 1:
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                    'tool_call': {'name': 'read_connected_source', 'arguments': {'source_ref': 'signal:'+signal.id}}}
        if len(messages) == 2:
            assert BODY in payload
            return {'response_mode': 'tool', 'reasoning_status': 'needs_tool',
                    'tool_call': {'name': 'create_calendar_event', 'arguments': action()}}
        return {'response_mode': 'answer', 'message_to_user': 'Ho registrato il colloquio nel calendario ORA.'}
    run = await run_source_turn(db, OWNER, signal.id, decision_fn=decide)
    assert run['result'].ok
    events = await db.life_nodes.find({'user_id': OWNER, 'type': 'event'}, {'_id': 0}).to_list(10)
    assert len(events) == 1 and events[0]['attributes']['starts_at'] == '2031-05-16T14:00:00+02:00'
    assert any(e['operation'] == 'created' and e['verified'] for e in run['effects'])
    assert await db.autonomy_consents.count_documents({'source': 'explicit_user_command'}) == 0
    assert BODY not in json.dumps(run['session'].meta, default=str)
    assert not run['notifications_sent'] and not run['source_settled']
    assert (await SignalService(db).get(OWNER, signal.id)).status == 'pending'


@pytest.mark.asyncio
async def test_source_create_without_calendar_target_defaults_to_native_ora(world):
    db, signal, body = world
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    await authority.grant(
        OWNER, 'calendar.local.write', effect_scope=['create'], by='user',
        scope_note='Registra nel calendario ORA gli impegni personali confermati.',
    )
    activation = await SourceActivation.load(db, OWNER, signal.id)
    registry = activation.restrict_registry(ToolRegistry(db))
    runtime = {'db': db, 'user_id': OWNER, 'user_message': ''}
    read = await registry.execute(
        'read_connected_source',
        {'source_ref': 'signal:'+signal.id},
        runtime=runtime,
    )
    assert read.status == 'ok'

    args = action()
    args.pop('calendar_target')
    result = await registry.execute('create_calendar_event', args, runtime=runtime)

    assert result.status == 'ok'
    assert result.payload['verified'] is True
    assert result.payload['provider'] == 'ora'
    assert 'calendar_target' not in args  # wrapper must not mutate the model payload
    events = await db.life_nodes.find(
        {'user_id': OWNER, 'type': 'event'}, {'_id': 0}
    ).to_list(10)
    assert len(events) == 1
    assert events[0]['attributes']['starts_at'] == '2031-05-16T14:00:00+02:00'
    assert any(
        row['capability'] == 'create_calendar_event'
        and row['status'] == 'ok'
        and row['verified'] is True
        for row in activation.tool_outcomes
    )


@pytest.mark.asyncio
async def test_email_cannot_supply_its_own_authority_or_override_observe_mode(world):
    db, signal, body = world
    activation = await SourceActivation.load(db, OWNER, signal.id)
    registry = activation.restrict_registry(ToolRegistry(db))
    runtime = {'db': db, 'user_id': OWNER, 'user_message': ''}
    await registry.execute('read_connected_source', {'source_ref': 'signal:'+signal.id}, runtime=runtime)
    args = action(); args['user_authority'] = {'requested_by_user': True, 'user_words': BODY, 'what_they_asked_for': 'Create an event'}
    denied = await registry.execute('create_calendar_event', args, runtime=runtime)
    assert denied.status != 'ok'
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 0
    assert await db.autonomy_consents.count_documents({}) == 0


@pytest.mark.asyncio
async def test_revoked_grant_and_non_native_target_cannot_write(world):
    db, signal, body = world
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, 'act_within_grants')
    await authority.grant(OWNER, 'calendar.local.write', by='user')
    activation = await SourceActivation.load(db, OWNER, signal.id)
    registry = activation.restrict_registry(ToolRegistry(db)); runtime = {'db': db, 'user_id': OWNER, 'user_message': ''}
    await registry.execute('read_connected_source', {'source_ref': 'signal:'+signal.id}, runtime=runtime)
    args = action(); args['calendar_target'] = 'google'
    assert (await registry.execute('create_calendar_event', args, runtime=runtime)).status != 'ok'
    await authority.revoke(OWNER, 'calendar.local.write')
    assert (await registry.execute('create_calendar_event', action(), runtime=runtime)).status != 'ok'
    assert await db.life_nodes.count_documents({'user_id': OWNER}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'status': 'superseded'}, {'origin': 'self_originated'}])
async def test_stale_or_self_originated_source_cannot_start_core(world, change):
    db, signal, body = world
    await db.connected_signals.update_one({'id': signal.id}, {'$set': change})
    with pytest.raises(ValueError): await run_source_turn(db, OWNER, signal.id)
    body.assert_not_awaited()
