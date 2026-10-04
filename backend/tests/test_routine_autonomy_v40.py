import inspect
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


def test_place_changes_refresh_routines_before_opportunity_snapshot():
    source = inspect.getsource(discovery.OpportunityDiscovery.review)
    assert 'getattr(change, "source", "") == "places"' in source
    assert "review_routines(owner_id" in source
    assert source.index("review_routines(owner_id") < source.index("snapshot = await")
