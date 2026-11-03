"""Open-Meteo: the forecast from three models, marine data and the wind map's grid.

One request covers every spot. Times are requested as Unix seconds in UTC,
with a day of past hours so the timeline can start at local midnight
anywhere. The wind map's grid is one request for all its points, from
Open-Meteo's best model for the place, with no past hours.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import aiohttp

from . import ProviderError, fetch_json, from_unix

FORECAST_URL: Final = "https://api.open-meteo.com/v1/forecast"
MARINE_URL: Final = "https://marine-api.open-meteo.com/v1/marine"

# ECMWF IFS (9 km), GFS (HRRR for about 40 hours in the US) and ICON.
MODELS: Final = ("ecmwf_ifs", "ncep_gfs_seamless", "dwd_icon_seamless")
FORECAST_VARIABLES: Final = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
    "precipitation_probability",
    "weather_code",
    "visibility",
    "cape",
)
MARINE_VARIABLES: Final = (
    "wave_height",
    "wave_period",
    "wave_direction",
    "sea_surface_temperature",
)
WIND_VARIABLES: Final = ("wind_speed_10m", "wind_direction_10m", "wind_gusts_10m")
PAST_DAYS: Final = 1
FORECAST_DAYS: Final = 7

type Values = tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class Forecast:
    """One place's hourly forecast.

    `values[variable]` holds one series per model, in the order of MODELS.
    """

    times: tuple[datetime, ...]
    values: Mapping[str, tuple[Values, ...]]

    def at(self, variable: str, index: int) -> Values:
        """Return each model's value of a variable for one hour."""
        return tuple(series[index] for series in self.values[variable])


@dataclass(frozen=True, slots=True)
class Marine:
    """One place's hourly marine forecast."""

    times: tuple[datetime, ...]
    values: Mapping[str, Values]


@dataclass(frozen=True, slots=True)
class WindPoints:
    """Hourly wind at many points: one series per point for each variable.

    Speeds are in knots, and directions in degrees the wind comes from.
    """

    times: tuple[datetime, ...]
    speed: tuple[Values, ...]
    direction: tuple[Values, ...]
    gust: tuple[Values, ...]


def calls(variables: int, points: int, days: int = PAST_DAYS + FORECAST_DAYS) -> float:
    """Return how many calls Open-Meteo counts for a request.

    Each place counts max(1, V/10 x max(1, D/14)), where V is the number of
    variables times models.
    """
    return points * max(1.0, variables / 10 * max(1.0, days / 14))


def forecast_calls(points: int) -> float:
    """Return the calls counted for one forecast request."""
    return calls(len(FORECAST_VARIABLES) * len(MODELS), points)


def marine_calls(points: int) -> float:
    """Return the calls counted for one marine request."""
    return calls(len(MARINE_VARIABLES), points)


def wind_calls(points: int) -> float:
    """Return the calls counted for one wind grid request."""
    return calls(len(WIND_VARIABLES), points, FORECAST_DAYS)


async def async_get_forecast(
    session: aiohttp.ClientSession, points: Sequence[tuple[float, float]]
) -> list[Forecast]:
    """Return the hourly forecast for each point."""
    payload = await fetch_json(
        session,
        FORECAST_URL,
        _params(points, FORECAST_VARIABLES)
        | {"models": ",".join(MODELS), "wind_speed_unit": "kn"},
    )
    return parse_forecast(payload, len(points))


async def async_get_marine(
    session: aiohttp.ClientSession, points: Sequence[tuple[float, float]]
) -> list[Marine]:
    """Return the hourly marine forecast for each point, from the nearest sea."""
    payload = await fetch_json(
        session,
        MARINE_URL,
        _params(points, MARINE_VARIABLES) | {"cell_selection": "sea"},
    )
    return parse_marine(payload, len(points))


async def async_get_wind(
    session: aiohttp.ClientSession, points: Sequence[tuple[float, float]]
) -> WindPoints:
    """Return the hourly wind at each point, from now for a week."""
    payload = await fetch_json(
        session,
        FORECAST_URL,
        _params(points, WIND_VARIABLES) | {"past_days": 0, "wind_speed_unit": "kn"},
    )
    return parse_wind(payload, len(points))


def parse_forecast(payload: Any, count: int) -> list[Forecast]:
    """Read a forecast response for `count` points."""
    forecasts = []
    for place in _places(payload, count):
        hourly = place["hourly"]
        forecasts.append(
            Forecast(
                times=_times(hourly),
                values={
                    variable: tuple(
                        _series(hourly, f"{variable}_{model}") for model in MODELS
                    )
                    for variable in FORECAST_VARIABLES
                },
            )
        )
    return forecasts


def parse_marine(payload: Any, count: int) -> list[Marine]:
    """Read a marine response for `count` points."""
    return [
        Marine(
            times=_times(place["hourly"]),
            values={
                variable: _series(place["hourly"], variable)
                for variable in MARINE_VARIABLES
            },
        )
        for place in _places(payload, count)
    ]


def parse_wind(payload: Any, count: int) -> WindPoints:
    """Read a wind response for `count` points."""
    places = _places(payload, count)
    times = _times(places[0]["hourly"])
    if any(len(place["hourly"]["time"]) != len(times) for place in places):
        raise ProviderError("Open-Meteo returned points with different hours")
    return WindPoints(
        times=times,
        speed=tuple(_series(place["hourly"], "wind_speed_10m") for place in places),
        direction=tuple(
            _series(place["hourly"], "wind_direction_10m") for place in places
        ),
        gust=tuple(_series(place["hourly"], "wind_gusts_10m") for place in places),
    )


def _params(
    points: Sequence[tuple[float, float]], variables: Sequence[str]
) -> dict[str, str | int | float]:
    return {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        "hourly": ",".join(variables),
        "timeformat": "unixtime",
        "timezone": "GMT",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
    }


def _places(payload: Any, count: int) -> list[dict[str, Any]]:
    """Return the per-place results; a single place comes back unwrapped."""
    places = payload if isinstance(payload, list) else [payload]
    if len(places) != count or not all(
        isinstance(place, dict) and "hourly" in place for place in places
    ):
        raise ProviderError(f"Open-Meteo returned {len(places)} places, not {count}")
    return places


def _times(hourly: Mapping[str, Any]) -> tuple[datetime, ...]:
    return tuple(from_unix(seconds) for seconds in hourly["time"])


def _series(hourly: Mapping[str, Any], key: str) -> Values:
    """Return one series, or nothing for each hour if the model lacks it."""
    values = hourly.get(key)
    if values is None:
        return (None,) * len(hourly["time"])
    if len(values) != len(hourly["time"]):
        raise ProviderError(f"Open-Meteo returned a short series for {key}")
    return tuple(None if value is None else float(value) for value in values)
