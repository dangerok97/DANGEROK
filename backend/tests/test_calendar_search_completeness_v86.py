"""V86 — an empty calendar window is not global absence."""

from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient


OWNER = "alice"


async def _future_event(db, *, title: str, days: int):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    await db.calendar_event_drafts.insert_one({
        "id": "ced_v86_future",
        "user_id": OWNER,
        "title": title,
        "start_datetime": start.isoformat(),
        "end_datetime": (start + timedelta(hours=1)).isoformat(),
        "timezone": "Europe/Rome",
        "status": "draft",
        "sync_status": "local_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@pytest.mark.asyncio
async def test_empty_today_window_does_not_mean_event_does_not_exist():
    from conversation_engine.ai_core.loop import _calendar_empty_read_is_scope_limited
    from conversation_engine.ai_core.tools.calendar_caps import get_calendar_events

    db = AsyncMongoMockClient().test
    await _future_event(db, title="TEST ORA — seconda passata", days=2)

    obs = await get_calendar_events(
        {"when": "today"},
        {"user_id": OWNER, "db": db, "platform": "web"},
    )

    assert obs.status == "ok"
    assert obs.payload["events"] == []
    assert obs.payload["coverage"]["scope"] == "window_only"
    assert "does NOT prove" in obs.payload["coverage"]["absence_semantics"]
    assert _calendar_empty_read_is_scope_limited([obs.model_dump()]) is True


@pytest.mark.asyncio
async def test_named_cancel_target_still_finds_future_event_after_empty_today_read():
    from conversation_engine.ai_core.tools.calendar_caps import (
        cancel_calendar_event,
        get_calendar_events,
    )

    db = AsyncMongoMockClient().test
    await _future_event(db, title="TEST ORA — seconda passata", days=2)

    today = await get_calendar_events(
        {"when": "today"},
        {"user_id": OWNER, "db": db, "platform": "web"},
    )
    assert today.payload["events"] == []

    target = await cancel_calendar_event(
        {"target_title": "TEST ORA seconda passata"},
        {
            "user_id": OWNER,
            "db": db,
            "platform": "web",
            "user_message": "Cancella TEST ORA seconda passata",
        },
    )

    # Punctuation-only variation resolves to the exact normalized future event.
    # Cancellation itself is still governed and may ask for confirmation.
    assert target.status in ("partial", "ok")
    payload = target.payload
    if payload.get("status") == "authority_required":
        assert payload["calendar_ref"] == "calendar:ced_v86_future"
        assert "TEST ORA" in payload["confirmation_request"]["question"]
    else:
        assert payload.get("calendar_ref") == "calendar:ced_v86_future"


def test_global_absence_wording_is_guarded_after_scoped_empty_calendar_read():
    from conversation_engine.ai_core.loop import _CALENDAR_ABSENCE_CLAIM_RE

    for sentence in (
        'Non c\'è nessun evento chiamato "TEST ORA" nel tuo calendario.',
        "Non esiste quell'evento.",
        "Non ho trovato nessun impegno nel calendario.",
    ):
        assert _CALENDAR_ABSENCE_CLAIM_RE.search(sentence)


def test_calendar_scope_guard_forces_another_cognitive_round():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "conversation_engine"
        / "ai_core"
        / "loop.py"
    ).read_text(encoding="utf-8")

    assert "CALENDAR_SEARCH_SCOPE_INCOMPLETE" in source
    assert 'event="CALENDAR_SCOPE_NUDGE"' in source
    assert "broaden the search" in source
    assert "target_title" in source
