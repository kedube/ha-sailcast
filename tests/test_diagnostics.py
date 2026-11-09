"""Tests for SailCast's diagnostics."""

from __future__ import annotations

import json

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.diagnostics import (
    async_get_config_entry_diagnostics,
    safe_error,
)
from custom_components.sailcast.providers import ProviderError

from .conftest import WORLDTIDES_KEY, mock_world, set_up_abroad


async def test_diagnostics(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Diagnostics show each source's status without showing where anyone sails."""
    sailor = loaded.subentries["sailor_alex"]
    spot = loaded.subentries["spot_harbor"]
    hass.config_entries.async_update_subentry(
        loaded,
        sailor,
        data=dict(sailor.data)
        | {
            "user": "user_alex",
            "auto_calendar": {
                "calendar": "calendar.alex_family",
                "days": ["sat"],
                "min_score": 60,
                "ahead": 2,
                "spots": ["spot_harbor"],
            },
        },
    )
    # Each change reloads the entry; two changes at once can share a reload.
    await hass.async_block_till_done()
    hass.config_entries.async_update_subentry(
        loaded,
        spot,
        data=dict(spot.data) | {"source_names": {"tide_station": "Point Loma"}},
    )
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded)
    text = json.dumps(diagnostics)
    for private in (
        "32.75",
        "117.27",
        "9410170",
        "PCT0056",
        "PZZ740",
        "Harbor",
        "Alex",
        "user_alex",
        "Point Loma",
    ):
        assert private not in text, private
    assert diagnostics["sources"]["SailCast forecast"]["last_update_success"]
    assert diagnostics["sources"]["SailCast warnings"]["update_interval"] == 300
    # The entry reloaded twice, fetching the forecast, marine data and the
    # ensemble's spread each time, and the count keeps going.
    assert diagnostics["open_meteo_calls_today"] == 36.6
    assert diagnostics["planned_sails"] == 0
    assert diagnostics["wind_grids"] == []
    assert diagnostics["results"]["outlooks"] == 6
    assert [spot["hours"] for spot in diagnostics["results"]["spots"]] == [160] * 3
    spot = diagnostics["profiles"]["spots"][0]
    assert spot["latitude"] == "**REDACTED**"
    assert spot["water_type"] == "bay"


async def test_diagnostics_with_readings(
    hass: HomeAssistant, observed: MockConfigEntry
) -> None:
    """Buoys, airports and sensors show by kind only, shorelines without places."""
    diagnostics = await async_get_config_entry_diagnostics(hass, observed)
    text = json.dumps(diagnostics)
    for private in ("46258", "SDBC1", "KSAN", "KNZY", "Mission Bay", "32.749"):
        assert private not in text, private
    assert [reading["kind"] for reading in diagnostics["readings"]] == [
        "buoy",
        "airport",
        "buoy",
        "airport",
    ]
    assert diagnostics["readings"][0]["fields"] == [
        "water_temperature",
        "wave_direction",
        "wave_height",
        "wave_period",
    ]
    spots = diagnostics["results"]["spots"]
    assert [spot["shoreline"]["on_water"] for spot in spots] == [True, False, True]
    assert spots[2]["wave_sources"] == ["estimate"]
    assert "wind" in spots[2]["nudged"]


def test_errors_without_addresses() -> None:
    """Errors keep their kind and host, not the address or a position."""
    error = ProviderError(
        "https://www.ndbc.noaa.gov/data/realtime2/46258.txt returned 404"
    )
    assert safe_error(error) == "ProviderError: www.ndbc.noaa.gov returned 404"
    assert safe_error(ValueError("near 32.7500,-117.2700")) == "ValueError: near …,…"
    assert safe_error(None) is None


def test_errors_without_stations() -> None:
    """Errors leave out every station and zone the spots use."""
    error = ProviderError(
        "Rijkswaterstaat has no predictions for rws:harlingen.waddenzee: busy"
    )
    assert (
        safe_error(error, {"rws:harlingen.waddenzee", "harlingen.waddenzee"})
        == "ProviderError: Rijkswaterstaat has no predictions for …: busy"
    )


async def test_diagnostics_abroad(
    hass: HomeAssistant,
    world_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Diagnostics say a key is set and where tides come from, never the key."""
    mock_world(aioclient_mock)
    await set_up_abroad(hass, world_entry, freezer)
    diagnostics = await async_get_config_entry_diagnostics(hass, world_entry)
    text = json.dumps(diagnostics)
    for private in (WORLDTIDES_KEY, "harlingen", "50.785", "53.18", "Wadden"):
        assert private not in text, private
    assert diagnostics["worldtides_key_set"]
    spots = diagnostics["results"]["spots"]
    assert {spot["tide_provider"] for spot in spots} == {"worldtides", "rws", None}
    assert {spot["warnings_provider"] for spot in spots} == {"meteoalarm"}
