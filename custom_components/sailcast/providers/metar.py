"""Airport weather reports (METAR) from aviationweather.gov.

Airports are found in a box around a spot. One request gets every airport's
latest report, with wind in knots and visibility in statute miles, which can
be written as "10+" for ten miles or more.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any, Final

import aiohttp

from . import ProviderError, Reading, Readings, fetch_json, from_unix

STATIONINFO_URL: Final = "https://aviationweather.gov/api/data/stationinfo"
METAR_URL: Final = "https://aviationweather.gov/api/data/metar"
METERS_PER_STATUTE_MILE: Final = 1609.344


@dataclass(frozen=True, slots=True)
class Airport:
    """An airport that sends weather reports."""

    id: str
    name: str
    latitude: float
    longitude: float


async def async_airports_near(
    session: aiohttp.ClientSession, latitude: float, longitude: float, km: float
) -> list[Airport]:
    """Return the airports with weather reports within a box around a point."""
    lat_span = km / 111.195
    lon_span = km / (111.195 * max(0.01, math.cos(math.radians(latitude))))
    payload = await fetch_json(
        session,
        STATIONINFO_URL,
        {
            "bbox": (
                f"{latitude - lat_span:.4f},{longitude - lon_span:.4f},"
                f"{latitude + lat_span:.4f},{longitude + lon_span:.4f}"
            ),
            "format": "json",
        },
    )
    return parse_airports(payload)


async def async_get_reports(
    session: aiohttp.ClientSession, stations: Collection[str]
) -> dict[str, Readings]:
    """Return each airport's latest report, by airport."""
    payload = await fetch_json(
        session, METAR_URL, {"ids": ",".join(sorted(stations)), "format": "json"}
    )
    return parse_reports(payload)


def parse_airports(payload: Any) -> list[Airport]:
    """Read stations in a box, keeping the airports that send reports."""
    if not isinstance(payload, list):
        raise ProviderError("aviationweather.gov sent no list of stations")
    airports = []
    for station in payload:
        if not isinstance(station, dict) or "METAR" not in (
            station.get("siteType") or ()
        ):
            continue
        try:
            airports.append(
                Airport(
                    id=str(station["icaoId"]),
                    name=str(station.get("site") or station["icaoId"]).strip(),
                    latitude=float(station["lat"]),
                    longitude=float(station["lon"]),
                )
            )
        except KeyError, TypeError, ValueError:
            continue
    return airports


def parse_reports(payload: Any) -> dict[str, Readings]:
    """Read reports, keeping each airport's newest."""
    if not isinstance(payload, list):
        raise ProviderError("aviationweather.gov sent no list of reports")
    newest: dict[str, dict[str, Any]] = {}
    for report in payload:
        if not isinstance(report, dict) or not isinstance(report.get("obsTime"), int):
            continue
        station = report.get("icaoId")
        if station and report["obsTime"] > newest.get(station, {}).get("obsTime", 0):
            newest[station] = report
    return {station: _readings(report) for station, report in newest.items()}


def _readings(report: dict[str, Any]) -> Readings:
    time = from_unix(report["obsTime"])
    fields: dict[str, Reading] = {}
    wind = _number(report.get("wspd"))
    if wind is not None:
        fields["wind"] = Reading(wind, time)
        # Reports leave gusts out unless they're well over the mean wind, so
        # a missing gust says nothing about how gusty it is.
        if (gust := _number(report.get("wgst"))) is not None:
            fields["gust"] = Reading(max(wind, gust), time)
        # Calm air has no direction, and VRB means it keeps changing.
        direction = _number(report.get("wdir"))
        if direction is not None and wind > 0:
            fields["wind_direction"] = Reading(direction % 360, time)
    if (temperature := _number(report.get("temp"))) is not None:
        fields["temperature"] = Reading(temperature, time)
    if (miles := visibility_miles(report.get("visib"))) is not None:
        fields["visibility"] = Reading(miles * METERS_PER_STATUTE_MILE, time)
    return Readings(fields)


def visibility_miles(value: Any) -> float | None:
    """Return a report's visibility in statute miles.

    It's a number, or text such as "10+" (ten or more), "1/2" or "1 1/2".
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().rstrip("+").removeprefix("M").removeprefix("P")
    if not text:
        return None
    try:
        return float(sum(Fraction(part) for part in text.split()))
    except ValueError, ZeroDivisionError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
