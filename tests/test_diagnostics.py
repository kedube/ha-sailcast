"""Tests for SailCast's diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast.diagnostics import async_get_config_entry_diagnostics


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
    # The entry reloaded twice, fetching the forecast and marine data each
    # time, and the count keeps going.
    assert diagnostics["open_meteo_calls_today"] == 27.6
    assert diagnostics["planned_sails"] == 0
    assert diagnostics["results"]["outlooks"] == 6
    assert [spot["hours"] for spot in diagnostics["results"]["spots"]] == [160] * 3
    spot = diagnostics["profiles"]["spots"][0]
    assert spot["latitude"] == "**REDACTED**"
    assert spot["water_type"] == "bay"
