"""V90 — temporary situations act on current risk before merely monitoring."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

OWNER = "alice"


@pytest.mark.asyncio
async def test_conversation_weather_exposes_current_precipitation_and_near_term_risk(monkeypatch):
    import weather
    from home.service import HomeService
    from conversation_engine.ai_core.tools.weather_caps import get_weather_forecast

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        HomeService,
        "_where_they_are",
        AsyncMock(return_value=(42.25, 11.76, "Tarquinia")),
    )
    monkeypatch.setattr(
        weather,
        "forecast_at",
        AsyncMock(return_value={
            "available": True,
            "place": "Tarquinia",
            "condition_label": "Pioggia debole",
            "temperature_c": 19,
            "humidity_pct": 84,
            "wind_kmh": 8,
            "precipitation_mm": 0.1,
            "hours": [
                {"time": "12:00", "temperature_c": 19, "rain_chance_pct": 80},
                {"time": "13:00", "temperature_c": 20, "rain_chance_pct": 45},
                {"time": "14:00", "temperature_c": 21, "rain_chance_pct": 15},
                {"time": "15:00", "temperature_c": 21, "rain_chance_pct": 10},
            ],
            "days": [],
        }),
    )

    obs = await get_weather_forecast({}, {"user_id": OWNER, "db": db})

    assert obs.status == "ok"
    assert obs.payload["current"]["precipitation_mm"] == 0.1
    assert obs.payload["current"]["precipitation_active"] is True
    assert obs.payload["near_term"]["next_3h_max_rain_chance_pct"] == 80


@pytest.mark.asyncio
async def test_agent_weather_evidence_calls_out_precipitation_in_progress(monkeypatch):
    import weather
    from home.service import HomeService
    from agent.providers import read_weather

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        HomeService,
        "_where_they_are",
        AsyncMock(return_value=(42.25, 11.76, "Tarquinia")),
    )
    monkeypatch.setattr(
        weather,
        "forecast_at",
        AsyncMock(return_value={
            "available": True,
            "place": "Tarquinia",
            "condition_label": "Pioggia debole",
            "temperature_c": 19,
            "humidity_pct": 84,
            "wind_kmh": 8,
            "precipitation_mm": 0.1,
            "hours": [
                {"time": "12:00", "temperature_c": 19, "rain_chance_pct": 80},
                {"time": "13:00", "temperature_c": 20, "rain_chance_pct": 45},
                {"time": "14:00", "temperature_c": 21, "rain_chance_pct": 15},
            ],
            "days": [],
        }),
    )

    out = await read_weather(
        db,
        OWNER,
        SimpleNamespace(id="goal_laundry"),
        step=SimpleNamespace(input_refs=[]),
    )

    claims = [c.text for c in out.claims]
    assert any("precipitazioni in corso" in c.lower() for c in claims)
    assert any("prossime tre ore" in c.lower() and "80%" in c for c in claims)


def test_conversation_prompt_prioritizes_action_estimate_and_recheck():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    prompt = COGNITIVE_SYSTEM_PROMPT
    assert "changes what the person should do NOW" in prompt
    assert "Do not bury it after a forecast" in prompt
    assert "ACTION NOW -> CURRENT EVIDENCE -> PROVISIONAL OUTCOME TIME -> NEXT RECHECK" in prompt
    assert "indicativamente domani verso le 11:00" in prompt
    assert "current observed risk belongs in `facts`" in prompt
    assert "future estimate belongs in `assumptions`" in prompt


def test_background_agent_and_delivery_prioritize_perishable_protective_action():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    reasoning = (root / "agent" / "reasoning.py").read_text(encoding="utf-8")
    delivery = (root / "delivery" / "reasoning.py").read_text(encoding="utf-8")

    assert "do not choose silent or quiet_update" in reasoning
    assert "make the headline start with the action" in reasoning
    assert "adverse condition is already happening" in delivery
    assert "prefer push with timing=now" in delivery
    assert "Do not schedule the warning for later" in delivery
