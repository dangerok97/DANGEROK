"""Tests only; no live credentials or billable traffic."""
import json
import httpx
import pytest
import vision_provider as provider


@pytest.mark.asyncio
async def test_payment_failure_blocks_same_credential_across_models(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-unpaid")
    monkeypatch.setenv("GEMINI2_API_KEY", "synthetic-working")
    monkeypatch.setenv("ORA_VISION_MODELS", "model-a,model-b")
    monkeypatch.setattr(provider, "_BACKOFF", {})
    monkeypatch.setattr(provider, "_PREFERRED", None)
    attempts = []
    def answer(req):
        key = req.headers["x-goog-api-key"]
        attempts.append((req.url.path, key))
        if key == "synthetic-unpaid":
            return httpx.Response(402)
        return httpx.Response(200, json={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":json.dumps({"recognized": True})}]}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        assert (await provider.ask_json("sys","prompt",b"photo",client=client))["recognized"]
        assert len([p for p in attempts if p[1] == "synthetic-unpaid"]) == 1
        initial = len(attempts)
        assert (await provider.ask_json("sys","prompt",b"photo",client=client))["recognized"]
        assert len(attempts) == initial + 1


@pytest.mark.asyncio
async def test_both_unpaid_report_quota_without_repeated_requests(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "unpaid-a")
    monkeypatch.setenv("GEMINI2_API_KEY", "unpaid-b")
    monkeypatch.setenv("ORA_VISION_MODELS", "model-a,model-b")
    monkeypatch.setattr(provider, "_BACKOFF", {})
    monkeypatch.setattr(provider, "_PREFERRED", None)
    calls = []
    def deny(req):
        calls.append(req.url.path)
        return httpx.Response(402)
    async with httpx.AsyncClient(transport=httpx.MockTransport(deny)) as client:
        with pytest.raises(provider.VisionProviderError) as exc:
            await provider.ask_json("sys","prompt",b"photo",client=client)
        assert exc.value.code == "provider_quota"
        assert len(calls) == 2
        with pytest.raises(provider.VisionProviderError) as retry:
            await provider.ask_json("sys","prompt",b"photo",client=client)
        assert retry.value.code == "provider_quota"
        assert len(calls) == 2
