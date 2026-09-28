"""Selecting OpenAI for one person must not redirect other people's turns."""
from types import SimpleNamespace

import pytest

from llm import manager
from llm.base import LLMResult
from llm.router import LLMPreferenceIn, patch_llm_preference
from conversation_engine.ai_core.loop import _call_ai, _user_llm_preference


class Users:
    def __init__(self):
        self.preferences = {}

    async def update_one(self, selector, update):
        self.preferences[selector["user_id"]] = update["$set"]["preferences.llm_provider"]

    async def find_one(self, selector, projection):
        preference = self.preferences.get(selector["user_id"])
        return {"preferences": {"llm_provider": preference}} if preference else None


@pytest.mark.asyncio
async def test_setting_one_users_openai_preference_does_not_mutate_process_preference(monkeypatch):
    import llm.router as router

    users = Users()
    monkeypatch.setattr(router, "db", SimpleNamespace(users=users))
    previous = manager.get_runtime_preferred()
    manager.set_runtime_preferred(None)
    try:
        await patch_llm_preference(LLMPreferenceIn(provider="openai"), {"user_id": "person_a"})
        assert users.preferences == {"person_a": "openai"}
        assert manager.get_runtime_preferred() is None
    finally:
        manager.set_runtime_preferred(previous)


@pytest.mark.asyncio
async def test_ai_core_forwards_only_current_users_preference(monkeypatch):
    calls = []

    async def chat(**kwargs):
        calls.append(kwargs)
        return LLMResult(text='{"ok":true}', provider="openai", model="synthetic")

    monkeypatch.setattr(manager, "get_manager", lambda: SimpleNamespace(chat=chat))
    assert await _call_ai(decision_fn=None, system="s", user="u", user_preference="openai") == {"ok": True}
    assert await _call_ai(decision_fn=None, system="s", user="u", user_preference=None) == {"ok": True}
    assert [call["user_preference"] for call in calls] == ["openai", None]


@pytest.mark.asyncio
async def test_preference_is_fetched_for_one_user_and_absent_for_another():
    users = Users()
    users.preferences["person_a"] = "openai"
    db = SimpleNamespace(users=users)
    assert await _user_llm_preference(db, "person_a") == "openai"
    assert await _user_llm_preference(db, "person_b") is None
