"""Regression from the isolated real-model result: 10m28s, 2,765m, 15km/h wind."""
import pytest

from conversation_engine.ai_core.grounding.formatting import normalize_route_weather_reply
from scripts.phase1_semantic_gate import review_trip_answer
from scripts import phase1_read_provider_eval as runner


def observations():
    return [
        {"name": "get_route", "capability": "get_route", "payload": {
            "status": "ok", "destination": "Colosseo", "duration_seconds": 628,
            "distance_meters": 2765, "reflects_current_traffic": True}},
        {"name": "get_weather_forecast", "capability": "get_weather_forecast", "payload": {
            "status": "ok", "current": {"condition": "Rovesci", "temperature_c": 24,
                                      "wind_kmh": 15, "humidity_pct": 74},
            "hours": [{"datetime": "2026-10-08T15:00", "rain_chance_pct": 75}]}}
    ]


def test_compound_eta_and_wind_speed_are_not_route_discrepancies():
    answer = ("Il viaggio dura 10 minuti e 28 secondi (628 secondi), "
              "per 2.765 metri. Meteo: 24 °C, vento a 15 km/h, pioggia al 75%.")
    assert review_trip_answer(answer, observations())["passed"] is True


def test_serialized_model_message_is_rendered_from_provider_facts():
    raw = "{'summary': 'oggetto del modello', 'details': []}"
    plain, findings = normalize_route_weather_reply(raw, observations())
    assert findings == ["STRUCTURED_MESSAGE_RENDERED_FROM_EVIDENCE"]
    assert "10 minuti" in plain and "2,8 km" in plain
    assert "24 °C" in plain and "75%" in plain
    assert "oggetto del modello" not in plain


def test_formatting_fallback_does_not_modify_unrelated_conversation():
    raw = "{'summary': 'codice', 'details': []}"
    assert normalize_route_weather_reply(raw, []) == (raw, [])


@pytest.mark.asyncio
async def test_model_output_format_correction_still_fails_model_quality_gate():
    reference = await runner._scripted_model_factory()

    async def decide(system, user):
        value = await reference(system, user)
        if value.get("response_mode") == "answer":
            value["message_to_user"] = "{'summary': 'dati formattati male', 'details': []}"
        return value

    report = await runner.run_case(mode="scripted", decide=decide)
    assert report["verdict"]["technical_passed"] is True
    assert report["verdict"]["semantic_gate_passed"] is False
    assert report["semantic_review"]["grounding_rewrites"] > 0
    assert "dati formattati male" not in report["final_answer"]
