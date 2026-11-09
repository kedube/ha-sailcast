"""Nudging the next hours toward what buoys, airports and your own sensors read.

When a reading is fresh, SailCast compares it with the forecast for the same
place and time, and moves the spot's forecast by the difference, fading to
nothing over six hours. Buoys and airports have a forecast of their own;
your sensors are taken to be at the spot. A buoy's wind and gusts arrive
already scaled to the 10 m that forecasts give (see providers/ndbc.py). Each
field expires on its own and comes from the best source that has it: your
sensors, then the buoy, then the airport. Without a gust reading, gusts move
with the wind.

A measured visibility replaces the forecast's for the hour under way. Only a
measured visibility can make an hour dangerous.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import statistics
from typing import TYPE_CHECKING, Any, Final

from .geo import mean_direction
from .providers import Reading, Readings

if TYPE_CHECKING:
    from .providers.open_meteo import Forecast, Marine

HOUR: Final = timedelta(hours=1)
FADE: Final = timedelta(hours=6)
# A reading a little ahead of the clock still counts.
AHEAD: Final = timedelta(minutes=10)
# Wind directions mean little in lighter air than this (kt).
LIGHT_AIR: Final = 3.0

SENSORS: Final = "sensors"
BUOY: Final = "buoy"
AIRPORT: Final = "airport"

# How long each field's reading stays fresh, and its sources, best first.
FIELDS: Final = {
    "wind": (timedelta(hours=2), (SENSORS, BUOY, AIRPORT)),
    "gust": (timedelta(hours=2), (SENSORS, BUOY, AIRPORT)),
    "wind_direction": (timedelta(hours=2), (SENSORS, BUOY, AIRPORT)),
    "temperature": (timedelta(hours=2), (SENSORS, BUOY, AIRPORT)),
    "water_temperature": (timedelta(hours=6), (SENSORS, BUOY)),
    "wave_height": (timedelta(hours=3), (BUOY,)),
    "wave_period": (timedelta(hours=3), (BUOY,)),
    "visibility": (timedelta(hours=2), (AIRPORT, BUOY)),
}
# The fields that nudge the forecast, and the forecast variable each matches.
WEATHER: Final = {
    "wind": "wind_speed_10m",
    "gust": "wind_gusts_10m",
    "wind_direction": "wind_direction_10m",
    "temperature": "temperature_2m",
}
SEA: Final = {
    "wave_height": "wave_height",
    "water_temperature": "sea_surface_temperature",
}


@dataclass(frozen=True, slots=True)
class Observation:
    """One source's readings, and the forecast where it is.

    Sensors have no forecast of their own: they're at the spot.
    """

    kind: str
    station: str | None
    readings: Readings
    forecast: Forecast | None = None
    marine: Marine | None = None


@dataclass(frozen=True, slots=True)
class Adjustment:
    """A field moved toward a reading, by the difference from the forecast."""

    field: str
    kind: str
    station: str | None
    reading: float
    time: datetime
    difference: float

    def as_dict(self) -> dict[str, Any]:
        """Return the adjustment as JSON-ready data."""
        return {
            "field": self.field,
            "kind": self.kind,
            "station": self.station,
            "reading": self.reading,
            "time": self.time.isoformat(),
            "difference": self.difference,
        }


def latest(
    observations: Sequence[Observation], now: datetime
) -> dict[str, tuple[Observation, Reading]]:
    """Return each field's freshest reading, from its best source."""
    chosen = {}
    for key, (fresh, kinds) in FIELDS.items():
        for kind in kinds:
            found = [
                (observation, reading)
                for observation in observations
                if observation.kind == kind
                and (reading := observation.readings.get(key)) is not None
                and now - fresh <= reading.time <= now + AHEAD
            ]
            if found:
                chosen[key] = max(found, key=lambda pair: pair[1].time)
                break
    return chosen


