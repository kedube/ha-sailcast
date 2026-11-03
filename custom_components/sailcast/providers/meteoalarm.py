"""MeteoAlarm: official warnings from Europe's national weather services.

Each country's active warnings come in one small Atom feed, which lists a
warning once for each of its areas. A warning names its regions by code, or,
in a few countries such as the UK and Norway, draws its own outline. A spot
takes the warnings for every region within a few kilometers of its pin, so a
lake shared by regions gets them all, and those whose outline holds the pin.

The regions' outlines come from the file MeteoAlarm publishes for those who
pass its warnings on, about 33 MB. It isn't openly licensed, so SailCast
doesn't include it: Home Assistant downloads it when a spot in Europe needs
it, keeps a simplified copy, and looks for a newer one each month.

Each warning has a level (yellow, orange or red) and a kind, such as wind or
fog, read from its title: "Yellow Wind Warning issued for The Netherlands -
Harlingen". Green means no warning, so it's left out. A warning a spot uses
is read in full once, for its sender, description and advice, which are shown
as written.

MeteoAlarm's warnings may be passed on under terms equivalent to CC BY 4.0,
showing the national service's name, when each warning was issued, a link to
meteoalarm.org and its note on delays, within ten minutes of publication.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
import html
import json
import math
import re
from typing import Any, Final

import aiohttp

from ..geo import distance_km, distance_to_area_km
from . import ProviderError, fetch_bytes, fetch_json

FEED_URL: Final = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{slug}"
GEOCODES_LIST: Final = "https://gitlab.com/api/v4/projects/72863924/repository/tree"
GEOCODES_URL: Final = (
    "https://gitlab.com/meteoalarm-pm-group/documents/-/raw/master/{name}"
)
GEOCODES_WAIT: Final = 300
PREFIX: Final = "meteoalarm"
LEVELS: Final = ("yellow", "orange", "red")
# Where MeteoAlarm's countries are, roughly: south, north, west, east.
EUROPE: Final = (27.0, 72.0, -32.0, 45.0)
# A spot takes the warnings for regions this close to its pin, or else, out
# at sea, for the nearest region this close.
NEAR_KM: Final = 5.0
REACH_KM: Final = 40.0
# No region is wider than this, so one whose corner is further is far away.
FAR_KM: Final = 1000.0
# Outlines are simplified to about a kilometer, and rounded to about 100 m.
TOLERANCE: Final = 0.01
DECIMALS: Final = 3

# Each country's feed, by MeteoAlarm's country code, and its weather service.
COUNTRIES: Final = {
    "AD": ("andorra", "Servei Meteorològic Nacional"),
    "AT": ("austria", "GeoSphere Austria"),
    "BA": ("bosnia-herzegovina", "FHMZ and RHMZ RS"),
    "BE": ("belgium", "Royal Meteorological Institute (RMI)"),
    "BG": ("bulgaria", "NIMH"),
    "CH": ("switzerland", "MeteoSwiss"),
    "CY": ("cyprus", "Cyprus Department of Meteorology"),
    "CZ": ("czechia", "Czech Hydrometeorological Institute"),
    "DE": ("germany", "Deutscher Wetterdienst (DWD)"),
    "DK": ("denmark", "Danish Meteorological Institute (DMI)"),
    "EE": ("estonia", "Estonian Environment Agency"),
    "ES": ("spain", "AEMET"),
    "FI": ("finland", "Finnish Meteorological Institute"),
    "FR": ("france", "Météo-France"),
    "GR": ("greece", "Hellenic National Meteorological Service"),
    "HR": ("croatia", "DHMZ"),
    "HU": ("hungary", "HungaroMet"),
    "IE": ("ireland", "Met Éireann"),
    "IL": ("israel", "Israel Meteorological Service"),
    "IS": ("iceland", "Icelandic Meteorological Office"),
    "IT": ("italy", "Aeronautica Militare (MeteoAM)"),
    "LT": ("lithuania", "Lithuanian Hydrometeorological Service"),
    "LU": ("luxembourg", "MeteoLux"),
    "LV": ("latvia", "LVĢMC"),
    "MD": ("moldova", "Environmental Meteorology and Monitoring Authority (AMM)"),
    "ME": ("montenegro", "ZHMS"),
    "MK": ("republic-of-north-macedonia", "Hydrometeorological Service (HMS)"),
    "MT": ("malta", "Malta Meteorological Office"),
    "NL": ("netherlands", "KNMI"),
    "NO": ("norway", "MET Norway"),
    "PL": ("poland", "IMGW-PIB"),
    "PT": ("portugal", "IPMA"),
    "RO": ("romania", "National Meteorological Administration"),
    "RS": ("serbia", "RHMZ"),
    "SE": ("sweden", "SMHI"),
    "SI": ("slovenia", "ARSO"),
    "SK": ("slovakia", "SHMÚ"),
    "UA": ("ukraine", "Ukrainian Hydrometeorological Center"),
    "UK": ("united-kingdom", "Met Office"),
}
# Countries whose warnings draw their own outlines, with no regions, and
# roughly where they are: south, north, west, east.
OUTLINED: Final = {
    "AD": (42.4, 42.7, 1.4, 1.8),
    "CH": (45.8, 47.9, 5.9, 10.5),
    "EE": (57.5, 59.9, 21.6, 28.3),
    "IL": (29.4, 33.4, 34.2, 35.9),
    "LU": (49.4, 50.2, 5.7, 6.6),
    "NO": (57.8, 71.3, 4.0, 31.3),
    "SE": (55.2, 69.1, 10.9, 24.2),
    "UA": (44.3, 52.4, 22.1, 40.3),
    "UK": (49.8, 60.9, -8.7, 1.9),
}

_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)
_TITLE = re.compile(r"<title>([^<]*)</title>")
_CAP_LINK = re.compile(r'<link type="application/cap\+xml" href="([^"]+)"')
_REGION = re.compile(r"<valueName>EMMA_ID</valueName>\s*<value>([^<]+)</value>")
_POLYGON = re.compile(r"<cap:polygon>([^<]+)</cap:polygon>")
_HEADLINE = re.compile(
    r"^(Yellow|Orange|Red) (.+?) Warning issued for .+? - (.+)$", re.IGNORECASE
)
_INFO = re.compile(r"<info>(.*?)</info>", re.S)
_GEOCODES = re.compile(r"^MeteoAlarm_Geocodes_\d{4}_\d{2}_\d{2}\.json$")

type Ring = tuple[tuple[float, float], ...]
# Each region's code, name and outer rings of (latitude, longitude).
type Table = tuple[tuple[str, str, tuple[Ring, ...]], ...]


@dataclass(frozen=True, slots=True)
class Warning:
    """One active warning: its level, kind and area, and when it holds.

    `regions` are the region codes it's for, `outlines` the areas it draws,
    as (latitude, longitude) rings, and `link` its full text.
    """

    level: str
    kind: str
    area: str
    regions: tuple[str, ...]
    outlines: tuple[Ring, ...]
    onset: datetime
    expires: datetime
    sent: datetime
    link: str

    @property
    def event(self) -> str:
        """Return the warning's name, such as "Yellow wind warning"."""
        return f"{self.level.capitalize()} {self.kind} warning"


