"""First read, failure recovery and newly connected source discovery."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from connected.initial_sync import after_connect


def test_first_read_finishes_before_connect_returns_and_is_durably_queued():
    collection = SimpleNamespace(update_one=AsyncMock())
    db = MagicMock()
    db.__getitem__.return_value = collection
    async def read(**kwargs):
        assert collection.update_one.await_count == 1
        assert kwargs == {"user_id": "user", "instance_id": "calendar"}
        return {"totals": {"failed": 0, "received": 3}}
    result = asyncio.run(after_connect(db, user_id="user", instance_id="calendar", sync=read))
    assert result == {"ok": True, "retry_pending": False}
    assert collection.update_one.call_args.args[0] == {"owner_id": "user", "source_id": "calendar"}


def test_failure_keeps_authorized_connection_and_pending_retry():
    db = MagicMock()
    db.__getitem__.return_value.update_one = AsyncMock()
    sync = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    assert asyncio.run(after_connect(db, user_id="u", instance_id="mail", sync=sync)) == {
        "ok": False, "retry_pending": True,
    }


def test_partial_calendar_read_does_not_report_success():
    db = MagicMock()
    db.__getitem__.return_value.update_one = AsyncMock()
    result = asyncio.run(after_connect(db, user_id="u", instance_id="cal",
        sync=AsyncMock(return_value={"totals": {"failed": 1}})))
    assert result["ok"] is False


def test_new_calendar_is_discovered_even_if_owner_already_has_mail(monkeypatch):
    from connected import polling
    import connected.service
    class Cursor:
        def __init__(self, rows): self.rows = rows
        def sort(self, *args): return self
        async def to_list(self, *args): return self.rows
    attempts = MagicMock()
    attempts.find.side_effect = [Cursor([]), Cursor([{"owner_id": "u", "source_id": "mail"}])]
    db = MagicMock()
    db.__getitem__.return_value = attempts
    db.connector_instances.find.return_value = Cursor([{"user_id": "u", "id": "new-calendar"}])
    monkeypatch.setattr(connected.service, "ConnectedLifeService", lambda db: SimpleNamespace())
    calendar = SimpleNamespace(id="new-calendar")
    monkeypatch.setattr(polling, "due", AsyncMock(return_value=[calendar]))
    queue, parked = asyncio.run(polling._what_to_read(db, now=datetime.now(timezone.utc), limit=10))
    assert queue == [("u", calendar)]
    assert parked == 0
