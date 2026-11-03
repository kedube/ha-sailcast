"""NOAA CO-OPS: US tide and current predictions, and station lists.

Predictions are requested in UTC, tides in meters above MLLW and currents in
knots. Harmonic tide stations give hourly heights; subordinate stations give
only highs and lows. Current stations give slack and peak times, whatever
interval is asked for, so the hours in between are interpolated later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import aiohttp

from . import ProviderError, Station, TideEvent, Tides, fetch_json

DATA_URL: Final = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
STATIONS_URL: Final = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi"
APPLICATION: Final = "SailCast"
HOURS: Final = 240  # ten days


@dataclass(frozen=True, slots=True)
class CurrentEvent:
    """A slack, or the peak of a flood or ebb, in knots.

    Speed is positive on the flood and negative on the ebb.
    """

    time: datetime
    speed: float


@dataclass(frozen=True, slots=True)
class Currents:
    """A current station's predictions and the directions its water flows to."""

    station: str
    events: tuple[CurrentEvent, ...]
    flood_direction: float | None
    ebb_direction: float | None


async def async_get_tides(
    session: aiohttp.ClientSession, station: str, begin: date
) -> Tides:
    """Return ten days of tide predictions from `begin`."""
    events = parse_tide_events(
        await _predictions(session, station, begin, "hilo"), station
    )
    hourly = await _predictions(session, station, begin, "h")
    # Subordinate stations answer hourly requests with an error.
    if "error" in hourly:
        return Tides(station, events)
    return Tides(station, events, parse_tide_heights(hourly, station))


async def async_get_currents(
    session: aiohttp.ClientSession, station: str, begin: date
) -> Currents:
    """Return ten days of current predictions from `begin`.

    `station` is a station ID and depth bin, such as "PCT0056_1".
    """
    station_id, _, depth_bin = station.partition("_")
    payload = await fetch_json(
        session,
        DATA_URL,
        _params(begin)
        | {
            "product": "currents_predictions",
            "station": station_id,
            "bin": depth_bin or "1",
            "units": "english",
            "interval": "MAX_SLACK",
        },
    )
    return parse_currents(payload, station)


async def async_tide_stations_near(
    session: aiohttp.ClientSession, latitude: float, longitude: float, miles: int
) -> list[Station]:
    """Return the tide prediction stations within a radius, nearest first."""
    payload = await fetch_json(
        session,
        f"{STATIONS_URL}/tidepredstations.json",
        {"lat": latitude, "lon": longitude, "radius": miles},
    )
    try:
        return [
            Station(
                id=item["stationId"],
                name=item["name"],
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
            )
            # Far from any station, the list is null.
            for item in sorted(
                payload["stationList"] or (), key=lambda item: item["distance"]
            )
        ]
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected tide station list: {err}") from err


async def async_current_stations(session: aiohttp.ClientSession) -> list[Station]:
    """Return every current prediction station, one per station and depth bin.

    Stations whose current is weak and variable have no predictions, so
    they're left out.
    """
    payload = await fetch_json(
        session, f"{STATIONS_URL}/stations.json", {"type": "currentpredictions"}
    )
    try:
        return [
            Station(
                id=f"{item['id']}_{item['currbin']}",
                name=item["name"],
                latitude=float(item["lat"]),
                longitude=float(item["lng"]),
            )
            for item in payload["stations"]
            if item.get("type") != "W"
        ]
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected current station list: {err}") from err


def parse_tide_events(payload: Any, station: str) -> tuple[TideEvent, ...]:
    """Read high and low tides."""
    try:
        return tuple(
            TideEvent(_time(item["t"]), float(item["v"]), item["type"] == "H")
            for item in _checked(payload, station)["predictions"]
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected tides for {station}: {err}") from err


def parse_tide_heights(
    payload: Any, station: str
) -> tuple[tuple[datetime, float], ...]:
    """Read hourly tide heights."""
    try:
        return tuple(
            (_time(item["t"]), float(item["v"]))
            for item in _checked(payload, station)["predictions"]
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected tides for {station}: {err}") from err


def parse_currents(payload: Any, station: str) -> Currents:
    """Read slack and peak current times."""
    try:
        items = _checked(payload, station)["current_predictions"]["cp"]
        first = items[0] if items else {}
        return Currents(
            station=station,
            events=tuple(
                CurrentEvent(_time(item["Time"]), float(item["Velocity_Major"]))
                for item in items
            ),
            flood_direction=_direction(first.get("meanFloodDir")),
            ebb_direction=_direction(first.get("meanEbbDir")),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected currents for {station}: {err}") from err


async def _predictions(
    session: aiohttp.ClientSession, station: str, begin: date, interval: str
) -> Any:
    return await fetch_json(
        session,
        DATA_URL,
        _params(begin)
        | {
            "product": "predictions",
            "station": station,
            "datum": "MLLW",
            "units": "metric",
            "interval": interval,
        },
    )


def _params(begin: date) -> dict[str, str | int | float]:
    return {
        "application": APPLICATION,
        "begin_date": begin.strftime("%Y%m%d"),
        "range": HOURS,
        "time_zone": "gmt",
        "format": "json",
    }


def _checked(payload: Any, station: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProviderError(f"Unexpected response for {station}")
    if "error" in payload:
        message = payload["error"].get("message", payload["error"])
        raise ProviderError(f"NOAA has no predictions for {station}: {message}")
    return payload


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def _direction(value: Any) -> float | None:
    return None if value in (None, "") else float(value) % 360
