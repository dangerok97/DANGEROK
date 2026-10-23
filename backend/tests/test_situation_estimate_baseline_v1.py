"""Owner's own test 23/10/2026 12:38 ("panni stesi").

The checkpoint judge, now seeing live weather, proposed "asciutti entro le
18:00" five times; every proposal was rejected because an estimate must cite
sourced research and the plan never contained any. Monitoring then suspended
without telling the person that rain was due in the evening. Synthetic data.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionStep, AgentEvidence, AutonomousGoal, ResultProvenance
from agent.service import AgentService
from conversation_engine.ai_core.situation_receipt import verified_situation_receipt

OWNER = "user_baseline"


def goal(kind="situation_followup"):
    return AutonomousGoal(
        id="gol_sit_baseline", owner_id=OWNER, objective="Sapere quando l'attività sintetica è completata",
        desired_outcome="Sapere quando l'attività sintetica è completata", source_kind=kind,
        source_refs=["situation:sit_baseline"],
    )


def weather_step():
    return ActionStep(ordinal=0, intent="Leggere le condizioni attuali", step_type="inspect",
                      capability_needed="weather.read")


@pytest.mark.asyncio
async def test_situation_plan_gets_baseline_research_after_first_read():
    service = AgentService(AsyncMongoMockClient().baseline_add)
    steps = await service._with_situation_baseline_research(OWNER, goal(), [weather_step()])
    assert [s.capability_needed for s in steps] == ["weather.read", "web.research"]
    assert [s.ordinal for s in steps] == [0, 1]
    assert "attività sintetica" in steps[1].expected_result


@pytest.mark.asyncio
async def test_valid_research_already_held_is_reused_not_repeated():
    db = AsyncMongoMockClient().baseline_reuse
    service = AgentService(db)
    g = goal()
    await service.evidence.record(AgentEvidence(
        owner_id=OWNER, goal_id=g.id, kind="research", claim="Durata tipica sintetica",
        provenance=ResultProvenance(source_class="external_research", capability="web.research",
                                    research_valid_until=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat()),
    ))
    steps = await service._with_situation_baseline_research(OWNER, g, [weather_step()])
    assert [s.capability_needed for s in steps] == ["weather.read"]


@pytest.mark.asyncio
async def test_non_situation_goals_and_plans_with_research_are_unchanged():
    service = AgentService(AsyncMongoMockClient().baseline_other)
    plain = [weather_step()]
    assert await service._with_situation_baseline_research(OWNER, goal("opportunity"), plain) == plain
    with_research = [weather_step(), ActionStep(ordinal=1, intent="Ricerca", step_type="research",
                                                capability_needed="web.research")]
    assert await service._with_situation_baseline_research(OWNER, goal(), with_research) == with_research


def test_plain_reply_for_new_situation_has_no_technical_receipt():
    result = {"status": "success", "operation": "create",
              "situation": {"id": "sit_0123456789abcdef", "created_at": "2026-10-23T09:34:26+00:00",
                            "started_at": "2026-10-23T11:34:21+02:00", "status": "active"}}
    plain = "La seguo io: ti avviso quando è il momento giusto."
    assert verified_situation_receipt(plain, result) == plain
    # A record claim is still corrected with the canonical receipt.
    claimed = verified_situation_receipt("Ho registrato la nuova situazione sit_FAKE1234.", result)
    assert "sit_0123456789abcdef" in claimed and "sit_FAKE1234" not in claimed
