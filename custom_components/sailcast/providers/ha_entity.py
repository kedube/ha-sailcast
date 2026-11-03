"""Your own sensors: a weather station or a boat's instruments, as readings.

Each field a spot uses can come from any Home Assistant sensor. Values are
converted from the sensor's unit, and each is timed by when the sensor last
reported, so a sensor that stops reporting expires like a buoy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_conversion import SpeedConverter, TemperatureConverter

from . import Reading, Readings

SPEEDS: Final = frozenset({"wind", "gust"})
TEMPERATURES: Final = frozenset({"temperature", "water_temperature"})
DIRECTIONS: Final = frozenset({"wind_direction"})
FIELDS: Final = ("wind", "gust", "wind_direction", "temperature", "water_temperature")


def read(hass: HomeAssistant, sensors: Mapping[str, str]) -> Readings:
    """Return the sensors' latest values, leaving out any that can't be read."""
    fields: dict[str, Reading] = {}
    for key, entity_id in sensors.items():
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            continue
        try:
            value = convert(
                key, float(state.state), state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            )
        except HomeAssistantError, ValueError:
            continue
        if value is not None:
            fields[key] = Reading(value, state.last_reported)
    return Readings(fields)


def convert(key: str, value: float, unit: str | None) -> float | None:
    """Return a sensor's value in SailCast's units, or None for an unknown field.

    A sensor without a unit is taken to be in knots or °C already.
    """
    if key in SPEEDS:
        return SpeedConverter.convert(
            value, unit or UnitOfSpeed.KNOTS, UnitOfSpeed.KNOTS
        )
    if key in TEMPERATURES:
        return TemperatureConverter.convert(
            value, unit or UnitOfTemperature.CELSIUS, UnitOfTemperature.CELSIUS
        )
    if key in DIRECTIONS:
        return value % 360
    return None
