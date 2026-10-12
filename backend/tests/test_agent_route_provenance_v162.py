"""A route read is a fresh estimate, not a timestamped traffic measurement.

Real adapters, consumer, executor and evidence readback; HTTP replies are
synthetic and no language model or external action is used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from agent.evidence import EvidenceStore
from agent.execution import StepExecutor
from agent.models import ActionStep, AgentBudget, AutonomousGoal
from places import routing
from places.models import Coordinates, LifePlace
from scripts import phase1_read_provider_eval as public_gate


OWNER = "synthetic-route-reader-owner"
REFS = ["place:synthetic-origin", "place:synthetic-destination"]
TIME_SOURCE = "ora_clock_not_provider_observation_time"


async def world():
    db = AsyncMongoMockClient().v162_route_consumer
    await db.life_places.insert_many([
        LifePlace(id=ref.split(":", 1)[1], user_id=OWNER, label=label,
            coordinates=Coordinates(latitude=point["latitude"], longitude=point["longitude"])).model_dump()
        for ref, label, point in zip(REFS, ("Origine sintetica", "Destinazione sintetica"),
                                    (public_gate.ORIGIN, public_gate.DESTINATION))
    ])
    goal = AutonomousGoal(id="synthetic-route-goal", owner_id=OWNER, status="active",
        objective="Preparare lo spostamento", desired_outcome="Conoscere la stima del percorso")
    step = ActionStep(intent="Leggere il percorso", step_type="inspect", capability_needed="route.read",
        input_refs=REFS, parameters={"travel_mode": "drive"})
    return db, goal, step


def adapter(monkeypatch, provider, adjust=None):
    monkeypatch.setenv("ROUTING_PROVIDER", provider)
    monkeypatch.setenv("ROUTING_API_KEY", "synthetic-route-reader-key")
    client = httpx.AsyncClient
    requests, responses = [], []

    def reply(request):
        requests.append(request)
        return public_gate._scripted_reply(request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs:
        client(transport=httpx.MockTransport(reply), **kwargs))
    original = routing.get_route

    async def get_route(*args, **kwargs):
        response = await original(*args, **kwargs)
        if adjust is not None:
            response = adjust(deepcopy(response))
        responses.append(deepcopy(response))
        return response

    monkeypatch.setattr(routing, "get_route", get_route)
    return requests, responses


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google_routes", "mapbox"])
@pytest.mark.parametrize("metadata", ["current", "legacy"])
async def test_route_estimate_and_retrieval_meaning_survive_executor_and_evidence(monkeypatch, provider, metadata):
    def adjust(response):
        if metadata == "legacy":
            for key in ("duration_kind", "retrieved_at", "retrieval_time_source", "provider_as_of"):
                response.pop(key, None)
        return response

    requests, responses = adapter(monkeypatch, provider, adjust)
    db, goal, step = await world()
    budget = AgentBudget()
    result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False, budget=budget)
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    assert result.status == "succeeded" and result.data_ref == "route:live"
    assert len(requests) == len(responses) == budget.capability_calls == 1
    assert budget.cognitive_calls == 0 and len(evidence) == (2 if provider == "google_routes" else 1)
    assert responses[0]["duration_seconds"] == 900 and responses[0]["distance_meters"] == 3800
    assert responses[0]["reflects_current_traffic"] is True
    assert result.provenance.provider == provider and result.provenance.source_refs == REFS
    # Freshness describes this new route estimate, not its measurement time.
    expected_freshness = "fresh" if metadata == "current" else "unknown"
    assert result.provenance.freshness == expected_freshness
    claims = " ".join(item.claim for item in evidence)
    assert "durata stimata" in claims and "15 min" in claims and "3.8 km" in claims
    if provider == "google_routes":
        assert "3 min" in claims
    else:
        assert "aggiunge" not in claims  # This adapter supplied no traffic-free duration.
    assert "traffico attuale" not in claims
    for row in (item.for_ai() for item in evidence):
        assert row["really_happened"] is True and row["how_old"] == expected_freshness
        assert row["source_refs"] == REFS
        assert "stimata" in row["note"] and "provider non dichiara l'istante" in row["note"]
        assert len(row["note"]) <= 200
        if metadata == "current":
            assert row["observed_at"] == responses[0]["retrieved_at"]
            assert datetime.fromisoformat(row["observed_at"]).utcoffset().total_seconds() == 0
            assert "lettura ORA" in row["note"] and "non istante dei dati" in row["note"]
        else:
            assert row["observed_at"] == ""
            assert "Orario della lettura non disponibile" in row["note"]
    stored = json.dumps([item.model_dump() for item in evidence])
    for point in (public_gate.ORIGIN, public_gate.DESTINATION):
        assert str(point["latitude"]) not in stored and str(point["longitude"]) not in stored
    assert await db.agent_action_attempts.count_documents({}) == 0
    assert await db.action_intents.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [
    {"retrieved_at": "2026-10-12T09:00:00", "retrieval_time_source": TIME_SOURCE},
    {"retrieved_at": {"untrusted": "not a time"}, "retrieval_time_source": TIME_SOURCE},
    {"retrieved_at": "2026-10-12T09:00:00+00:00", "retrieval_time_source": "unidentified_clock"},
])
async def test_invalid_or_unidentified_clock_is_not_promoted_to_observed_time(monkeypatch, metadata):
    requests, _ = adapter(monkeypatch, "google_routes", lambda response: {**response, **metadata})
    db, goal, step = await world()
    result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False)
    assert result.status == "succeeded" and len(requests) == 1
    assert result.provenance.observed_at == "" and result.provenance.freshness == "unknown"
    assert "Orario della lettura non disponibile" in result.provenance.certainty_note
    assert "not a time" not in result.provenance.certainty_note
    assert all(row.for_ai()["observed_at"] == "" for row in await EvidenceStore(db).for_goal(OWNER, goal.id))


@pytest.mark.asyncio
async def test_partial_route_does_not_invent_a_measurement_timestamp(monkeypatch):
    requests, responses = adapter(monkeypatch, "google_routes", lambda response: {**response, "duration_seconds": None})
    db, goal, step = await world()
    result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False)
    assert result.status == "partial" and result.error_type == "route_duration_missing" and result.retryable
    assert len(requests) == 1
    assert result.provenance.observed_at == responses[0]["retrieved_at"]
    note = result.provenance.for_ai()["note"]
    assert "lettura ORA" in note and "provider non dichiara l'istante" in note
    assert len(note) <= 200 and await db.agent_evidence.count_documents({}) == 0


@pytest.mark.asyncio
async def test_provider_time_is_distinct_from_the_ora_retrieval_time(monkeypatch):
    as_of = "2026-10-11T23:04:05+00:00"
    _, responses = adapter(monkeypatch, "google_routes", lambda response: {**response, "provider_as_of": as_of})
    db, goal, step = await world()
    result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False)
    assert result.provenance.observed_at == responses[0]["retrieved_at"]
    assert result.provenance.observed_at != as_of
    assert as_of in result.provenance.certainty_note and len(result.provenance.certainty_note) <= 200
    assert result.provenance.freshness == "fresh"  # Still the age of the requested estimate.


@pytest.mark.asyncio
async def test_estimate_age_uses_the_saved_retrieval_time_without_restamping_it(monkeypatch):
    retrieved = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    adapter(monkeypatch, "google_routes", lambda response: {**response, "retrieved_at": retrieved})
    db, goal, step = await world()
    result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False)
    assert result.status == "succeeded" and result.provenance.observed_at == retrieved
    assert result.provenance.freshness == "stale"
    assert all(row.for_ai()["how_old"] == "stale" for row in await EvidenceStore(db).for_goal(OWNER, goal.id))


@pytest.mark.asyncio
async def test_nontraffic_route_remains_an_estimate_without_claiming_traffic(monkeypatch):
    requests, responses = adapter(monkeypatch, "mapbox")
    db, goal, step = await world()
    step.parameters["travel_mode"] = "walk"
    result = await StepExecutor(db).run(OWNER, goal, step, may_touch_the_world=False)
    assert result.status == "succeeded" and len(requests) == 1
    assert responses[0]["reflects_current_traffic"] is False
    evidence = await EvidenceStore(db).for_goal(OWNER, goal.id)
    assert len(evidence) == 1 and "durata stimata" in evidence[0].claim
    assert "traffico non dichiarato dal provider" in evidence[0].claim
    assert evidence[0].for_ai()["observed_at"] == responses[0]["retrieved_at"]
