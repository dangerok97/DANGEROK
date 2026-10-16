"""The autonomous source-to-Core lane must not starve polling or other owners.

Synthetic owners only; no real mailbox, model, account, or notification.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ambient import runtime
from connected import polling


@pytest.mark.asyncio
async def test_background_source_sync_does_not_enter_slow_core(monkeypatch):
    read = AsyncMock(return_value={
        "looked_at": 1, "read": 1, "failed": 0,
        "understood": 0, "noise": 0,
    })
    monkeypatch.setattr(polling, "poll_once", read)
    result = await runtime.read_sources(SimpleNamespace())
    assert result["read"] == 1
    assert read.await_args.kwargs["interpret"] is False


@pytest.mark.asyncio
async def test_reasoning_owner_selection_rotates_instead_of_repeating_first(monkeypatch):
    class Signals:
        def __init__(self):
            self.queries = []

        async def distinct(self, field, query):
            self.queries.append((field, query))
            return ["owner-c", "owner-a", "owner-b"]

    signals = Signals()
    db = SimpleNamespace(connected_signals=signals)
    monkeypatch.setattr(polling, "_last_understand_owner", None)
    observed = []
    for _ in range(5):
        selected = await polling._owners_with_something_to_understand(db, limit=1)
        observed.append(selected[0])
    assert observed == ["owner-a", "owner-b", "owner-c", "owner-a", "owner-b"]
    assert all(query["status"] == "pending" for _, query in signals.queries)
    assert all("_supersession_pending" in query for _, query in signals.queries)


@pytest.mark.asyncio
async def test_reasoning_lane_handles_only_one_owner_and_one_signal(monkeypatch):
    selected = AsyncMock(return_value=["synthetic-owner"])
    monkeypatch.setattr(polling, "_owners_with_something_to_understand", selected)
    calls = []

    class FakeConnectedLife:
        def __init__(self, db):
            assert db is not None

        async def interpret(self, owner_id, *, limit):
            calls.append((owner_id, limit))
            return {"passed_on": 1, "noise": 0}

    from connected import service
    monkeypatch.setattr(service, "ConnectedLifeService", FakeConnectedLife)
    result = await polling.interpret_due(SimpleNamespace())
    assert calls == [("synthetic-owner", 1)]
    assert result == {"looked_at": 1, "understood": 1, "noise": 0}
    assert selected.await_args.kwargs["limit"] == 1


@pytest.mark.asyncio
async def test_ambient_runtime_gives_core_longer_than_source_poll(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "_a_call_is_live", lambda: False)
    monkeypatch.setattr(runtime, "_launch", lambda name, operation, *, timeout:
                        calls.append((name, timeout)) or True)
    await runtime._cycle(SimpleNamespace(), 1)
    times = dict(calls)
    assert times["sources"] == 120
    assert times["source-understanding"] == 220
    assert times["source-understanding"] > polling.TICK_BUDGET_SECONDS
