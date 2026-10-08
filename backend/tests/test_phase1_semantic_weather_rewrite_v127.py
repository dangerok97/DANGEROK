"""The weather guard should not claim forecast strength from probability alone."""
from conversation_engine.ai_core.grounding.weather_advice import guard_weather_intensity

WEATHER = [{"name": "get_weather_forecast", "payload": {"status": "ok",
    "hours": [{"rain_chance_pct": 75}]}}]


def test_forecast_strength_is_not_derived_from_rain_chance():
    revised, findings = guard_weather_intensity(
        "La pioggia si intensifica nel pomeriggio.", WEATHER)
    assert findings
    assert "non quanto forte" in revised


def test_rain_chance_without_strength_is_preserved():
    sentence = "Probabilita di pioggia al 75%."
    assert guard_weather_intensity(sentence, WEATHER) == (sentence, [])
