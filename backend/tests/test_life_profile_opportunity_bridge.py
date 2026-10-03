"""P0 gate: a confirmed life fact can wake the ordinary opportunity pipeline."""

from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.mark.asyncio
async def test_confirmed_life_fact_becomes_one_reviewable_change_and_opportunity(monkeypatch):
    from life_setup.profile_service import LifeProfileService
    from opportunities.discovery import OpportunityDiscovery
    from opportunities import reasoning as opportunity_reasoning, snapshot
    import life_orchestration.scheduler as scheduler

    db = AsyncMongoMockClient().test
    wake = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "schedule_user_reasoning", wake)

    # Keep this gate about the profile bridge, not other live domains.
    for name in (
        "_open_questions", "_recently_settled", "_places", "_presence",
        "_routines", "_comparisons", "_calendar", "_situations",
        "_disagreements", "_money", "_existing_work", "_documents",
    ):
        if hasattr(snapshot, name):
            monkeypatch.setattr(snapshot, name, AsyncMock(return_value=[]))

    async def scan(state, **kwargs):
        facts = state.get("life_profile") or []
        assert any(
            row.get("ref") == "life_profile:casa.citta"
            and row.get("value") == "Milano"
            for row in facts
        )
        return {
            "opportunities": [{
                "identity_key": "fixture:life-profile-city",
                "what": "La città di casa è cambiata.",
                "why_it_matters": "Può cambiare quali servizi locali sono pertinenti.",
                "initiative": "prepare",
                "evidence_refs": ["life_profile:casa.citta"],
            }]
        }

    monkeypatch.setattr(opportunity_reasoning, "scan", AsyncMock(side_effect=scan))

    profiles = LifeProfileService(db)
    await profiles.upsert_fact(
        "alice",
        domain="casa",
        key="casa.citta",
        value="Milano",
        source="user_confirmed",
        status="confirmed",
        confirmed=True,
        allow_overwrite_confirmed=True,
    )

    changes = await db.meaningful_changes.find(
        {"owner_id": "alice"}, {"_id": 0}
    ).to_list(10)
    assert len(changes) == 1
    assert changes[0]["source"] == "life_profile"
    assert changes[0]["entity_ref"] == "life_profile:casa.citta"
    # The durable change log carries an identity/digest, not a second copy of
    # the personal value.
    assert "Milano" not in str(changes[0])
    wake.assert_awaited_once_with("alice", reason="opportunity_change")

    reviewed = await OpportunityDiscovery(db).review("alice", force=True)
    assert reviewed.ran
    assert reviewed.scan is not None
    assert len(reviewed.scan.created) == 1
    created = reviewed.scan.created[0]
    assert "life_profile:casa.citta" in created.evidence_refs

    # Writing the same confirmed fact again is not a new life change.
    await profiles.upsert_fact(
        "alice",
        domain="casa",
        key="casa.citta",
        value="Milano",
        source="user_confirmed",
        status="confirmed",
        confirmed=True,
        allow_overwrite_confirmed=True,
    )
    assert await db.meaningful_changes.count_documents(
        {"owner_id": "alice", "status": "pending"}
    ) == 0
    assert wake.await_count == 1