@dataclass(frozen=True, slots=True)
class Details:
    """Who sent a warning, and its description and advice as written."""

    sender: str | None
    text: str | None


@dataclass(frozen=True, slots=True)
class Region:
    """A warning region near a pin, and how far it is, 0 if the pin is in it."""

    code: str
    name: str
    distance_km: float

    @property
    def country(self) -> str:
        """Return the region's country code, the first two letters of its code."""
        return self.code[:2]


@dataclass(frozen=True, slots=True)
class Place:
    """What a pin takes warnings from: nearby regions, and the countries to ask."""

    regions: tuple[str, ...]
    countries: tuple[str, ...]

    @property
    def services(self) -> tuple[str, ...]:
        """Return the national weather services the warnings come from."""
        return tuple(COUNTRIES[country][1] for country in self.countries)


def covers(latitude: float, longitude: float) -> bool:
    """Return whether a position is near enough Europe to ask MeteoAlarm about."""
    south, north, west, east = EUROPE
    return south <= latitude <= north and west <= longitude <= east


async def async_get_warnings(
    session: aiohttp.ClientSession, country: str
) -> list[Warning]:
    """Return a country's active warnings."""
    if country not in COUNTRIES:
        raise ProviderError(f"MeteoAlarm has no feed for {country}")
    body = await fetch_bytes(session, FEED_URL.format(slug=COUNTRIES[country][0]))
    return parse_feed(body.decode("utf-8", "replace"))


