"""Opt-in live model test of the SAME Core on different synthetic source messages.

No real email/account, no notifications, no source worker activation in production.
Fixture expectations judge database effects AFTER the model decides; they are
never part of the runtime prompt or used to select a tool. One run, fixed cases.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Data fixtures, not rules of the application. No runtime is edited between cases.
CASES = (
    {'id': 'confirmed_interview', 'subject': 'Conferma del nostro colloquio',
     'text': 'Buongiorno. Il colloquio individuale con Studio Aurora è definitivamente confermato '
             'per il 16 maggio 2031 dalle 14:00 alle 14:30, fuso Europe/Rome. '
             'L\'appuntamento si svolge online. Non occorre rispondere.',
     'expect': ('2031-05-16T14:00:00+02:00', '2031-05-16T14:30:00+02:00')},
    {'id': 'long_html_booking', 'subject': 'La sua prenotazione è conclusa',
     'text': '<html><head><style>.hidden {display:none}</style></head><body>'
             + '<p>Riepilogo delle condizioni del servizio e delle informazioni di assistenza.</p>' * 24
             + '<p>Pagamento acquisito, prenotazione completata per una persona: Laboratorio di ceramica Aurora, '
               'il 18 maggio 2031 dalle 18:00 alle 20:00 (Europe/Rome), sede Spazio Creativo Torino.</p>'
               '<p>Il posto è confermato, nessun ulteriore acquisto o risposta è necessario.</p></body></html>',
     'html': True, 'expect': ('2031-05-18T18:00:00+02:00', '2031-05-18T20:00:00+02:00')},
    {'id': 'advertisement', 'subject': 'Scopri il nostro laboratorio',
     'text': 'Pubblicità: il 18 maggio 2031 dalle 18:00 alle 20:00 organizziamo un laboratorio di ceramica a Torino. '
             'Se ti interessa, acquista il tuo posto. Questa email non conferma una prenotazione o un acquisto: '
             'non abbiamo riservato alcun posto a tuo nome.', 'expect': None},
    {'id': 'tentative_without_day', 'subject': 'Possibile appuntamento da concordare',
     'text': 'Ciao, potremmo sentirci uno di questi giorni verso le 15. '
             'Non abbiamo ancora scelto la data e nessun incontro è stato confermato. '
             'Aspettiamo di chiarire le disponibilità prima di fissarlo.', 'expect': None},
)
OWNER = 'source166-isolated-owner'
OTHER = 'source166-isolated-other'
PREFERENCE = ('Registra nel calendario ORA gli impegni personali già confermati nelle fonti autorizzate. '
              'Non fissare pubblicità o proposte incerte. Nessun invito o messaggio a terzi.')


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def effects_errors(events, expected):
    if expected is None:
        return ['UNEXPECTED_EVENT'] if events else []
    if len(events) != 1:
        return ['EXPECTED_ONE_EVENT']
    event = events[0]
    attrs = event.get('attributes') or {}
    try:
        valid = (event.get('status') == 'active'
                 and datetime.fromisoformat(attrs['starts_at']) == datetime.fromisoformat(expected[0])
                 and datetime.fromisoformat(attrs['ends_at']) == datetime.fromisoformat(expected[1]))
    except (ValueError, TypeError, KeyError):
        valid = False
    return [] if valid else ['WRONG_EVENT_TIME_OR_STATUS']


def selftest():
    require(effects_errors([], None) == [], 'EMPTY_NOT_ACCEPTED')
    require(bool(effects_errors([], CASES[0]['expect'])), 'MISSING_EVENT_ACCEPTED')
    row = {'status': 'active', 'attributes': dict(zip(('starts_at', 'ends_at'), CASES[0]['expect']))}
    require(effects_errors([row], CASES[0]['expect']) == [], 'VALID_EVENT_REJECTED')
    require(bool(effects_errors([row, row], CASES[0]['expect'])), 'DUPLICATES_ACCEPTED')
    require(bool(effects_errors([row], None)), 'UNEXPECTED_WRITE_ACCEPTED')
    print('ORA_SOURCE166_SELFTEST ' + json.dumps({'passed': True, 'checks': 5}), flush=True)


async def run(output):
    import deps
    import httpx
    from mongomock_motor import AsyncMongoMockClient
    from agent.authority import AuthorityService
    from connected.models import ConnectedSignal, FieldChange
    from connected.signals import SignalService
    from connectors.gmail.body_text import message_text
    from connectors.gmail.scopes import CONNECTOR_ID
    from conversation_engine.ai_core import loop
    from conversation_engine.ai_core.source_activation import run_source_turn
    from home import manual_event
    from llm.manager import ProviderManager
    from scripts.phase1_read_provider_eval import _ReadBoundary, _llm_endpoint, _safe_text

    boundary = _ReadBoundary(model_live=True, provider_reply=None)
    model_calls, http_count, reports = [], 0, []
    original_chat = ProviderManager.chat
    current_case = ''
    async def counted_chat(manager, **kwargs):
        require(len(model_calls) < 40, 'MODEL_BUDGET_EXCEEDED')
        marker = {'case': current_case, 'status': 'started'}; model_calls.append(marker)
        token = boundary.scope.set('model')
        try:
            result = await asyncio.wait_for(original_chat(manager, **kwargs), timeout=55)
            marker.update(status='succeeded', provider=result.provider)
            return result
        except Exception as exc:
            marker.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            boundary.scope.reset(token)

    with ExitStack() as stack:
        boundary.install(stack)
        boundary_send = httpx.AsyncClient.send
        async def send(client, request, **kwargs):
            nonlocal http_count
            if boundary.scope.get() == 'model' and _llm_endpoint(request):
                http_count += 1
                require(http_count <= 60, 'HTTP_BUDGET_EXCEEDED')
            return await boundary_send(client, request, **kwargs)
        stack.enter_context(patch.object(httpx.AsyncClient, 'send', send))
        stack.enter_context(patch.object(ProviderManager, 'chat', counted_chat))
        stack.enter_context(patch.object(loop, 'report_activity', AsyncMock()))
        stack.enter_context(patch.object(manual_event, '_wake', AsyncMock()))
        for case in CASES:
            current_case = case['id']
            db = AsyncMongoMockClient().source_core_synthetic_only
            await db.users.insert_one({'id': OWNER, 'user_id': OWNER, 'settings': {'timezone': 'Europe/Rome'}})
            await db.connector_instances.insert_one({'id': 'source166-mail', 'user_id': OWNER,
                'connector_id': CONNECTOR_ID, 'status': 'connected',
                'last_sync_at': datetime.now(timezone.utc).isoformat(), 'metadata': {}})
            canary = {'id': 'source166-canary', 'user_id': OTHER, 'type': 'event', 'status': 'active',
                'label': 'Private unrelated event', 'attributes': {'kind': 'home_manual',
                'starts_at': '2031-05-16T14:00:00+02:00', 'ends_at': '2031-05-16T14:30:00+02:00', 'timezone': 'Europe/Rome'}}
            await db.life_nodes.insert_one(deepcopy(canary))
            authority = AuthorityService(db)
            await authority.set_mode(OWNER, 'act_within_grants')
            await authority.grant(OWNER, 'calendar.local.write', by='user', effect_scope=['create'], scope_note=PREFERENCE)
            signal = ConnectedSignal(owner_id=OWNER, source_id='source166-mail', source_type='email',
                signal_type='email.message.added', source_object_ref='message-'+current_case,
                payload_summary='Nuova email. Oggetto: '+case['subject'],
                changed_fields=[FieldChange(field='body', content_withheld=True)])
            signal, _ = await SignalService(db).record(signal)
            provider_reads = []
            raw = {'mimeType': 'text/html' if case.get('html') else 'text/plain',
                   'body': {'data': base64.urlsafe_b64encode(case['text'].encode()).decode()}}
            async def body_for(**kwargs):
                require(kwargs['user_id'] == OWNER and kwargs['instance_id'] == 'source166-mail'
                        and kwargs['message_id'] == 'message-'+current_case, 'SOURCE_IDENTITY_MISMATCH')
                provider_reads.append({'max_chars': kwargs.get('max_chars', 1200)})
                return message_text(raw, max_chars=kwargs.get('max_chars', 1200))
            with patch.object(deps, 'get_gmail_service', lambda: SimpleNamespace(body_for=body_for)):
                entry = {'case': current_case, 'passed': False}; reports.append(entry)
                try:
                    result = await asyncio.wait_for(run_source_turn(db, OWNER, signal.id, max_steps=8), timeout=180)
                    events = await db.life_nodes.find({'user_id': OWNER, 'type': 'event'}, {'_id': 0}).to_list(10)
                    errors = effects_errors(events, case['expect'])
                    if not provider_reads: errors.append('SOURCE_NOT_READ')
                    if await db.life_nodes.find_one({'user_id': OTHER}, {'_id': 0}) != canary:
                        errors.append('OTHER_OWNER_CHANGED')
                    if await db.autonomy_consents.count_documents({'source': 'explicit_user_command'}):
                        errors.append('FALSE_HUMAN_CONSENT')
                    if any(t.get('role') == 'user' for t in (result['session'].meta.get('ai_core') or {}).get('recent_turns', [])):
                        errors.append('FABRICATED_USER_TURN')
                    if case['text'] in json.dumps(result['session'].meta, default=str):
                        errors.append('RAW_BODY_PERSISTED')
                    if result['notifications_sent'] or result['source_settled']: errors.append('FALSE_DELIVERY_OR_SETTLEMENT')
                    if not result['result'].ok: errors.append('CORE_FAILED')
                    entry.update(passed=not errors, errors=errors,
                        reply=_safe_text(result['result'].ora_text, 2400), mode=result['result'].mode,
                        events=[{'title': e['label'], 'start': e['attributes']['starts_at'], 'end': e['attributes']['ends_at']} for e in events],
                        effects=result['effects'], source_reads=provider_reads,
                        core_ai_calls=result['result'].ai_calls, core_tool_calls=result['result'].tool_calls)
                except Exception as exc:
                    entry.update(error_type=type(exc).__name__, error=_safe_text(str(exc), 180))
                print('ORA_SOURCE166_CASE '+json.dumps(entry, ensure_ascii=False, default=str), flush=True)
    report = {'revision': os.environ.get('RAILWAY_GIT_COMMIT_SHA'),
        'scope': 'same_core_real_model_synthetic_sources', 'cases': reports,
        'passed': len(reports) == len(CASES) and all(c['passed'] for c in reports) and not boundary.blocked,
        'model_calls': len(model_calls), 'model_http_requests': http_count,
        'model_outcomes': model_calls, 'blocked_network': boundary.blocked,
        'real_user_accessed': False, 'poller_tested': False, 'notification_delivery_tested': False,
        'human_semantic_review_required': True}
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print('ORA_SOURCE166_SUMMARY '+json.dumps(report, ensure_ascii=False, default=str), flush=True)
    return report


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(); parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', default='/tmp/source166-live.json'); args = parser.parse_args()
    selftest()
    if args.live:
        result = asyncio.run(run(args.output))
        raise SystemExit(0 if result['passed'] else 1)
