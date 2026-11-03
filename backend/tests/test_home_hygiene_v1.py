"""Owner audit 3/11: undated asks from October still active; a GPS home with no town."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository
from opportunities.service import OpportunityService

OWNER = "usr_hygiene_v1"


def opp(key, sensitivity, days_old, valid_until=None):
    born = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return Opportunity(owner_id=OWNER, identity_key=key, status="active", semantic_summary=key,
                       why_it_matters="x", why_now="x", relevance="medium", urgency="none",
                       time_sensitivity=sensitivity, confidence="reasonable", initiative="inform",
                       what_ora_can_do="x", evidence=[EvidenceRef(kind="note", ref=key)],
                       source_context="opportunity_recheck", decision_provenance="model",
                       valid_until=valid_until, created_at=born, updated_at=born)


@pytest.mark.asyncio
async def test_undated_asks_age_out_by_their_own_nature():
    db = AsyncMongoMockClient().hygiene_v1
    repo = OpportunityRepository(db)
    for o in (opp("visita oggi", "perishable", 3), opp("panni località", "changing", 10),
              opp("pagamenti ING", "stable", 22), opp("fresco", "changing", 2),
              opp("datato", "perishable", 30, valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())):
        await repo.save(o)
    assert await OpportunityService(db).expire_past(OWNER) == 3
    left = sorted(o.identity_key for o in await repo.list(OWNER, statuses=["active"]))
    assert left == ["datato", "fresco"]


@pytest.mark.asyncio
async def test_a_gps_home_gets_its_town(monkeypatch):
    from action_engine.travel import maps
    from places.models import Coordinates
    from places.service import PlacesService

    monkeypatch.setattr(maps, "nominatim_reverse_city", AsyncMock(return_value="Tarquinia"))
    db = AsyncMongoMockClient().hygiene_place_v1
    place = await PlacesService(db).save_place(
        OWNER, label="Casa", role="home", coordinates=Coordinates(latitude=42.25, longitude=11.75),
        source="current_position", location_source="current_position")
    assert place.locality == "Tarquinia"
