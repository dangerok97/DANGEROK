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
    monkeypatch.setattr(weather, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(weather, "configured_provider", lambda: "test")
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
    monkeypatch.setattr(weather, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(weather, "configured_provider", lambda: "test")
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
    assert "CUMULATIVE PHYSICAL PROCESSES" in prompt
    assert "do not infer \"finished by 16:00\"" in prompt
    assert "cumulative physical process" in prompt.lower()
    assert "documented/calibrated" in prompt
    assert "keep the estimate broad" in prompt


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
    assert "accumulated effective exposure" in reasoning
    assert "remaining favorable window is too short" in reasoning


def test_empirical_numeric_estimate_without_structured_basis_is_blocked():
    from conversation_engine.ai_core.loop import _quantitative_estimate_issues
    from conversation_engine.ai_core.models import CognitiveDecision

    decision = CognitiveDecision(
        response_mode="answer",
        message_to_user="Indicativamente saranno pronti verso le 16:00.",
        user_intent_summary="stimare un tempo reale",
    )
    issues = _quantitative_estimate_issues(
        decision,
        decision.message_to_user,
        [],
    )

    assert "unstructured_empirical_estimate" in issues


def test_live_weather_is_input_not_calibration_for_an_unrelated_rate():
    from conversation_engine.ai_core.loop import _quantitative_estimate_issues
    from conversation_engine.ai_core.models import CognitiveDecision, QuantitativeEstimate

    decision = CognitiveDecision(
        response_mode="answer",
        message_to_user="Indicativamente saranno pronti verso le 16:00.",
        user_intent_summary="stimare un tempo reale",
        quantitative_estimates=[
            QuantitativeEstimate(
                statement="pronti verso le 16:00",
                basis_type="specialized_capability",
                evidence_refs=["weather:now"],
                uncertainty_note="dipende dalle condizioni",
                material_to_action=True,
            )
        ],
    )
    weather_observation = {
        "kind": "tool",
        "name": "get_weather_forecast",
        "status": "ok",
        "payload": {"status": "ok"},
        "provenance": ["weather:now"],
    }

    issues = _quantitative_estimate_issues(
        decision,
        decision.message_to_user,
        [weather_observation],
    )

    assert "material_estimate_basis_unverified:specialized_capability" in issues


def test_external_research_can_calibrate_empirical_numeric_estimate():
    from conversation_engine.ai_core.loop import _quantitative_estimate_issues
    from conversation_engine.ai_core.models import CognitiveDecision, QuantitativeEstimate

    decision = CognitiveDecision(
        response_mode="answer",
        message_to_user="Indicativamente la finestra è tra 8 e 12 ore.",
        user_intent_summary="stimare un tempo reale",
        quantitative_estimates=[
            QuantitativeEstimate(
                statement="tra 8 e 12 ore",
                basis_type="external_research",
                evidence_refs=["src_technical_1"],
                uncertainty_note="range adattato alle condizioni locali",
                material_to_action=True,
            )
        ],
    )
    research_observation = {
        "kind": "research",
        "name": "research",
        "status": "ok",
        "payload": {"grounding": "TOOL_OBSERVATION"},
        "provenance": ["src_technical_1"],
    }

    assert _quantitative_estimate_issues(
        decision,
        decision.message_to_user,
        [research_observation],
    ) == []


def test_general_prompt_requires_documented_calibration_for_empirical_numbers():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    prompt = COGNITIVE_SYSTEM_PROMPT
    assert "Quantitative real-world estimates need calibration" in prompt
    assert "Mechanism is not a number" in prompt
    assert "Live context" in prompt and "not calibration" in prompt
    assert "quantitative_estimates" in prompt
    assert "external research from credible/technical sources" in prompt
