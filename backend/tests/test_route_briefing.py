"""Route briefings must use provider evidence and matching appointments."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


def test_polyline_and_fastest_route_with_delay():
    from places.briefing import decode_polyline, route_choices

    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [
        (38.5, -120.2), (40.7, -120.95), (43.252, -126.453),
    ]
    assert decode_polyline("_p~iF~ps|") == []
    choices = route_choices([
        {"duration_seconds": 1800, "delay_seconds": 600},
        {"duration_seconds": 1440, "delay_seconds": 120},
    ])
    assert choices[1]["recommended"] is True
    assert choices[0]["recommended"] is False
    assert choices[0]["delay_minutes"] == 10
    assert "6 minuti" in choices[0]["reason"]


@pytest.mark.asyncio
async def test_google_routes_requests_alternatives_and_keeps_geometry(monkeypatch):
    from places import routing

    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {"routes": [
                {"duration": "1800s", "staticDuration": "1200s", "distanceMeters": 18000,
                 "polyline": {"encodedPolyline": "route-a"}},
                {"duration": "1500s", "staticDuration": "1400s", "distanceMeters": 20000,
                 "polyline": {"encodedPolyline": "route-b"}},
            ]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers, content):
            import json
            captured.update(json.loads(content))
            assert "routes.polyline.encodedPolyline" in headers["X-Goog-FieldMask"]
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    result = await routing._google_routes({"latitude": 45, "longitude": 9},
                                          {"latitude": 46, "longitude": 10}, "drive",
                                          alternatives=True)
    assert captured["computeAlternativeRoutes"] is True
    assert result["duration_seconds"] == 1500
    assert result["alternatives"][0]["delay_seconds"] == 600
    assert result["alternatives"][1]["polyline"] == "route-b"


@pytest.mark.asyncio
async def test_route_weather_samples_actual_geometry(monkeypatch):
    from datetime import datetime, timezone
    from places import briefing

    seen = {}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = [(now.replace(hour=0) + __import__("datetime").timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
             for i in range(48)]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"hourly": {"time": hours, "weather_code": [61] * 48,
                                "precipitation_probability": [75] * 48,
                                "temperature_2m": [12] * 48}} for _ in range(3)]

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            seen.update(params)
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    monkeypatch.setattr("weather.configured_provider", lambda: "open_meteo")
    samples = await briefing.weather_along_route("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 1800)
    assert len(seen["latitude"].split(",")) == 3
    assert len(samples) == 3
    assert samples[1]["label"] == "Lungo il tragitto"
    assert samples[1]["rain_chance_pct"] == 75
