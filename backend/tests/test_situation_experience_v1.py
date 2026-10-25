"""ORA remembers how similar Situations went at the same place, and uses it as evidence."""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations import experience
from situations.models import SituationEvent, SituationState


def state(sid, summary="Panni stesi ad asciugare", place="Tarquinia", started=None, resolved=None, facts=None):
    return SituationState(
        id=sid, user_id="u1", summary=summary, location_label=place,
        started_at=started, resolved_at=resolved,
        history=[SituationEvent(revision=2, operation="resolve", source="user_conversation",
                                changes={"facts": facts or []})],
    )


def test_similarity_is_about_the_same_thing():
    assert experience.similar("Panni stesi ad asciugare", "Ho steso i panni ad asciugare")
    assert not experience.similar("Panni stesi ad asciugare", "Parcheggio pagato fino alle 5")


@pytest.mark.asyncio
async def test_closing_records_estimate_and_end_and_a_new_one_recalls_it():
    db = AsyncMongoMockClient().experience_v1
    await db.agent_goals.insert_one({
        "owner_id": "u1", "source_refs": ["situation:sit_old"], "updated_at": "2026-10-25T17:00:00+00:00",
        "situation_outcome": {"headline": "Asciutti tra le 16:00 e le 17:00",
                              "window_start": "2026-10-25T15:00:00+00:00", "window_end": "2026-10-25T16:00:00+00:00"},
    })
    old = state("sit_old", started="2026-10-25T09:39:00+01:00", resolved="2026-10-25T16:40:00+00:00",
                facts=["erano ancora un po' umidi"])
    await experience.record(db, "u1", old, operation="resolve")
    new = state("sit_new", summary="Ho steso i panni ad asciugare")
    text = await experience.recall(db, "u1", new, tz="Europe/Rome")
    assert text and "stima 16:00-17:00" in text and "chiusa alle 17:40" in text
    assert "umidi" in text and "Tarquinia" in text
    # Elsewhere, or something else, recalls nothing.
    assert await experience.recall(db, "u1", state("sit_x", place="Roma")) is None
    assert await experience.recall(db, "u1", state("sit_y", summary="Lavatrice avviata")) is None
    assert await experience.recall(db, "u2", new) is None


def test_history_counts_as_a_baseline_and_guidance_mentions_it():
    import inspect
    from agent.reasoning import _SITUATION_OUTCOME
    from situations import outcomes
    assert "situation.history" in inspect.getsource(outcomes.validate_assessment)
    assert "situation_experience" in _SITUATION_OUTCOME
    for word in ("panni", "laundry", "bucato"):
        assert word not in _SITUATION_OUTCOME.lower()
