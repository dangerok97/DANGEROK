"""Estimates of outdoor processes see the whole window: evening, daylight, season.

Owner, 24/10/2026 18:37: "non siamo d'estate, fuori 16 gradi e umidità 65%:
come è possibile che siano asciutti nel pomeriggio tardi?" The agent saw only
six hours of profile, no sunset, and the claims were capped so daily data fell off.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from agent import providers
from test_situation_weather_clock_v160 import NOW, OWNER, forecast, setup


def long_forecast():
    data = forecast()
    start = datetime(2026, 10, 11, 23, 0)
    data["hours"] = [
        {"time": (start + timedelta(hours=i)).strftime("%H:%M"),
         "datetime": (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M"),
         "temperature_c": 20 - i, "humidity_pct": 60 + 3 * i, "wind_kmh": 10, "rain_chance_pct": 0}
        for i in range(12)
    ]
    data["days"] = [
        {"date": "2026-10-11", "label": "Oggi", "min_c": 12, "max_c": 19, "rain_chance_pct": 0, "condition_label": "Sereno"},
        {"date": "2026-10-12", "label": "Domani", "min_c": 11, "max_c": 17, "rain_chance_pct": 95, "condition_label": "Pioggia"},
    ]
    data["sunrise"], data["sunset"] = "07:24", "18:13"
    return data


@pytest.mark.asyncio
async def test_weather_evidence_keeps_twelve_hours_daylight_and_both_days(monkeypatch):
    db, goal, home, read, moved = await setup(monkeypatch, long_forecast())
    out = await providers.read_weather(db, OWNER, goal, step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    text = " ".join(c.text for c in out.claims)
    assert "tramonto 18:13" in text and "alba 07:24" in text
    assert "2026-10-12T10:00:00+02:00" in text  # the twelfth hour is still there
    assert "Oggi:" in text and "Domani:" in text and "pioggia max 95%" in text


def test_guidance_asks_for_the_whole_window_not_the_current_reading():
    from agent.reasoning import _SITUATION_OUTCOME as text
    for phrase in ("whole expected window", "sunset", "season", "under conditions like these"):
        assert phrase in text
    for word in ("panni", "laundry", "bucato"):
        assert word not in text.lower()
