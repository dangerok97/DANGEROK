from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from places.service import PlacesService
import places.reasoning as reasoning
import opportunities.discovery as discovery


@pytest.mark.asyncio
async def test_routine_learning_does_not_reread_unchanged_presence_evidence(monkeypatch):
    db = AsyncMongoMockClient().test
    service = PlacesService(db)
    evidence = {
        "period": "last_30_days",
        "place_names": {"home": "Casa", "work": "Lavoro"},
        "days": [
            {"day": "2026-10-01", "places": ["home", "work", "home"]},
            {"day": "2026-10-02", "places": ["home", "work", "home"]},
        ],
        "journeys": [
            {"from_place_id": "home", "to_place_id": "work", "duration_seconds": 1800}
        ],
    }
    monkeypatch.setattr(service, "routine_evidence", AsyncMock(return_value=evidence))
    reader = AsyncMock(return_value=None)
    monkeypatch.setattr(reasoning, "read_the_shape_of_the_days", reader)

    first = await service.review_routines("alice")
    second = await service.review_routines("alice")

    assert first is None
    assert second == {"unchanged": True}
    assert reader.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source,kind", [("places", "presence.changed"), ("documents", "document.facts_changed")])
async def test_place_changes_refresh_routines_before_opportunity_snapshot(monkeypatch, source, kind):
    from opportunities import snapshot
    from opportunities.models import ScanResult
    from opportunities.service import OpportunityService
    from places.models import ObservedRoutine

    db = AsyncMongoMockClient().test
    old = ObservedRoutine(user_id="alice", place_sequence=["home", "work"],
                          interpretation="Routine precedente sintetica")
    await db.observed_routines.insert_one(old.model_dump())
    evidence = {
        "place_names": {"home": "Casa", "work": "Lavoro"}, "journeys": [],
        "days": [{"day": "2026-10-01", "places": ["home", "work"]},
                 {"day": "2026-10-02", "places": ["home", "work"]}],
    }
    monkeypatch.setattr(PlacesService, "routine_evidence", AsyncMock(return_value=evidence))
    reader = AsyncMock(return_value={
        "place_ids": ["home", "work"], "weekdays": ["lunedì"],
        "typical_start": "09:00", "typical_end": "17:00", "occurrences": 2,
        "interpretation": "Routine aggiornata sintetica", "worth_asking": False,
        "question": "", "proactive_review_lead_minutes": 0,
    })
    monkeypatch.setattr(reasoning, "read_the_shape_of_the_days", reader)
    calls = []
    real_refresh = PlacesService.review_routines

    async def refresh(service, owner, **kwargs):
        result = await real_refresh(service, owner, **kwargs)
        calls.append("routines")
        return result

    expected = "Routine aggiornata sintetica" if source == "places" else old.interpretation

    async def build(database, owner, **kwargs):
        calls.append("snapshot")
        routine = await database.observed_routines.find_one({"user_id": owner, "id": old.id})
        # Read the actual persisted routine, not merely proof that the method
        # was called: the snapshot must see the completed refresh.
        assert routine["interpretation"] == expected
        return {"routines": [{"id": routine["id"], "interpretation": routine["interpretation"]}]}

    async def scan(service, owner, **kwargs):
        calls.append("scan")
        assert kwargs["prepared_snapshot"]["routines"][0]["interpretation"] == expected
        return ScanResult(silence=True)

    monkeypatch.setattr(PlacesService, "review_routines", refresh)
    monkeypatch.setattr(snapshot, "build", build)
    monkeypatch.setattr(OpportunityService, "scan", scan)
    service = discovery.OpportunityDiscovery(db)
    admitted = await service.changes.record("alice", source=source, kind=kind, entity_ref="synthetic-source")
    assert admitted.admitted
    result = await service.review("alice")
    assert result.ran and not result.unavailable and result.changes_reviewed == 1
    assert calls == (["routines", "snapshot", "scan"] if source == "places" else ["snapshot", "scan"])
    assert reader.await_count == (1 if source == "places" else 0)
