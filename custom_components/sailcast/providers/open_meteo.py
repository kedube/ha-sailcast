"""Open-Meteo: the forecast from three models, marine data, spread and the wind map.

One request covers every spot. Times are requested as Unix seconds in UTC,
with a day of past hours so the timeline can start at local midnight
anywhere. Buoys and airports get a lighter forecast of their own, so their
readings can be compared with the forecast for the same place. The ECMWF
ensemble's spread comes from its ensemble mean, which costs one variable. The
wind map's grid is one request for all its points, from Open-Meteo's best
model for the place, with no past hours.
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
ENSEMBLE_URL: Final = "https://ensemble-api.open-meteo.com/v1/ensemble"
SPREAD_MODEL: Final = "ecmwf_ifs025_ensemble_mean"

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
# What buoys and airports read, for comparing with the forecast there.
NEARBY_VARIABLES: Final = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
)
BUOY_VARIABLES: Final = ("wave_height", "sea_surface_temperature")
SPREAD_VARIABLE: Final = "wind_speed_10m_spread"
PAST_DAYS: Final = 1
FORECAST_DAYS: Final = 7
NEARBY_DAYS: Final = 1

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
class Spread:
    """The ECMWF ensemble's hourly wind spread at one place.

    Each value is one standard deviation of the ensemble's wind, in knots.
    """

    times: tuple[datetime, ...]
    values: Values


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


def nearby_calls(points: int) -> float:
    """Return the calls counted for the forecast at buoys and airports."""
    return calls(len(NEARBY_VARIABLES) * len(MODELS), points, PAST_DAYS + NEARBY_DAYS)


def buoy_calls(points: int) -> float:
    """Return the calls counted for marine data at buoys."""
    return calls(len(BUOY_VARIABLES), points, PAST_DAYS + NEARBY_DAYS)


def spread_calls(points: int) -> float:
    """Return the calls counted for one ensemble spread request."""
    return calls(1, points)


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


async def async_get_nearby(
    session: aiohttp.ClientSession, points: Sequence[tuple[float, float]]
) -> list[Forecast]:
    """Return today's wind and air temperature from the three models at each point."""
    payload = await fetch_json(
        session,
        FORECAST_URL,
        _params(points, NEARBY_VARIABLES)
        | {
            "models": ",".join(MODELS),
            "wind_speed_unit": "kn",
            "forecast_days": NEARBY_DAYS,
        },
    )
    return parse_forecast(payload, len(points), NEARBY_VARIABLES)


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


async def async_get_buoy_marine(
    session: aiohttp.ClientSession, points: Sequence[tuple[float, float]]
) -> list[Marine]:
    """Return today's wave height and water temperature at each buoy."""
    payload = await fetch_json(
        session,
        MARINE_URL,
        _params(points, BUOY_VARIABLES)
        | {"cell_selection": "sea", "forecast_days": NEARBY_DAYS},
    )
    return parse_marine(payload, len(points), BUOY_VARIABLES)


async def async_get_spread(
    session: aiohttp.ClientSession, points: Sequence[tuple[float, float]]
) -> list[Spread]:
    """Return the ECMWF ensemble's wind spread at each point."""
    payload = await fetch_json(
        session,
        ENSEMBLE_URL,
        _params(points, (SPREAD_VARIABLE,))
        | {"models": SPREAD_MODEL, "wind_speed_unit": "kn"},
    )
    return [
        Spread(_times(place["hourly"]), _series(place["hourly"], SPREAD_VARIABLE))
        for place in _places(payload, len(points))
    ]


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


def parse_forecast(
    payload: Any, count: int, variables: Sequence[str] = FORECAST_VARIABLES
) -> list[Forecast]:
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
                    for variable in variables
                },
            )
        )
    return forecasts


def parse_marine(
    payload: Any, count: int, variables: Sequence[str] = MARINE_VARIABLES
) -> list[Marine]:
    """Read a marine response for `count` points."""
    return [
        Marine(
            times=_times(place["hourly"]),
            values={
                variable: _series(place["hourly"], variable) for variable in variables
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
