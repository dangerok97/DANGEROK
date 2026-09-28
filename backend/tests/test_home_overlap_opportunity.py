from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from home.manual_event import create_manual_event, home_event_times
from opportunities.service import OpportunityService


@pytest.mark.asyncio
async def test_two_model_wordings_of_same_home_conflict_make_one_grounded_card(monkeypatch):
    db = AsyncMongoMockClient().test
    day = (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=2)).date().isoformat()
    a, a_end = home_event_times(day, "10:00", "Europe/Rome")
    b, b_end = home_event_times(day, "10:15", "Europe/Rome")
    first = await create_manual_event(db, "alice", title="Ritiro documenti", start=a,
        end=a_end, tz_name="Europe/Rome", description="Portare documento originale")
    second = await create_manual_event(db, "alice", title="Consegna al tecnico", start=b,
        end=b_end, tz_name="Europe/Rome")
    refs = ["calendar:" + first["id"], "calendar:" + second["id"]]
    from opportunities import service as module
    monkeypatch.setattr(module.life_snapshot, "build", AsyncMock(return_value={"unavailable_sources": []}))
    monkeypatch.setattr(module.life_snapshot, "evidence_refs", lambda state: {ref: "calendar_event" for ref in refs})
    from opportunities import reasoning
    raw = [{"identity_key": f"conflict_{i}", "what": f"lunedì {day}: hai un conflitto",
            "why_it_matters": "Compra un corriere e consegna oggi.",
            "what_i_can_do": "Il corriere consegnerà certamente.",
            "evidence_refs": refs, "requires_clarification": True,
            "clarifying_question": "Qual è l'indirizzo?", "valid_until": datetime.now(ZoneInfo("Europe/Rome")).isoformat()}
           for i in (1, 2)]
    monkeypatch.setattr(reasoning, "scan", AsyncMock(return_value={"opportunities": raw}))
    result = await OpportunityService(db).scan("alice")
    assert len(result.created) == 1
    assert await db.opportunities.count_documents({"owner_id": "alice"}) == 1
    card = (await db.opportunities.find_one({"owner_id": "alice"}))
    assert card["identity_key"].startswith("home_overlap:")
    assert "45 minuti" in card["semantic_summary"]
    assert "lunedì" not in card["semantic_summary"]
    assert "corriere" not in card["what_ora_can_do"]
    assert not card["requires_clarification"] and not card["needs_research"]
    assert datetime.fromisoformat(card["valid_until"]) == datetime.fromisoformat(a_end).astimezone(timezone.utc)
