"""Kartverket: Norwegian tide predictions.

Kartverket's tide API takes a position and answers from the nearest
reference station, corrected for the position, in centimeters above chart
datum. A position outside Norway's waters gets no data. Its data is under
Creative Commons Attribution 4.0, credited as ©Kartverket.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from typing import Final

import aiohttp

from . import ProviderError, TideEvent, Tides, fetch_bytes

API: Final = "https://vannstand.kartverket.no/tideapi.php"
PREFIX: Final = "kartverket"
DAYS: Final = 10
DATUM: Final = "CD"
NOTICE: Final = "©Kartverket"
# Norway's coast, roughly, so other places aren't asked.
AREA: Final = (57.5, 81.5, 4.0, 32.0)
_LEVEL = re.compile(r'<waterlevel value="([-\d.]+)" time="([^"]+)" flag="(\w+)"')
_STATION = re.compile(r'<location name="([^"]*)"')


class NoDataError(ProviderError):
    """Kartverket has no tides for a position."""


def covers(latitude: float, longitude: float) -> bool:
    """Return whether a position is near enough Norway to ask about."""
    south, north, west, east = AREA
    return south <= latitude <= north and west <= longitude <= east


async def async_get_tides(
    session: aiohttp.ClientSession, latitude: float, longitude: float, begin: datetime
) -> Tides:
    """Return ten days of highs and lows and hourly heights at a position."""

    async def ask(**params: str) -> str:
        url = (
            f"{API}?tide_request=locationdata&lat={latitude:.4f}&lon={longitude:.4f}"
            f"&fromtime={_time(begin)}&totime={_time(begin + timedelta(days=DAYS))}"
            "&refcode=cd&tzone=0&lang=en&"
            + "&".join(f"{key}={value}" for key, value in params.items())
        )
        return (await fetch_bytes(session, url)).decode("utf-8", "replace")

    extremes = await ask(datatype="tab")
    hourly = await ask(datatype="pre", interval="60")
    return parse_tides(extremes, hourly, source(latitude, longitude))


async def async_station_at(
    session: aiohttp.ClientSession, latitude: float, longitude: float, day: datetime
) -> str | None:
    """Return the station Kartverket answers for a position from, if any."""
    url = (
        f"{API}?tide_request=locationdata&lat={latitude:.4f}&lon={longitude:.4f}"
        f"&fromtime={_time(day)}&totime={_time(day + timedelta(days=1))}"
        "&datatype=tab&refcode=cd&tzone=0&lang=en"
    )
    body = (await fetch_bytes(session, url)).decode("utf-8", "replace")
    if "<nodata" in body or not (match := _STATION.search(body)):
        return None
    return match.group(1)


def source(latitude: float, longitude: float) -> str:
    """Return the ID Kartverket's predictions at a pin are kept under."""
    return f"{PREFIX}:{latitude:.4f},{longitude:.4f}"


def parse_tides(extremes: str, hourly: str, station: str) -> Tides:
    """Read highs and lows and hourly heights, in meters above chart datum."""
    if "<nodata" in extremes:
        raise NoDataError("Kartverket has no tides for this position")
    try:
        events = tuple(
            TideEvent(_parse_time(when), round(float(value) / 100, 3), flag == "high")
            for value, when, flag in _LEVEL.findall(extremes)
            if flag in ("high", "low")
        )
        heights = tuple(
            (_parse_time(when), round(float(value) / 100, 3))
            for value, when, flag in _LEVEL.findall(hourly)
            if flag == "pre"
        )
    except ValueError as err:
        raise ProviderError(f"Unexpected Kartverket tides: {err}") from err
    if not events:
        raise ProviderError("Kartverket sent no tides")
    name = match.group(1) if (match := _STATION.search(extremes)) else None
    return Tides(station, events, heights, datum=DATUM, name=name, notice=NOTICE)


def _time(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)
