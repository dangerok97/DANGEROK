"""The real reasoning boundary retains likelihood, severity and source limits.

This is a delivery-of-evidence regression, not proof that a live LLM will obey
the instructions. Model decisions and external HTTP are explicitly scripted.
"""
import json

import httpx
import pytest

from scripts import phase1_read_provider_eval as runner


@pytest.mark.asyncio
async def test_rising_rain_probability_reaches_model_without_invented_intensity():
    scripted = await runner._scripted_model_factory()
    reviewed = []

    def reply(request):
        response = runner._scripted_reply(request)
        if request.url.host != "api.open-meteo.com":
            return response
        data = response.json()
        data["current"].update({"weather_code": 80, "precipitation": 0.2})
        data["hourly"]["precipitation_probability"] = [68, 68, 75, 83, 83, 90] + [90] * 9
        return httpx.Response(200, json=data, request=request)

    async def inspect_then_decide(system, user):
        payload = json.loads(user)
        weather = [observation for observation in payload["observations"]
                   if observation.get("name") == "get_weather_forecast"]
        if weather:
            observed = weather[-1]["payload"]
            assert observed["current"]["condition"] == "Rovesci"
            assert observed["current"]["precipitation_mm"] == 0.2
            chances = [hour["rain_chance_pct"] for hour in observed["hours"]]
            assert chances[0] == 68 and max(chances) == 90
            assert all("precipitation_mm" not in hour and "intensity" not in hour
                       for hour in observed["hours"])
            assert observed["provider"] == "open_meteo"
            assert observed["timezone"] == "Europe/Rome"
            assert "T" in observed["observed_at"]
            assert all("T" in hour["datetime"] for hour in observed["hours"])
            catalogue = next(line for line in payload["available_tools"]
                             if line.startswith("get_weather_forecast("))
            assert "rain_chance_pct is probability, not intensity" in catalogue
            assert "current readings and forecasts are not guarantees" in catalogue
            assert "rain_chance_pct describes likelihood, not rainfall intensity" in system
            assert "Current precipitation_mm and the" in system
            assert "a forecast is not a guarantee" in system
            reviewed.append(observed)
        return await scripted(system, user)

    result = await runner.run_case(
        mode="scripted", decide=inspect_then_decide, provider_reply=reply, max_steps=5,
    )
    assert result["verdict"]["passed"] is True, result
    assert len(reviewed) == 1
    assert result["real_model_executed"] is False
    assert result["live_provider_reads"] == 0
    assert result["semantic_review"]["automatically_accepted"] is False
