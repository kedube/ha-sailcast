"""Tests for the sailcast.get_forecast action."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast.const import DOMAIN


async def get_forecast(hass: HomeAssistant, **data: str) -> dict[str, Any]:
    """Call the action and return its response."""
    response = await hass.services.async_call(
        DOMAIN, "get_forecast", data, blocking=True, return_response=True
    )
    assert isinstance(response, dict)
    return response


async def test_response(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """The response has the week's days and the hours from now."""
    response = await get_forecast(hass, spot="river", sailor="ALEX")
    assert response["spot"] == "River"
    assert response["sailor"] == "Alex"
    assert response["skill"] == "intermediate"
    assert response["units"] == {
        "wind": "kn",
        "current": "kn",
        "wave_height": "m",
        "tide_height": "m",
        "temperature": "°C",
    }
    assert len(response["days"]) == 7
    assert response["hours"][0]["time"] == "2026-11-02T22:00:00+00:00"
    saturday = response["days"][5]
    assert saturday["date"] == "2026-11-07"
    assert saturday["confidence"] == "high"
    assert set(saturday["ratings"]) == {
        "dinghy",
        "small_keelboat",
        "cruiser",
        "large_cruiser",
    }
    keelboat, cruiser = saturday["boats"]
    assert keelboat["boat"] == "Keelboat"
    assert cruiser["boat"] == "Cruiser"
    assert keelboat["best_window"] == {
        "start": "2026-11-07T21:00:00+00:00",
        "end": "2026-11-08T00:53:00+00:00",
        "score": 80,
    }
    hour = response["hours"][0]
    assert hour["wind"] == 6.1
    assert hour["ratings"]["small_keelboat"] == "good"
    assert [boat["boat"] for boat in hour["boats"]] == ["Keelboat", "Cruiser"]


async def test_one_boat(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Asking for one boat leaves out the others."""
    response = await get_forecast(hass, spot="Harbor", sailor="Alex", boat="cruiser")
    assert [boat["boat"] for boat in response["days"][0]["boats"]] == ["Cruiser"]
    assert [boat["boat"] for boat in response["hours"][0]["boats"]] == ["Cruiser"]


async def test_us_units(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Heights are in feet and temperatures in °F with US units."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    response = await get_forecast(hass, spot="Harbor", sailor="Alex")
    assert response["units"]["wave_height"] == "ft"
    assert response["units"]["temperature"] == "°F"
    hour = response["hours"][0]
    assert hour["wave_height"] == pytest.approx(4.53, abs=0.01)
    assert hour["wind"] == 6.1  # knots either way


@pytest.mark.parametrize(
    ("data", "key", "message"),
    [
        (
            {"spot": "Lake", "sailor": "Alex"},
            "unknown_spot",
            "There's no spot named Lake",
        ),
        (
            {"spot": "Harbor", "sailor": "Pat"},
            "unknown_sailor",
            "There's no sailor named Pat",
        ),
        (
            {"spot": "Harbor", "sailor": "Sam", "boat": "Cruiser"},
            "unknown_boat",
            "Sam doesn't sail a boat named Cruiser",
        ),
    ],
)
async def test_unknown_names(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    data: dict[str, str],
    key: str,
    message: str,
) -> None:
    """Unknown spots, sailors and boats are explained, and named."""
    with pytest.raises(ServiceValidationError) as err:
        await get_forecast(hass, **data)
    assert err.value.translation_key == key
    assert str(err.value).rstrip(".") == message


async def test_not_loaded(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Without a loaded entry, the action says so."""
    await hass.config_entries.async_unload(loaded.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await get_forecast(hass, spot="Harbor", sailor="Alex")
    assert err.value.translation_key == "not_loaded"


async def test_currents(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Currents are in knots, positive on the flood, and slack is plain 0."""
    response = await get_forecast(hass, spot="Bay", sailor="Sam")
    currents = [hour["current"] for hour in response["hours"]]
    assert max(currents) > 0 > min(currents)
    assert all(math.copysign(1, current) > 0 for current in currents if current == 0)