async def async_get_details(session: aiohttp.ClientSession, link: str) -> Details:
    """Return who sent a warning, and its description and advice."""
    if not link.startswith("https://feeds.meteoalarm.org/"):
        raise ProviderError("MeteoAlarm linked a warning elsewhere")
    return parse_details((await fetch_bytes(session, link)).decode("utf-8", "replace"))


async def async_geocodes_name(session: aiohttp.ClientSession) -> str:
    """Return the name of the newest file of region outlines MeteoAlarm publishes."""
    listing = await fetch_json(session, GEOCODES_LIST, {"per_page": 100})
    try:
        names = [item["name"] for item in listing if _GEOCODES.match(item["name"])]
    except (KeyError, TypeError) as err:
        raise ProviderError(f"Unexpected list of MeteoAlarm files: {err}") from err
    if not names:
        raise ProviderError("MeteoAlarm publishes no region outlines")
    return str(max(names))


async def async_get_geocodes(session: aiohttp.ClientSession, name: str) -> bytes:
    """Return a file of region outlines, about 33 MB."""
    return await fetch_bytes(
        session, GEOCODES_URL.format(name=name), wait=GEOCODES_WAIT
    )


def parse_feed(text: str) -> list[Warning]:
    """Read a feed's warnings, once each, leaving out green ones."""
    if "<feed" not in text:
        raise ProviderError("MeteoAlarm sent no feed")
    warnings: dict[str, Warning] = {}
    for entry in _ENTRY.findall(text):
        title = _TITLE.search(entry)
        match = (
            _HEADLINE.match(html.unescape(title.group(1)).strip()) if title else None
        )
        link = _CAP_LINK.search(entry)
        if not match or not link or match.group(1).lower() not in LEVELS:
            continue
        try:
            found = Warning(
                level=match.group(1).lower(),
                kind=match.group(2).lower().replace("-", " "),
                area=html.unescape(_tag(entry, "areaDesc") or match.group(3)),
                regions=tuple(_REGION.findall(entry)),
                outlines=tuple(_ring(points) for points in _POLYGON.findall(entry)),
                onset=_time(_tag(entry, "onset") or _tag(entry, "sent")),
                expires=_time(_tag(entry, "expires")),
                sent=_time(_tag(entry, "sent")),
                link=html.unescape(link.group(1)),
            )
        except (TypeError, ValueError) as err:
            raise ProviderError(f"Unexpected MeteoAlarm warning: {err}") from err
        # The feed lists a warning once for each of its regions and outlines.
        if seen := warnings.get(found.link):
            found = replace(
                seen,
                area=seen.area
                if found.area in seen.area.split(", ")
                else f"{seen.area}, {found.area}",
                regions=tuple(dict.fromkeys(seen.regions + found.regions)),
                outlines=seen.outlines + found.outlines,
            )
        warnings[found.link] = found
    return list(warnings.values())


def parse_details(text: str) -> Details:
    """Read a warning's sender, description and advice, in English if it has them."""
    infos = _INFO.findall(text)
    if not infos:
        raise ProviderError("MeteoAlarm sent a warning with no text")
    info = next(
        (info for info in infos if (_cap(info, "language") or "").startswith("en")),
        infos[0],
    )
    parts = [
        part for part in (_cap(info, "description"), _cap(info, "instruction")) if part
    ]
    return Details(_cap(info, "senderName"), "\n\n".join(parts) or None)


def parse_regions(body: bytes) -> Table:
    """Read the regions' outer rings, simplified, one region at a time.

    The file is large, so it's read a region at a time rather than all at
    once. This takes a few seconds, so run it in an executor.
    """
    text = body.decode("utf-8")
    decoder = json.JSONDecoder()
    regions = []
    try:
        index = text.index("[", text.index('"features"')) + 1
        while True:
            while text[index] in " \t\r\n,":
                index += 1
            if text[index] == "]":
                break
            feature, index = decoder.raw_decode(text, index)
            props, geometry = feature.get("properties") or {}, feature.get("geometry")
            if props.get("type") != "EMMA_ID" or not geometry:
                continue
            if rings := _outer_rings(geometry):
                regions.append((props["code"], props["name"], rings))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected MeteoAlarm region outlines: {err}") from err
    return tuple(sorted(regions))


