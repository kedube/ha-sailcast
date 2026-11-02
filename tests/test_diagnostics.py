"""Tests for SailCast's diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Diagnostics show each source's status without showing where anyone sails."""
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
    ):
        assert private not in text, private
    assert diagnostics["sources"]["SailCast forecast"]["last_update_success"]
    assert diagnostics["sources"]["SailCast warnings"]["update_interval"] == 300
    assert diagnostics["open_meteo_calls_today"] == 9.2
    assert diagnostics["results"]["outlooks"] == 6
    assert [spot["hours"] for spot in diagnostics["results"]["spots"]] == [160] * 3
    spot = diagnostics["profiles"]["spots"][0]
    assert spot["latitude"] == "**REDACTED**"
    assert spot["water_type"] == "bay"
