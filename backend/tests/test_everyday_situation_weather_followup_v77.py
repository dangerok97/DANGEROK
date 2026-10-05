from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService
from places.models import Coordinates
from places.service import PlacesService
from situations.models import SituationState
from situations.repository import SituationRepository


OWNER = "alice"


@pytest.mark.asyncio
async def test_everyday_situation_reaches_real_weather_and_schedules_useful_recheck(monkeypatch):
    """
    v77 Reality Gate:
      ordinary user statement -> governed Situation -> source-aware plan
      -> real read-only weather evidence -> AI-chosen precise background revisit.

    No production branch knows what laundry is. The model-facing source context
    is what makes weather a sensible capability for this particular Situation.
    """
    from agent import reasoning
    from ambient.service import AmbientService
    from home.service import HomeService
    import weather

    db = AsyncMongoMockClient().test
    service = AgentService(db)

    home = await PlacesService(db).save_place(
        OWNER,
        label="Casa",
        role="home",
        locality="Tarquinia",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
        source="user_stated",
        role_confirmed_by_user=True,
    )
    situation = SituationState(
        id="sit_laundry_v77",
        user_id=OWNER,
        summary="Ho steso i panni sul balcone di Casa.",
        semantic_kind="attività temporanea con esito atteso",
        temporal_scope="iniziata adesso",
        attention_intent=(
            "valutare se tempi o condizioni esterne rendono utile "
            "ricontrollare i panni"
        ),
        facts=["I panni sono stesi all'aperto."],
        constraints=["Non devono restare fuori se arriva pioggia."],
        linked_object_refs=[f"place:{home.id}"],
    )
    await SituationRepository(db).insert(situation)

    goal = AutonomousGoal(
        id="goal_laundry_v77",
        owner_id=OWNER,
        status="active",
        objective="Seguire l'esito futuro della situazione raccontata dall'utente",
        desired_outcome="Rivalutare la situazione quando ci sono informazioni reali utili",
        why_now="La situazione temporanea è appena iniziata.",
        success_criteria=["La situazione viene rivalutata con fonti reali pertinenti"],
        source_kind="opportunity",
        source_refs=[f"situation:{situation.id}", f"place:{home.id}"],
        next_run_at=datetime.now(timezone.utc).isoformat(),
    )
    await service.repo.save_goal(goal)

    captured = {}

    async def plan_model(goal_payload, *, capabilities, context, language="it"):
        captured["goal"] = goal_payload
        captured["capabilities"] = capabilities
        captured["context"] = context

        rows = context.get("source_context") or []
        assert len(rows) == 1
        source = rows[0]
        assert source["ref"] == f"situation:{situation.id}"
        assert source["attention_intent"] == situation.attention_intent
        assert f"place:{home.id}" in source["linked_object_refs"]
        assert "panni" in source["summary"].lower()

        return {
            "plan_summary": "Controllare condizioni pertinenti e rivalutare al momento utile.",
            "expected_outcome": "Sapere se serve intervenire o restare in silenzio.",
            "assumptions": [],
            "known_constraints": [],
            "steps": [
                {
                    "intent": "Leggere le condizioni meteo del luogo della situazione",
                    "step_type": "inspect",
                    "capability_needed": "weather.read",
                    "input_refs": [f"place:{home.id}"],
                    "parameters": {},
                    "expected_result": "Meteo aggiornato e rischio di pioggia nelle prossime ore",
                    "external_effect": False,
                    "reversibility": "easily",
                },
                {
                    "intent": "Rivalutare se la situazione richiede attenzione",
                    "step_type": "verify",
                    "capability_needed": "weather.read",
                    "input_refs": [f"place:{home.id}"],
                    "parameters": {},
                    "expected_result": "Evidenza fresca al momento utile",
                    "external_effect": False,
                    "reversibility": "easily",
                },
            ],
        }

    monkeypatch.setattr(reasoning, "make_plan", plan_model)
    monkeypatch.setattr(
        service.capabilities,
        "available",
        AsyncMock(return_value=[
            {"capability": "weather.read", "status": "available_real", "writes": False},
        ]),
    )

    current_location = AsyncMock(return_value=(41.9028, 12.4964, "Roma"))
    monkeypatch.setattr(HomeService, "_where_they_are", current_location)
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "condition_label": "Variabile",
        "temperature_c": 21,
        "humidity_pct": 67,
        "wind_kmh": 12,
        "precipitation_mm": 0,
        "hours": [
            {"time": "15:00", "temperature_c": 21, "rain_chance_pct": 20},
            {"time": "16:00", "temperature_c": 20, "rain_chance_pct": 55},
            {"time": "17:00", "temperature_c": 19, "rain_chance_pct": 75},
        ],
        "days": [],
    })
    monkeypatch.setattr(weather, "forecast_at", forecast)

    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    budget = AgentBudget()

    plan = await service._build_plan(OWNER, goal, run, budget, language="it")
    assert plan is not None
    assert plan.steps[0].capability_needed == "weather.read"
    assert plan.steps[0].input_refs == [f"place:{home.id}"]

    # The thing stays at Casa even if the person moves: no current-position
    # lookup is allowed to silently move this weather follow-up to Rome.
    out = await service._do_step(
        OWNER, goal, plan, plan.steps[0], run, budget, language="it"
    )
    assert out is None
    current_location.assert_not_awaited()
    forecast.assert_awaited_once_with(
        lat=42.249, lon=11.756, place="Tarquinia"
    )

    evidence = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0}
    ).to_list(20)
    evidence_blob = str(evidence)
    assert "probabilità massima di pioggia" in evidence_blob
    assert "75%" in evidence_blob
    assert "42.249" not in evidence_blob and "11.756" not in evidence_blob

    async def next_model(*args, **kwargs):
        found = str(kwargs.get("evidence") or "")
        assert "75%" in found
        return {
            "decision": "wait",
            "step_id": "",
            "reasoning": "Ricontrollare tra 25 minuti con evidenza meteo fresca.",
            "asks": "",
            "ask_kind": None,
            "wait_until": None,
            "wait_minutes": 25,
            "wait_hours": None,
        }

    monkeypatch.setattr(reasoning, "choose_next_action", next_model)

    decision, wait_step = await service._next(
        OWNER, goal, plan, run, budget, language="it"
    )
    assert decision == "wait"
    assert wait_step is not None
    assert wait_step.parameters == {"wait_minutes": 25}

    schedule = AsyncMock(return_value=True)
    monkeypatch.setattr(AmbientService, "schedule", schedule)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    result = await service._wait(
        OWNER,
        goal,
        plan,
        wait_step,
        run,
        minutes=25,
        note=wait_step.intent,
    )

    assert result["state"] == "waiting"
    assert result["for_minutes"] == 25
    assert goal.status == "waiting"
    assert goal.requires_user_input is False
    assert goal.requires_user_authority is False
    assert schedule.await_args.kwargs["source_ref"] == f"goal:{goal.id}"
    assert schedule.await_args.kwargs["reason"] == "opportunity_revisit"


@pytest.mark.asyncio
async def test_planning_context_never_reads_another_users_situation():
    db = AsyncMongoMockClient().test
    service = AgentService(db)

    foreign = SituationState(
        id="sit_foreign_v77",
        user_id="bob",
        summary="BOB-PRIVATE-SITUATION",
        attention_intent="BOB-PRIVATE-INTENT",
    )
    await SituationRepository(db).insert(foreign)

    goal = AutonomousGoal(
        id="goal_foreign_v77",
        owner_id=OWNER,
        status="active",
        objective="Seguire una situazione",
        desired_outcome="Capire cosa fare",
        source_refs=[f"situation:{foreign.id}"],
    )

    rows, unavailable = await service._planning_source_context(OWNER, goal)

    assert rows == []
    assert unavailable is True
    assert "BOB-PRIVATE" not in str(rows)
