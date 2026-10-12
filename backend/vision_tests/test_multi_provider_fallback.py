import pytest
import vision_provider as provider
import vision_openai_fallback as fallback

@pytest.mark.asyncio
async def test_primary_success_skips_secondary(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secondary")
    async def success(*args, **kwargs): return {"recognized": True}
    async def forbidden(*args, **kwargs): raise AssertionError("unneeded fallback")
    monkeypatch.setattr(provider, "ask_gemini_json", success)
    monkeypatch.setattr(fallback, "ask_openai", forbidden)
    assert (await provider.ask_json("system", "prompt", b"image"))["recognized"]

@pytest.mark.asyncio
async def test_secondary_recovers_from_primary_quota(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secondary")
    monkeypatch.setattr(provider, "_FALLBACK_COOLDOWN", {})
    async def quota(*args, **kwargs):
        raise provider.VisionProviderError("provider_quota")
    async def success(*args, **kwargs): return {"recognized": True}
    monkeypatch.setattr(provider, "ask_gemini_json", quota)
    monkeypatch.setattr(fallback, "ask_openai", success)
    assert (await provider.ask_json("system", "prompt", b"image"))["recognized"]

@pytest.mark.asyncio
async def test_secondary_quota_is_not_retried_immediately(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI2_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only-secondary")
    monkeypatch.setattr(provider, "_FALLBACK_COOLDOWN", {})
    calls = []
    async def quota(*args, **kwargs):
        calls.append(1)
        raise provider.VisionProviderError("provider_quota")
    monkeypatch.setattr(fallback, "ask_openai", quota)
    for _ in range(2):
        with pytest.raises(provider.VisionProviderError):
            await provider.ask_json("system", "prompt", b"image")
    assert len(calls) == 1
