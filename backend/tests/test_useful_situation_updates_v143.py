"""V143: one fresh, material Situation outcome; no monitoring jargon.

Fixtures do not involve real users, providers or notifications.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.updates import current_situation_updates


OWNER = "synthetic-owner"
SID = "sit_temporanea_test"
G1, G2 = "gol_situazione_test_1", "gol_situazione_test_2"


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat()


async def fixtures(db, *, at=None):
    now = at or datetime.now(timezone.utc)
    await db.situations.insert_one({
        "id": SID, "user_id": OWNER, "summary": "Attività temporanea da seguire.",
        "status": "active", "revision": 1,
        "created_at": iso(now - timedelta(days=2)),
        "updated_at": iso(now - timedelta(hours=2)),
    })
    await db.agent_goals.insert_many([
        {"id": G1, "owner_id": OWNER, "status": "waiting",
         "source_refs": [f"situation:{SID}"]},
        {"id": G2, "owner_id": OWNER, "status": "active",
         "source_refs": [f"situation:{SID}"]},
    ])
    for index, goal in enumerate((G1, G2)):
        await db.agent_updates.insert_one({
            "owner_id": OWNER, "goal_id": goal,
            "outcome": "requires_attention",
            "headline": "Metti al riparo l'attività all'aperto: la previsione indica pioggia imminente.",
            "at": iso(now - timedelta(minutes=12 + 2 * index)),
            "refs": [f"evd_synthetic_{index}", "journal:synthetic"],
        })
        await db.agent_evidence.insert_one({
            "id": f"evd_synthetic_{index}",
            "owner_id": OWNER, "goal_id": goal,
            "claim": "Provider meteo: probabilità di pioggia 80% entro un'ora.",
            "observed_at": iso(now - timedelta(minutes=13 + 2 * index)),
            "provenance": {
                "source_class": "external_research",
                "capability": "weather.read",
                "provider": "open_meteo",
                "freshness": "fresh",
            },
        })
    return now


@pytest.mark.asyncio
async def test_two_agent_goals_about_one_situation_produce_only_one_actionable_update():
    db = AsyncMongoMockClient().useful_situation_v143
    now = await fixtures(db)
    result = await current_situation_updates(db, OWNER, now=now)
    assert len(result) == 1
    item = result[0]
    assert item["situation_id"] == SID
    assert item["revision"] == 1
    assert "Metti al riparo" in item["headline"]
    assert "80%" in item["evidence_summary"]
    assert item["created_at"] == iso(now - timedelta(days=2))
    assert item["evidence_at"] != item["created_at"]


@pytest.mark.asyncio
async def test_yesterdays_weather_and_two_day_old_activity_do_not_trigger_an_alert():
    db = AsyncMongoMockClient().useful_stale_weather_v143
    now = await fixtures(db)
    await db.agent_evidence.update_many({}, {
        "$set": {"observed_at": iso(now - timedelta(hours=3))},
    })
    assert await current_situation_updates(db, OWNER, now=now) == []


@pytest.mark.asyncio
async def test_user_change_resolve_and_simulation_invalidate_previous_alert():
    db = AsyncMongoMockClient().useful_changed_v143
    now = await fixtures(db)
    await db.situations.update_one(
        {"id": SID}, {"$set": {"updated_at": iso(now - timedelta(minutes=2))}}
    )
    assert await current_situation_updates(db, OWNER, now=now) == []
    await db.situations.update_one(
        {"id": SID}, {"$set": {"updated_at": iso(now - timedelta(hours=2)),
                                "status": "resolved"}}
    )
    assert await current_situation_updates(db, OWNER, now=now) == []
    await db.situations.update_one(
        {"id": SID}, {"$set": {"status": "active"}}
    )
    await db.agent_evidence.update_many({}, {
        "$set": {"provenance.source_class": "simulated"},
    })
    assert await current_situation_updates(db, OWNER, now=now) == []


@pytest.mark.asyncio
async def test_unproven_vague_activity_does_not_become_an_update():
    db = AsyncMongoMockClient().useful_generic_v143
    now = await fixtures(db)
    await db.agent_updates.update_many({}, {
        "$set": {"headline": "Capire quando la situazione raggiunge l'esito utile per la persona."}
    })
    assert await current_situation_updates(db, OWNER, now=now) == []


@pytest.mark.asyncio
async def test_other_owner_cannot_read_another_persons_situation_or_evidence():
    db = AsyncMongoMockClient().useful_owners_v143
    now = await fixtures(db)
    assert await current_situation_updates(db, "other-account", now=now) == []


@pytest.mark.asyncio
async def test_generic_background_monitor_never_becomes_work_in_home():
    from agent.models import AutonomousGoal
    from agent.service import AgentService

    db = AsyncMongoMockClient().monitor_not_update_v143
    await db.agent_goals.insert_one(AutonomousGoal(
        id="gol_sit_internal",
        owner_id=OWNER,
        status="waiting",
        source_kind="situation_followup",
        source_refs=[f"situation:{SID}"],
        objective="Capire quando la situazione raggiunge un esito.",
        desired_outcome="Un risultato da verificare.",
        requires_user_input=True,
    ).model_dump())
    assert await AgentService(db).for_home(OWNER) == []
