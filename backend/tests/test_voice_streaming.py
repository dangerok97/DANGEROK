import asyncio
from contextlib import aclosing
from types import SimpleNamespace as Obj

import pytest

from voice import streaming as mod


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(mod, '_blocked', {})
    monkeypatch.setenv('GEMINI2_API_KEY', 'second-fixture')
    monkeypatch.setenv('GEMINI_API_KEY', 'first-fixture')


@pytest.mark.asyncio
async def test_first_audio_is_yielded_before_generation_finishes(monkeypatch):
    finish = asyncio.Event()
    closed = []
    async def pcm(*args):
        try:
            yield b'\x00\x01'
            await finish.wait()
            yield b'\x02\x03'
        finally: closed.append(True)
    monkeypatch.setattr(mod, '_pcm', pcm)
    async with aclosing(mod.speech_events('Testo già deciso.')) as events:
        first = await asyncio.wait_for(anext(events), .2)
        assert first['type'] == 'audio' and first['encoding'] == 'pcm_s16le'
        assert not finish.is_set() and not closed
        finish.set()
        assert (await anext(events))['type'] == 'audio'
        assert await anext(events) == {'type': 'done'}
    assert closed == [True]


@pytest.mark.asyncio
async def test_partial_audio_failure_never_restarts_on_second_key(monkeypatch):
    calls = []
    async def pcm(text, key, *args):
        calls.append(key)
        yield b'\x01\x00'
        raise RuntimeError('private upstream detail')
    monkeypatch.setattr(mod, '_pcm', pcm)
    events = [e async for e in mod.speech_events('Prima frase.')]
    assert [e['type'] for e in events] == ['audio', 'error']
    assert calls == ['second-fixture']
    assert 'private' not in str(events)


@pytest.mark.asyncio
async def test_unavailable_slot_is_skipped_and_recovers(monkeypatch):
    calls = []
    class Unavailable(Exception): code = 429
    async def pcm(text, key, *args):
        calls.append(key)
        if key == 'second-fixture': raise Unavailable()
        yield b'\x01\x00'
    monkeypatch.setattr(mod, '_pcm', pcm)
    for _ in range(2):
        assert [e async for e in mod.speech_events('Ciao.')][-1] == {'type': 'done'}
    assert calls == ['second-fixture', 'first-fixture', 'first-fixture']
    mod._blocked.clear()
    assert [e async for e in mod.speech_events('Ciao.')][-1]['type'] == 'done'
    assert calls[-2:] == ['second-fixture', 'first-fixture']


@pytest.mark.asyncio
async def test_disconnect_closes_generation_without_fallback(monkeypatch):
    entered = asyncio.Event()
    closed = []
    async def pcm(*args):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield b'never'
        finally: closed.append(True)
    monkeypatch.setattr(mod, '_pcm', pcm)
    events = mod.speech_events('Ciao.')
    task = asyncio.create_task(anext(events))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert closed == [True] and not mod._blocked
    await events.aclose()


@pytest.mark.asyncio
async def test_sdk_keeps_text_and_stock_voice_and_rejects_truncated_output(monkeypatch):
    from google import genai
    seen, closed = [], []
    finish = 'STOP'
    class Client:
        def __init__(self, **kwargs): self.aio = Obj(models=self, aclose=self.close)
        async def close(self): closed.append(True)
        async def generate_content_stream(self, **kwargs):
            seen.append(kwargs)
            async def replies():
                yield Obj(candidates=[Obj(finish_reason=finish, content=Obj(parts=[
                    Obj(inline_data=Obj(data=b'\x01\x00', mime_type='audio/L16;rate=24000'))]))])
            return replies()
    monkeypatch.setattr(genai, 'Client', Client)
    assert [x async for x in mod._pcm('Esattamente queste parole.', 'fixture', 'tts', 'Algieba')] == [b'\x01\x00']
    assert seen[0]['contents'].endswith('Testo:\nEsattamente queste parole.')
    assert seen[0]['config'].speech_config.voice_config.prebuilt_voice_config.voice_name == 'Algieba'
    finish = 'OTHER'
    with pytest.raises(RuntimeError, match='incomplete_speech'):
        _ = [x async for x in mod._pcm('Ciao.', 'fixture', 'tts', 'Algieba')]
    assert closed == [True, True]


@pytest.mark.asyncio
async def test_stream_endpoint_requires_auth_and_does_not_cache(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from voice.router import router
    from deps import get_current_user
    app = FastAPI()
    app.include_router(router, prefix='/api')
    async def events(text):
        yield {'type': 'audio', 'data': 'AQA=', 'sample_rate': 24000, 'encoding': 'pcm_s16le'}
        yield {'type': 'done'}
    monkeypatch.setattr(mod, 'speech_events', events)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        assert (await client.post('/api/voice/stream', json={'text': 'Ciao.'})).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: {'user_id': 'synthetic'}
        answer = await client.post('/api/voice/stream', json={'text': 'Ciao.'})
        assert answer.status_code == 200
        assert answer.headers['Cache-Control'] == 'no-store, no-transform'
        assert len(answer.text.splitlines()) == 2
        assert (await client.post('/api/voice/stream', json={'text': 'x'*4001})).status_code == 422
