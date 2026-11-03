"""Environment and Climate Change Canada: Canadian marine warnings.

Marine warnings come with ECCC's marine forecast for each area, from its
GeoMet API. A spot uses a whole area, or one of its parts where the area is
split, such as Western Lake Ontario. An area is found by asking which areas
cover the pin. Warnings say only that they're in effect, with no start or
end, and the forecast they come with covers the rest of today and tomorrow,
so SailCast applies one from when it was issued to the end of tomorrow.
Data Source: Environment and Climate Change Canada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
from typing import Any, Final

import aiohttp

from ..timeline import Alert
from . import ProviderError, fetch_json

API: Final = "https://api.weather.gc.ca/collections/marineweather-realtime/items"
PREFIX: Final = "eccc"
# Canada's waters, roughly, so other places aren't asked.
AREA: Final = (41.5, 84.0, -142.0, -52.0)
# How far around the pin to look for areas, in degrees.
SEARCH: Final = (0.01, 0.1)
IN_EFFECT: Final = "IN EFFECT"


@dataclass(frozen=True, slots=True)
class Area:
    """A marine forecast area, and its parts where it's split."""

    id: str
    name: str
    parts: tuple[str, ...] = ()


def covers(latitude: float, longitude: float) -> bool:
    """Return whether a position is near enough Canada to ask about."""
    south, north, west, east = AREA
    return south <= latitude <= north and west <= longitude <= east


async def async_areas_at(
    session: aiohttp.ClientSession, latitude: float, longitude: float
) -> list[Area]:
    """Return the marine areas covering a pin, or else those just around it."""
    for reach in SEARCH:
        payload = await fetch_json(
            session,
            API,
            {
                "f": "json",
                "skipGeometry": "true",
                "bbox": ",".join(
                    f"{value:.4f}"
                    for value in (
                        longitude - reach,
                        latitude - reach,
                        longitude + reach,
                        latitude + reach,
                    )
                ),
            },
        )
        if areas := parse_areas(payload):
            return areas
    return []


async def async_get_warnings(
    session: aiohttp.ClientSession, area: str, zone: tzinfo
) -> list[Alert]:
    """Return the warnings in effect in an area, each for its part, if split.

    Each alert's zone is the area, or the area and its part, such as
    "eccc:m0000144/Western Lake Ontario".
    """
    payload = await fetch_json(
        session, f"{API}/{area}", {"f": "json", "skipGeometry": "true"}
    )
    return parse_warnings(payload, area, zone)


def source(area: str, part: str | None = None) -> str:
    """Return the ID a spot's warnings are kept under, for an area or a part."""
    return f"{PREFIX}:{area}/{part}" if part else f"{PREFIX}:{area}"


def parse_areas(payload: Any) -> list[Area]:
    """Read the areas found, with their parts' names."""
    try:
        return [
            Area(
                feature["id"],
                feature["properties"]["area"]["value"]["en"],
                tuple(
                    location["name"]["en"]
                    for location in feature["properties"]["regularForecast"][
                        "locations"
                    ]
                    if location.get("name")
                ),
            )
            for feature in payload["features"]
        ]
    except (KeyError, TypeError) as err:
        raise ProviderError(f"Unexpected ECCC marine areas: {err}") from err


def parse_warnings(payload: Any, area: str, zone: tzinfo) -> list[Alert]:
    """Read the warnings in effect, from their issue to the end of the next day."""
    try:
        props = payload["properties"]
        issued = datetime.fromisoformat(props["lastUpdated"])
        end = datetime.combine(
            issued.astimezone(zone).date() + timedelta(days=2), time(), zone
        )
        alerts = []
        for location in (props.get("warnings") or {}).get("locations") or ():
            part = location["name"]["en"]
            for event in location.get("events") or ():
                if event["status"]["en"] != IN_EFFECT:
                    continue
                name = event["name"]["en"]
                alerts.append(
                    Alert(
                        event=name,
                        zone=source(area, part),
                        start=issued,
                        end=end,
                        headline=f"{name} in effect for {part}",
                    )
                )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected ECCC warnings for {area}: {err}") from err
    return alerts
