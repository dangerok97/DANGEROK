"""Cancellation/deadline regression with real async HTTP transport, no network."""
import asyncio
import json

import httpx
import pytest
import vision_provider as provider


@pytest.mark.asyncio
async def test_second_phase_skips_the_route_cancelled_by_first_deadline(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-cancellation-key')
    monkeypatch.delenv('GEMINI2_API_KEY', raising=False)
    monkeypatch.setenv('ORA_VISION_MODELS', 'slow-test-model,fast-test-model')
    provider._BACKOFF.clear(); provider._PREFERRED = None
    attempts = []
    async def handler(request):
        name = request.url.path.split('/')[-1].split(':')[0]
        attempts.append(name)
        if name == 'slow-test-model':
            await asyncio.sleep(1)
        data = {'recognized': True, 'canonical_key': 'test_container'}
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(data)}]}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(provider.ask_json('test', 'test', client=client), timeout=.03)
        result = await provider.ask_json('test', 'test', client=client)
    assert result['recognized'] is True
    assert attempts == ['slow-test-model', 'fast-test-model']
    provider._BACKOFF.clear(); provider._PREFERRED = None