def nudge(
    rows: Sequence[MutableMapping[str, Any]],
    chosen: dict[str, tuple[Observation, Reading]],
    *,
    forecast: Forecast | None,
    marine: Marine | None,
    now: datetime,
) -> tuple[Adjustment, ...]:
    """Move the spot's hours toward the chosen readings, and say how."""
    adjustments = []
    for key in (*WEATHER, *SEA):
        if key not in chosen:
            continue
        observation, reading = chosen[key]
        expected = _expected(key, observation, forecast, marine, reading.time)
        if expected is None:
            continue
        if key == "wind_direction":
            wind = chosen.get("wind")
            if wind is None or wind[1].value < LIGHT_AIR:
                continue
            difference = (reading.value - expected + 180) % 360 - 180
        else:
            difference = reading.value - expected
        _spread(rows, key, difference, reading.time)
        if key == "wind" and "gust" not in chosen:
            _spread(rows, "gust", difference, reading.time)
        adjustments.append(
            Adjustment(
                key,
                observation.kind,
                observation.station,
                reading.value,
                reading.time,
                difference,
            )
        )
    for row in rows:
        if {"wind", "gust"} & set(row.get("adjusted", ())):
            row["gust"] = max(row["gust"], row["wind"])
    if "visibility" in chosen:
        reading = chosen["visibility"][1]
        for row in rows:
            if row["start"] <= now < row["start"] + HOUR:
                row.update(visibility=reading.value, visibility_measured=True)
    return tuple(adjustments)


def _spread(
    rows: Sequence[MutableMapping[str, Any]],
    key: str,
    difference: float,
    since: datetime,
) -> None:
    """Add a difference to the hours from a reading on, fading over six hours."""
    for row in rows:
        if row["start"] + HOUR <= since:
            continue
        weight = 1 - (max(row["start"] + HOUR / 2, since) - since) / FADE
        if weight <= 0:
            break
        value = row.get(key)
        if value is None:
            continue
        shift = weight * difference
        if key == "wind_direction":
            row[key] = (value + shift) % 360
        elif key in ("wind", "gust", "wave_height"):
            row[key] = max(0.0, value + shift)
        else:
            row[key] = value + shift
        if key == "wind":
            row["wind_models"] = tuple(
                None if model is None else max(0.0, model + shift)
                for model in row.get("wind_models", ())
            )
        if key not in row.get("adjusted", ()):
            row["adjusted"] = (*row.get("adjusted", ()), key)


def _expected(
    key: str,
    observation: Observation,
    forecast: Forecast | None,
    marine: Marine | None,
    when: datetime,
) -> float | None:
    """Return what was forecast for a reading's place and time."""
    at_spot = observation.kind == SENSORS
    if key in WEATHER:
        source = observation.forecast or (forecast if at_spot else None)
        if source is None or WEATHER[key] not in source.values:
            return None
        variable = WEATHER[key]
        if key == "wind_direction":
            return _nearest(source.times, lambda index: _direction(source, index), when)
        return _between(
            source.times, lambda index: _middle(source.at(variable, index)), when
        )
    sea = observation.marine or (marine if at_spot else None)
    if sea is None or SEA[key] not in sea.values:
        return None
    series = sea.values[SEA[key]]
    return _between(sea.times, lambda index: series[index], when)


def _between(
    times: Sequence[datetime], value: Callable[[int], float | None], when: datetime
) -> float | None:
    """Return a value between the hours around a time."""
    index = bisect_right(times, when) - 1
    if index < 0 or index >= len(times):
        return None
    before = value(index)
    if index + 1 == len(times):
        return before
    after = value(index + 1)
    if before is None or after is None:
        return before if after is None else after
    fraction = (when - times[index]) / (times[index + 1] - times[index])
    return before + (after - before) * fraction


def _nearest(
    times: Sequence[datetime], value: Callable[[int], float | None], when: datetime
) -> float | None:
    """Return the value at the hour nearest a time."""
    index = bisect_right(times, when + HOUR / 2) - 1
    if index < 0 or index >= len(times):
        return None
    return value(index)


def _direction(forecast: Forecast, index: int) -> float | None:
    values = forecast.at(WEATHER["wind_direction"], index)
    if all(value is None for value in values):
        return None
    return mean_direction(values)


def _middle(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return statistics.median(known) if known else None
