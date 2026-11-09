"""NDBC: readings from buoys and coastal stations, and where they are.

Each station's realtime file holds 45 days, newest first. NDBC answers range
requests, so SailCast reads only the first 8 KB, which is the last several
hours. "MM" means missing. Fields arrive on their own schedules, so each
field's newest value is kept with its own time.

Forecasts give the wind 10 m above the water, but a buoy's anemometer is
about 3 to 5 m up, where the wind is some 8 to 12% lighter, and a pier's can
be 20 m up. Each station's page says how high its anemometer is, and its
wind and gusts are scaled to 10 m along the log wind profile over open water.
A station whose page doesn't say is left as it reads.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import html
import math
import re
from typing import Final

import aiohttp

from . import ProviderError, Reading, Readings, fetch_bytes

STATIONS_URL: Final = "https://www.ndbc.noaa.gov/activestations.xml"
REALTIME_URL: Final = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"
STATION_PAGE_URL: Final = "https://www.ndbc.noaa.gov/station_page.php?station={station}"
READ_BYTES: Final = 8192
PAGE_BYTES: Final = 262_144
# The height forecasts give the wind at, and the roughness of open water (m).
STANDARD_HEIGHT: Final = 10.0
ROUGHNESS: Final = 0.0002
# Higher than this, the profile over open water no longer fits (m).
HIGHEST: Final = 30.0
KNOTS_PER_METER_PER_SECOND: Final = 1.943844
METERS_PER_NAUTICAL_MILE: Final = 1852.0
MISSING: Final = "MM"

# The columns SailCast reads, what it calls them, and the factor to SailCast's
# units: knots for wind, meters for visibility.
COLUMNS: Final = {
    "WSPD": ("wind", KNOTS_PER_METER_PER_SECOND),
    "GST": ("gust", KNOTS_PER_METER_PER_SECOND),
    "WDIR": ("wind_direction", 1.0),
    "WVHT": ("wave_height", 1.0),
    "DPD": ("wave_period", 1.0),
    "MWD": ("wave_direction", 1.0),
    "ATMP": ("temperature", 1.0),
    "WTMP": ("water_temperature", 1.0),
    "VIS": ("visibility", METERS_PER_NAUTICAL_MILE),
}
_TIME_COLUMNS: Final = ("YY", "MM", "DD", "hh", "mm")


@dataclass(frozen=True, slots=True)
class Buoy:
    """A buoy or coastal station that reports weather or waves."""

    id: str
    name: str
    latitude: float
    longitude: float


async def async_stations(session: aiohttp.ClientSession) -> list[Buoy]:
    """Return every active station that reports weather or waves."""
    body = await fetch_bytes(session, STATIONS_URL)
    return parse_stations(body.decode("utf-8", "replace"))


async def async_get_readings(session: aiohttp.ClientSession, station: str) -> Readings:
    """Return a station's latest reading of each field."""
    body = await fetch_bytes(
        session,
        REALTIME_URL.format(station=station.upper()),
        headers={"Range": f"bytes=0-{READ_BYTES - 1}"},
        limit=READ_BYTES,
    )
    return parse_readings(body.decode("ascii", "replace"))


async def async_anemometer_height(
    session: aiohttp.ClientSession, station: str
) -> float | None:
    """Return how high above the water a station reads the wind, if NDBC says."""
    body = await fetch_bytes(
        session, STATION_PAGE_URL.format(station=station.upper()), limit=PAGE_BYTES
    )
    return parse_anemometer_height(body.decode("utf-8", "replace"))


def parse_anemometer_height(text: str) -> float | None:
    """Read a station page's anemometer height, above the water, in meters.

    The page gives the site's elevation above mean sea level ("sea level" on
    a buoy) and the anemometer's height above the site.
    """
    plain = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)))
    anemometer = re.search(
        r"Anemometer height:\s*([\d.]+)\s*m above site elevation", plain
    )
    site = re.search(
        r"Site elevation:\s*(?:sea level|([\d.]+)\s*m above mean sea level)", plain
    )
    if anemometer is None or site is None:
        return None
    try:
        height = float(anemometer[1]) + (float(site[1]) if site[1] else 0.0)
    except ValueError:
        return None
    return height if 0 < height <= HIGHEST else None


def at_standard_height(readings: Readings, height: float | None) -> Readings:
    """Return readings with wind and gusts scaled from the anemometer to 10 m."""
    if height is None:
        return readings
    factor = math.log(STANDARD_HEIGHT / ROUGHNESS) / math.log(height / ROUGHNESS)
    fields = dict(readings.fields)
    for key in ("wind", "gust"):
        if (reading := fields.get(key)) is not None:
            fields[key] = replace(
                reading, value=reading.value * factor, from_height=height
            )
    return Readings(fields)


def parse_stations(text: str) -> list[Buoy]:
    """Read NDBC's list of active stations, keeping those with readings.

    The list is flat, one element per station with everything in its
    attributes, so it's read without an XML parser.
    """
    buoys = []
    for element in re.findall(r"<station\s([^>]*?)/?>", text):
        attributes = dict(re.findall(r'(\w+)="([^"]*)"', element))
        if attributes.get("met") != "y" or "id" not in attributes:
            continue
        try:
            latitude = float(attributes["lat"])
            longitude = float(attributes["lon"])
        except KeyError, ValueError:
            continue
        buoys.append(
            Buoy(
                id=attributes["id"].upper(),
                name=html.unescape(attributes.get("name", "")).strip(),
                latitude=latitude,
                longitude=longitude,
            )
        )
    return buoys


def parse_readings(text: str) -> Readings:
    """Read the newest value of each field from the start of a realtime file."""
    lines = text.splitlines()
    if lines and not text.endswith("\n"):
        # The range ends partway through a line.
        lines.pop()
    header = next((line for line in lines if line.startswith("#YY")), None)
    if header is None:
        raise ProviderError("NDBC's file has no header")
    columns = {name: index for index, name in enumerate(header[1:].split())}
    if any(name not in columns for name in _TIME_COLUMNS):
        raise ProviderError("NDBC's file has no times")
    fields: dict[str, Reading] = {}
    for line in lines:
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != len(columns):
            continue
        try:
            year, month, day, hour, minute = (
                int(parts[columns[name]]) for name in _TIME_COLUMNS
            )
            time = datetime(year, month, day, hour, minute, tzinfo=UTC)
        except ValueError:
            continue
        for column, (key, factor) in COLUMNS.items():
            if key in fields or column not in columns:
                continue
            raw = parts[columns[column]]
            if raw == MISSING:
                continue
            try:
                fields[key] = Reading(float(raw) * factor, time)
            except ValueError:
                continue
    return Readings(fields)
