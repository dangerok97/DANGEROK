"""In-app voice keeps one conversation and yields promptly when audio fails."""
import asyncio
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from voice import providers
from conversation_engine.models import StartBody, MessageBody
from conversation_engine.ai_core.prompt import build_user_payload
from test_post_call_application_v315 import FintoDb, _combacia


@pytest.fixture(autouse=True)
def circuits(monkeypatch):
    monkeypatch.setattr(providers, '_last_failure', 0.0)
    monkeypatch.setattr(providers, '_provider_failures', {})
    monkeypatch.setattr(providers, '_gemini_key_failures', {})


@pytest.mark.asyncio
async def test_stuck_provider_is_cancelled_and_fallback_is_remembered(monkeypatch):
    events = []
    class Slow:
        name = 'slow'
        def is_available(self): return True
        async def speak(self, text, **kwargs):
            events.append('slow')
            try: await asyncio.Event().wait()
            finally: events.append('cancelled')
    class Working:
        name = 'working'
        def is_available(self): return True
        async def speak(self, text, **kwargs):
            events.append('working')
            return providers.Spoken(b'audio', 'audio/mpeg', 'stock', self.name)
    monkeypatch.setattr(providers, '_ORDER', (Slow, Working))
    monkeypatch.setattr(providers, 'TIMEOUT_S', .01)
    assert (await providers.say_it('Prima frase')).provider == 'working'
    assert (await providers.say_it('Seconda frase')).provider == 'working'
    assert events == ['slow', 'cancelled', 'working', 'working']


@pytest.mark.asyncio
async def test_total_failure_does_not_restart_the_same_failed_chain(monkeypatch):
    calls = []
    class Broken:
        name = 'broken'
        def is_available(self): return True
        async def speak(self, text, **kwargs): calls.append(text)
    monkeypatch.setattr(providers, '_ORDER', (Broken,))
    assert await providers.say_it('Uno') is None
    assert await providers.say_it('Due') is None
    assert calls == ['Uno']


@pytest.mark.asyncio
async def test_cancelling_audio_does_not_start_another_provider(monkeypatch):
    entered = asyncio.Event()
    calls = []
    class Slow:
        name = 'slow'
        def is_available(self): return True
        async def speak(self, text, **kwargs):
            entered.set()
            await asyncio.Event().wait()
    class Unwanted:
        name = 'unwanted'
        def is_available(self): return True
        async def speak(self, text, **kwargs): calls.append(text)
    monkeypatch.setattr(providers, '_ORDER', (Slow, Unwanted))
    task = asyncio.create_task(providers.say_it('Interrotta'))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not calls
    assert not providers._provider_failures


def test_voice_style_changes_form_and_keeps_tools_and_evidence():
    common = dict(user_message='Quando parto?', recent_turns=[], active_goal=None,
                  context_facts=[{'source': 'calendar', 'value': 'domani'}],
                  tools=[], observations=[{'name': 'calendar', 'status': 'ok'}])
    written = json.loads(build_user_payload(**common))
    spoken = json.loads(build_user_payload(**common, spoken_out_loud=True, in_app_voice=True))
    telephone = json.loads(build_user_payload(**common, spoken_out_loud=True))
    assert 'voice_presence' not in written and 'voice_presence' not in telephone
    assert 'JARVIS' in spoken['voice_presence']
    assert 'Non scherzare' in spoken['voice_presence']
    assert 'you_are_being_heard_not_read' in spoken
    for key in ('observations', 'context_facts', 'user_message'):
        assert spoken[key] == written[key]
    assert StartBody(text='x').response_channel == 'text'
    assert MessageBody(text='x').response_channel == 'text'
    with pytest.raises(ValidationError): MessageBody(text='x', response_channel='execute')


@pytest.mark.asyncio
async def test_switching_text_and_voice_keeps_session_and_navigation(monkeypatch):
    import conversation_engine.ai_core.orchestrator as mod
    from conversation_engine.ai_core.models import CognitiveTurnResult
    db = FintoDb()
    table = db['conversation_sessions']
    seen = []
    async def replace_one(query, document):
        for i, row in enumerate(table.righe):
            if _combacia(row, query):
                table.righe[i] = deepcopy(document)
                return
        raise AssertionError('unknown session')
    table.replace_one = replace_one
    async def run(**kwargs):
        sess = kwargs['sess']
        seen.append((sess.id, sess.meta['entry_point'], sess.meta['response_channel']))
        return CognitiveTurnResult(mode='answer', ora_text='Ci sono.')
    monkeypatch.setattr(mod, 'run_cognitive_loop', run)
    orch = mod.AICoreOrchestrator(db)
    first = await orch.start('owner', text='Ciao', origin='voice', entry_point='ora', response_channel='voice')
    sid = first['session_id']
    await orch.message('owner', sid, text='Ora scrivo', client_message_id='two')
    await orch.message('owner', sid, text='Ora parlo', client_message_id='three', response_channel='voice')
    await orch.client_resume('owner', sid, completed=[])
    assert seen == [(sid, 'ora', mode) for mode in ('voice', 'text', 'voice', 'voice')]


def test_provider_diagnostics_do_not_expose_error_details():
    from types import SimpleNamespace
    assert providers._error_status(SimpleNamespace(code=429, message="private")) == 429
    assert providers._error_status(SimpleNamespace(code="private")) == 0
    assert providers._error_status(SimpleNamespace(response=SimpleNamespace(status_code=401))) == 401


@pytest.mark.asyncio
async def test_failed_gemini_account_is_skipped_until_cooldown_expires(monkeypatch):
    from google import genai
    from types import SimpleNamespace
    calls, closed = [], []
    recovered = False
    class NoCredit(Exception):
        code = 402
    class Client:
        def __init__(self, api_key):
            self.key = api_key
            self.aio = SimpleNamespace(models=self, aclose=self.close)
        async def generate_content(self, **kwargs):
            calls.append(self.key)
            if self.key == 'first-fixture' and not recovered:
                raise NoCredit()
            return object()
        async def close(self): closed.append(self.key)
    monkeypatch.setenv('GEMINI_API_KEY', 'first-fixture')
    monkeypatch.setenv('GEMINI2_API_KEY', 'second-fixture')
    monkeypatch.setattr(genai, 'Client', Client)
    monkeypatch.setattr(providers, '_first_audio', lambda answer: b'\x00\x01' * 10)
    for words in ('Uno', 'Due'):
        assert (await providers.GeminiSpeech().speak(words)).provider == 'gemini'
    assert calls == ['first-fixture', 'second-fixture', 'second-fixture']
    assert closed == calls
    assert set(providers._gemini_key_failures) == {'GEMINI_API_KEY'}
    recovered = True
    providers._gemini_key_failures['GEMINI_API_KEY'] = 0
    assert await providers.GeminiSpeech().speak('Tre')
    assert calls[-1] == 'first-fixture'
    assert not providers._gemini_key_failures