def applies(warning: Warning, near: Place, latitude: float, longitude: float) -> bool:
    """Return whether a warning is for a region near a pin, or its outline holds it."""
    if set(warning.regions) & set(near.regions):
        return True
    return any(_inside(latitude, longitude, ring) for ring in warning.outlines)


def place(latitude: float, longitude: float, table: Table) -> Place:
    """Return the regions and countries a pin takes warnings from.

    This goes through every region, so run it in an executor.
    """
    found = [
        region
        for region in regions_near(latitude, longitude, REACH_KM, table)
        if region.country in COUNTRIES
    ]
    regions = [region for region in found if region.distance_km <= NEAR_KM] or found[:1]
    countries = dict.fromkeys(
        [region.country for region in regions] + outlined_countries(latitude, longitude)
    )
    return Place(tuple(region.code for region in regions), tuple(countries))


def regions_near(
    latitude: float, longitude: float, limit_km: float, table: Table
) -> list[Region]:
    """Return the regions holding a pin or within a distance, nearest first."""
    found = []
    for code, name, rings in table:
        # Most regions are far away, which one corner shows quickly.
        corner = rings[0][0]
        if distance_km(latitude, longitude, *corner) > limit_km + FAR_KM:
            continue
        distance = distance_to_area_km(
            latitude,
            longitude,
            {
                "type": "MultiPolygon",
                "coordinates": [[[[lon, lat] for lat, lon in ring]] for ring in rings],
            },
        )
        if distance <= limit_km:
            found.append(Region(code, name, distance))
    return sorted(found, key=lambda region: region.distance_km)


def outlined_countries(latitude: float, longitude: float) -> list[str]:
    """Return the countries with outlined warnings that a pin may be in."""
    return [
        country
        for country, (south, north, west, east) in OUTLINED.items()
        if south <= latitude <= north and west <= longitude <= east
    ]


def _outer_rings(geometry: dict[str, Any]) -> tuple[Ring, ...]:
    """Return a region's outer rings as (latitude, longitude), simplified."""
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    rings = []
    for polygon in polygons:
        ring = _simplify(polygon[0], TOLERANCE)
        if len(ring) >= 4:
            rings.append(
                tuple((round(lat, DECIMALS), round(lon, DECIMALS)) for lon, lat in ring)
            )
    return tuple(rings)


def _simplify(line: Sequence[Sequence[float]], tolerance: float) -> list[Any]:
    """Return a line's points with the Douglas-Peucker algorithm's fewer.

    Points closer than a quarter of the tolerance to the last one kept go
    first, which makes the rest quick on outlines with many points.
    """
    points = [line[0]]
    for point in line[1:-1]:
        previous = points[-1]
        if math.hypot(point[0] - previous[0], point[1] - previous[1]) >= tolerance / 4:
            points.append(point)
    points.append(line[-1])
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first][:2], points[last][:2]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        farthest, index = 0.0, 0
        for i in range(first + 1, last):
            x, y = points[i][:2]
            gap = (
                abs(dy * x - dx * y + x2 * y1 - y2 * x1) / length
                if length
                else math.hypot(x - x1, y - y1)
            )
            if gap > farthest:
                farthest, index = gap, i
        if farthest > tolerance:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def _inside(
    latitude: float, longitude: float, ring: Sequence[tuple[float, float]]
) -> bool:
    """Return whether a point is inside a ring of (lat, lon), by the even-odd rule."""
    inside = False
    for (lat1, lon1), (lat2, lon2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        if (lat1 > latitude) != (lat2 > latitude):
            crossing = lon1 + (latitude - lat1) / (lat2 - lat1) * (lon2 - lon1)
            if longitude < crossing:
                inside = not inside
    return inside


def _ring(points: str) -> Ring:
    return tuple(
        (float(lat), float(lon))
        for lat, lon in (pair.split(",") for pair in points.split())
    )


def _tag(entry: str, name: str) -> str | None:
    match = re.search(rf"<cap:{name}>([^<]*)</cap:{name}>", entry)
    return match.group(1).strip() if match else None


def _cap(info: str, name: str) -> str | None:
    match = re.search(rf"<{name}>(.*?)</{name}>", info, re.S)
    return html.unescape(match.group(1)).strip() if match else None


def _time(value: str | None) -> datetime:
    if not value:
        raise ValueError("no time")
    return datetime.fromisoformat(value)
