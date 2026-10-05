"""V84 Reality Gate: intelligent everyday life outcome watching.

The production system contains no rule for laundry. The acceptance fixture uses
one familiar everyday situation to prove the generic architecture:
conversation skill -> live environmental evidence -> estimated checkpoint ->
fresh recheck -> useful reminder.
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
)
from agent.service import AgentService
from places.models import Coordinates
from places.service import PlacesService


OWNER = "alice"
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_conversation_weather_skill_exposes_live_environment_without_domain_logic(monkeypatch):
    from conversation_engine.ai_core.tools.weather_caps import get_weather_forecast
    from home.service import HomeService
    import weather

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        HomeService,
        "_where_they_are",
        AsyncMock(return_value=(42.249, 11.756, "Tarquinia")),
    )
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "condition_label": "Sereno",
        "temperature_c": 22,
        "humidity_pct": 48,
        "wind_kmh": 17,
        "precipitation_mm": 0,
        "hours": [
            {
                "time": "13:00",
                "temperature_c": 22,
                "humidity_pct": 48,
                "wind_kmh": 17,
                "rain_chance_pct": 5,
            },
            {
                "time": "14:00",
                "temperature_c": 23,
                "humidity_pct": 43,
                "wind_kmh": 19,
                "rain_chance_pct": 5,
            },
            {
                "time": "15:00",
                "temperature_c": 23,
                "humidity_pct": 41,
                "wind_kmh": 16,
                "rain_chance_pct": 10,
            },
        ],
        "sunrise": "07:10",
        "sunset": "18:42",
    })
    monkeypatch.setattr(weather, "forecast_at", forecast)

    obs = await get_weather_forecast(
        {},
        {"user_id": OWNER, "db": db, "user_message": "situazione temporanea"},
    )

    assert obs.status == "ok"
    assert obs.payload["place"] == "Tarquinia"
    assert obs.payload["current"]["humidity_pct"] == 48
    assert obs.payload["current"]["wind_kmh"] == 17
    assert obs.payload["hours"][1]["humidity_pct"] == 43
    assert obs.payload["hours"][1]["wind_kmh"] == 19
    assert "42.249" not in str(obs.payload)
    assert "11.756" not in str(obs.payload)


@pytest.mark.asyncio
async def test_agent_weather_evidence_keeps_hourly_humidity_and_wind(monkeypatch):
    from agent import providers
    import weather

    db = AsyncMongoMockClient().test
    home = await PlacesService(db).save_place(
        OWNER,
        label="Casa",
        role="home",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
        locality="Tarquinia",
        source="user_stated",
        role_confirmed_by_user=True,
    )

    monkeypatch.setattr(weather, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(
        weather,
        "configured_provider",
        lambda: "open_meteo",
    )
    monkeypatch.setattr(
        weather,
        "forecast_at",
        AsyncMock(return_value={
            "available": True,
            "place": "Tarquinia",
            "condition_label": "Sereno",
            "temperature_c": 22,
            "humidity_pct": 48,
            "wind_kmh": 17,
            "precipitation_mm": 0,
            "hours": [
                {
                    "time": "13:00",
                    "temperature_c": 22,
                    "humidity_pct": 48,
                    "wind_kmh": 17,
                    "rain_chance_pct": 5,
                },
                {
                    "time": "14:00",
                    "temperature_c": 23,
                    "humidity_pct": 43,
                    "wind_kmh": 19,
                    "rain_chance_pct": 5,
                },
                {
                    "time": "15:00",
                    "temperature_c": 23,
                    "humidity_pct": 41,
                    "wind_kmh": 16,
                    "rain_chance_pct": 10,
                },
            ],
            "days": [],
        }),
    )

    goal = AutonomousGoal(
        id="goal_environment_v84",
        owner_id=OWNER,
        status="active",
        objective="Stimare il momento utile di una situazione temporanea",
        desired_outcome="Rivalutare quando l'esito è plausibilmente pronto",
    )
    step = type("Step", (), {"input_refs": [f"place:{home.id}"]})()

    out = await providers.read_weather(db, OWNER, goal, step=step)

    assert out.status == "succeeded"
    claims = " ".join(claim.text for claim in out.claims)
    assert "Profilo previsto" in claims
    assert "umidità 43%" in claims
    assert "vento 19 km/h" in claims
    assert "14:00" in claims
    assert "42.249" not in claims and "11.756" not in claims


@pytest.mark.asyncio
async def test_everyday_outcome_schedules_recheck_then_surfaces_estimated_moment(monkeypatch):
    from agent import reasoning
    from ambient.service import AmbientService

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_life_outcome_v84",
        owner_id=OWNER,
        status="active",
        objective="Seguire l'esito utile della situazione temporanea",
        desired_outcome=(
            "Avvisare quando, in base a evidenza fresca e conoscenza ordinaria, "
            "è plausibile che sia arrivato il momento utile"
        ),
        source_kind="opportunity",
        source_refs=["situation:sit_life_outcome_v84", "place:home_v84"],
    )
    await service.repo.save_goal(goal)

    await service.evidence.record(
        AgentEvidence(
            owner_id=OWNER,
            goal_id=goal.id,
            step_id="weather_initial",
            kind="inspect",
            claim=(
                "Profilo previsto: 13:00, 22°C, umidità 48%, vento 17 km/h, "
                "pioggia 5% | 14:00, 23°C, umidità 43%, vento 19 km/h, "
                "pioggia 5% | 15:00, 23°C, umidità 41%, vento 16 km/h, pioggia 10%."
            ),
            supports="andamento orario delle condizioni ambientali",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="weather.read",
                provider="open_meteo",
                freshness="fresh",
            ),
        )
    )

    async def next_action(*args, evidence, **kwargs):
        blob = str(evidence)
        assert "umidità 43%" in blob
        assert "vento 19 km/h" in blob
        return {
            "decision": "wait",
            "step_id": "",
            "reasoning": (
                "Le condizioni favoriscono il processo; stimo un controllo "
                "utile tra circa 110 minuti, non un esito già certo."
            ),
            "asks": "",
            "ask_kind": None,
            "wait_until": None,
            "wait_minutes": 110,
            "wait_hours": None,
        }

    monkeypatch.setattr(reasoning, "choose_next_action", next_action)

    run = AgentRun(owner_id=OWNER, goal_id=goal.id, background=True)
    decision, wait_step = await service._next(
        OWNER,
        goal,
        type("Plan", (), {"for_ai": lambda self: {}, "steps": []})(),
        run,
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert wait_step.parameters["wait_minutes"] == 110

    schedule = AsyncMock(return_value=True)
    monkeypatch.setattr(AmbientService, "schedule", schedule)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    waited = await service._wait(
        OWNER,
        goal,
        None,
        wait_step,
        run,
        minutes=110,
        note=wait_step.intent,
    )
    assert waited["state"] == "waiting"
    schedule.assert_awaited_once()

    # The wake itself proves nothing. Fresh evidence is recorded before any
    # visible conclusion is allowed.
    await service.evidence.record(
        AgentEvidence(
            owner_id=OWNER,
            goal_id=goal.id,
            step_id="weather_recheck",
            kind="verify",
            claim=(
                "Al ricontrollo: 23°C, umidità 42%, vento 15 km/h, "
                "nessuna precipitazione e rischio pioggia 5%."
            ),
            supports="condizioni fresche al checkpoint",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="weather.read",
                provider="open_meteo",
                freshness="fresh",
            ),
        )
    )
    await service.repo.journal(
        OWNER,
        goal.id,
        kind="step_done",
        note="Ho riletto le condizioni al checkpoint.",
        detail={
            "step_id": "weather_recheck",
            "status": "succeeded",
            "came_from": "external_research",
            "really_happened": True,
            "evidence": 1,
        },
    )

    async def visible(goal_payload, *, what_happened, already_said, language="it"):
        blob = str(what_happened)
        assert "umidità 42%" in blob
        assert "vento 15 km/h" in blob
        return {
            "outcome": "inform_user",
            "headline": (
                "Direi che è il momento di raccoglierli: con le condizioni "
                "rimaste favorevoli dovrebbero essere asciutti."
            ),
            "reasoning": (
                "È una stima aggiornata con evidenza fresca, non una misura diretta."
            ),
            "about": "momento utile stimato della situazione temporanea",
        }

    monkeypatch.setattr(reasoning, "decide_visibility", visible)
    monkeypatch.setattr(service.visibility, "show", AsyncMock(return_value=True))
    offered = AsyncMock(return_value=None)
    monkeypatch.setattr(service.needs, "offer_to_delivery", offered)

    result = await service._consider_visibility(
        OWNER, goal.id, run, AgentBudget(), language="it"
    )

    assert result is not None
    assert result.outcome == "inform_user"
    assert "dovrebbero" in result.headline.lower()
    assert "raccoglierli" in result.headline.lower()
    need = await db.agent_needs.find_one(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0}
    )
    assert need is not None
    assert need["kind"] == "useful_result"
    offered.assert_awaited_once()


def test_life_outcome_policy_is_model_educated_not_domain_hardcoded():
    prompt = (ROOT / "conversation_engine" / "ai_core" / "prompt.py").read_text(
        encoding="utf-8"
    ).lower()
    reasoning = (ROOT / "agent" / "reasoning.py").read_text(
        encoding="utf-8"
    ).lower()
    weather_skill = (
        ROOT / "conversation_engine" / "ai_core" / "tools" / "weather_caps.py"
    ).read_text(encoding="utf-8").lower()

    assert "your own stable general knowledge" in prompt
    assert "research/web evidence" in prompt
    assert "a timer is only a checkpoint" in prompt
    assert "use your own stable general knowledge" in reasoning
    assert "web.research when the missing background is specific" in reasoning
    assert "elapsed time alone as proof" in reasoning

    # Acceptance vocabulary belongs in tests only, not production routing.
    production = prompt + reasoning + weather_skill
    assert "panni" not in production
    assert "laundry" not in production
