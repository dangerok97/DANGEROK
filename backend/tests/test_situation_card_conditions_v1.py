"""The Situation update card shows the numbers of the latest real weather read.

Only provider values stored with the owner's evidence; never a default.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentEvidence, ResultProvenance
from agent.providers import Claim
from agent.situation_cards import latest_conditions

OWNER, OTHER, GOAL = "user_cond_owner", "user_cond_other", "gol_sit_cond"


def row(owner, observed, measures, *, ms="000", capability="weather.read", goal=GOAL):
    return AgentEvidence(
        owner_id=owner, goal_id=goal, kind="inspect", claim="Lettura sintetica",
        provenance=ResultProvenance(source_class="external_research", capability=capability,
                                    provider="synthetic", observed_at=observed),
        observed_at=observed.replace("+00:00", f".{ms}+00:00"), measures=measures,
    ).model_dump()


def test_measures_are_display_only_and_never_reach_the_model():
    evidence = AgentEvidence(owner_id=OWNER, goal_id=GOAL, claim="x", measures={"humidity_pct": 62.0})
    assert "measures" not in evidence.for_ai()
    assert Claim(text="x").measures == {}


@pytest.mark.asyncio
async def test_latest_read_numbers_are_merged_and_older_reads_ignored():
    db = AsyncMongoMockClient().cond_latest
    old, new = "2026-10-23T08:00:00+00:00", "2026-10-23T10:00:00+00:00"
    await db.agent_evidence.insert_many([
        row(OWNER, old, {"temperature_c": 11.0, "humidity_pct": 95.0}),
        row(OWNER, new, {"temperature_c": 19.0, "humidity_pct": 62.0, "wind_kmh": 12.0}, ms="611"),
        row(OWNER, new, {"rain_chance_max_pct": 5.0}, ms="618"),
        row(OWNER, new, {}, ms="620"),
    ])
    got = await latest_conditions(db, OWNER, GOAL)
    assert got == {"temperature_c": 19.0, "humidity_pct": 62.0, "wind_kmh": 12.0,
                   "rain_chance_max_pct": 5.0, "observed_at": new}


@pytest.mark.asyncio
async def test_other_owner_other_capability_or_no_numbers_give_nothing():
    db = AsyncMongoMockClient().cond_isolation
    at = "2026-10-23T10:00:00+00:00"
    await db.agent_evidence.insert_many([
        row(OTHER, at, {"temperature_c": 30.0}),
        row(OWNER, at, {"temperature_c": 30.0}, capability="web.research"),
        row(OWNER, at, {}),
    ])
    assert await latest_conditions(db, OWNER, GOAL) is None
