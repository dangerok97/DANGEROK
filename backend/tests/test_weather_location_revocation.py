"""Weather/location privacy gate.

Turning ORA location off must stop using a previously stored device fix. A
saved home is not proof of where somebody is now. Weather may resume only from
a consented CURRENT/RECENT device observation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from home.service import HomeService


class _DB:
    pass


@pytest.mark.asyncio
async def test_weather_point_is_none_when_location_consent_is_off():
    fake = SimpleNamespace(
        get_preference=AsyncMock(return_value="off"),
        build_presence=AsyncMock(),
    )
    with patch("location.service.LocationService", return_value=fake):
        assert await HomeService(_DB())._where_they_are("u1") is None
        fake.build_presence.assert_not_awaited()


@pytest.mark.asyncio
async def test_weather_ignores_stale_device_position():
    presence = SimpleNamespace(
        freshness="STALE",
        latitude=41.9,
        longitude=12.5,
        place_locality="Roma",
        place_municipality=None,
        place_label="Roma",
    )
    fake = SimpleNamespace(
        get_preference=AsyncMock(return_value="while_using"),
        build_presence=AsyncMock(return_value=presence),
    )
    with patch("location.service.LocationService", return_value=fake):
        assert await HomeService(_DB())._where_they_are("u1") is None


@pytest.mark.asyncio
async def test_weather_uses_recent_consented_device_position():
    presence = SimpleNamespace(
        freshness="RECENT",
        latitude=41.9,
        longitude=12.5,
        place_locality="Roma",
        place_municipality=None,
        place_label="Roma",
    )
    fake = SimpleNamespace(
        get_preference=AsyncMock(return_value="while_using"),
        build_presence=AsyncMock(return_value=presence),
    )
    with patch("location.service.LocationService", return_value=fake):
        assert await HomeService(_DB())._where_they_are("u1") == (41.9, 12.5, "Roma")
