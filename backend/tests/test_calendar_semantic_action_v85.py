"""V85 — semantic calendar targeting and no empty acknowledgements."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

ROOT = Path(__file__).resolve().parents[1]
OWNER = "alice"


async def _draft(db, *, event_id: str, title: str, days: int = 3):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    await db.calendar_event_drafts.insert_one({
        "id": event_id,
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
async def test_cancel_with_typo_surfaces_real_event_for_ai_semantic_resolution():
    from conversation_engine.ai_core.tools.calendar_caps import cancel_calendar_event

    db = AsyncMongoMockClient().test
    await _draft(
        db,
        event_id="ced_seconda_passata",
        title="TEST ORA — seconda passata",
    )

    obs = await cancel_calendar_event(
        {"target_title": "TEST ORA - seconda pasata"},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "Cancella TEST ORA - seconda pasata",
        },
    )

    assert obs.status == "partial"
    assert obs.payload["failure_kind"] == "calendar_target_needs_ai_resolution"
    assert obs.payload["requested_title"] == "TEST ORA - seconda pasata"
    assert len(obs.payload["candidates"]) == 1
    candidate = obs.payload["candidates"][0]
    assert candidate["title"] == "TEST ORA — seconda passata"
    assert candidate["calendar_ref"] == "calendar:ced_seconda_passata"

    # A fuzzy/semantic candidate is evidence for AI, never an automatic write.
    saved = await db.calendar_event_drafts.find_one(
        {"id": "ced_seconda_passata"}, {"_id": 0}
    )
    assert saved["status"] != "cancelled"


@pytest.mark.asyncio
async def test_two_plausible_calendar_names_are_returned_not_silently_chosen():
    from conversation_engine.ai_core.tools.calendar_caps import cancel_calendar_event

    db = AsyncMongoMockClient().test
    await _draft(db, event_id="ced_alfa", title="Riunione progetto Alfa", days=2)
    await _draft(db, event_id="ced_beta", title="Riunione progetto Beta", days=3)

    obs = await cancel_calendar_event(
        {"target_title": "Riunione progetto"},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "Cancella riunione progetto",
        },
    )

    assert obs.status == "partial"
    assert obs.payload["failure_kind"] == "calendar_target_needs_ai_resolution"
    titles = {row["title"] for row in obs.payload["candidates"]}
    assert {"Riunione progetto Alfa", "Riunione progetto Beta"} <= titles
    assert await db.calendar_event_drafts.count_documents(
        {"user_id": OWNER, "status": "cancelled"}
    ) == 0


@pytest.mark.asyncio
async def test_punctuation_difference_is_same_normalized_calendar_title():
    from conversation_engine.ai_core.tools.calendar_caps import (
        _named_calendar_ref_resolution,
    )

    db = AsyncMongoMockClient().test
    await _draft(
        db,
        event_id="ced_punctuation",
        title="TEST ORA — seconda passata",
    )

    got = await _named_calendar_ref_resolution(
        db,
        OWNER,
        "TEST ORA - seconda passata",
        now=datetime.now(timezone.utc),
    )

    assert got["status"] == "ok"
    assert got["match"]["calendar_ref"] == "calendar:ced_punctuation"


def test_prompt_requires_semantic_calendar_targeting_not_exact_title_passwords():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    prompt = COGNITIVE_SYSTEM_PROMPT.lower()
    assert "calendar references are semantic, not string passwords" in prompt
    assert "small lexical variation" in prompt
    assert "one real candidate is clearly what they mean" in prompt
    assert "never invent a ref" in prompt


def test_bare_ok_is_a_guarded_non_outcome():
    from conversation_engine.ai_core.loop import _BARE_ACK_RE

    assert _BARE_ACK_RE.fullmatch("Ok.")
    assert _BARE_ACK_RE.fullmatch("va bene")

    source = (ROOT / "conversation_engine" / "ai_core" / "loop.py").read_text(
        encoding="utf-8"
    )
    assert "BARE_ACK_NOT_PROGRESS" in source
    assert 'event="BARE_ACK_NUDGE"' in source
    assert "use the capability that can perform or prepare it" in source
