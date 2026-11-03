"""The US National Weather Service: marine warnings and marine zones.

Alerts are fetched by marine zone, one request for every zone. A point query
only matches zones that contain the point, so a pin near the shore can miss
its zone. Then the nearest of the forecast office's coastal zones is used.
Lakes without a marine zone get the alerts for the pin itself, such as a
Lake Wind Advisory, which also catches storm warnings drawn around it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import aiohttp

from ..geo import distance_to_area_km
from ..timeline import Alert
from . import ProviderError, fetch_json

API: Final = "https://api.weather.gov"
HEADERS: Final = {"Accept": "application/geo+json"}
# Zone outlines are large, so only this many of an office's zones are checked.
MAX_ZONES: Final = 16


@dataclass(frozen=True, slots=True)
class Zone:
    """A marine zone and how far a spot is from it."""

    id: str
    name: str
    distance_km: float


async def async_get_alerts(
    session: aiohttp.ClientSession, zones: Collection[str]
) -> list[Alert]:
    """Return the active alerts for the zones."""
    payload = await fetch_json(
        session,
        f"{API}/alerts/active",
        {"zone": ",".join(sorted(zones))},
        headers=HEADERS,
    )
    return parse_alerts(payload, zones)


async def async_get_alerts_at(
    session: aiohttp.ClientSession, latitude: float, longitude: float, zone: str
) -> list[Alert]:
    """Return the active alerts for a pin, all under the zone given."""
    payload = await fetch_json(
        session,
        f"{API}/alerts/active",
        {"point": f"{latitude:.4f},{longitude:.4f}"},
        headers=HEADERS,
    )
    return parse_alerts(payload, None, zone)


def parse_alerts(
    payload: Any, zones: Collection[str] | None, pin: str | None = None
) -> list[Alert]:
    """Read alerts, one per zone they cover, or each once for a pin's alerts.

    Cancelled alerts, tests and exercises are left out. An alert runs from
    its onset (or when it took effect) to its end (or when it expires).
    """
    alerts: list[Alert] = []
    try:
        for feature in payload["features"]:
            props = feature["properties"]
            if props.get("status") != "Actual" or props.get("messageType") == "Cancel":
                continue
            start = _time(props.get("onset") or props["effective"])
            end = _time(props.get("ends") or props["expires"])
            covered = (
                [pin]
                if pin
                else [zone for zone in props["geocode"]["UGC"] if zone in (zones or ())]
            )
            alerts.extend(
                Alert(
                    event=props["event"],
                    zone=zone,
                    start=start,
                    end=end,
                    headline=props.get("headline"),
                )
                for zone in covered
            )
    except (KeyError, TypeError, ValueError) as err:
        raise ProviderError(f"Unexpected alerts: {err}") from err
    return alerts


async def async_marine_zones(
    session: aiohttp.ClientSession, latitude: float, longitude: float
) -> tuple[list[Zone], bool]:
    """Return the marine zones for a spot, nearest first, and whether it's covered.

    That's the zone the spot is in, or the forecast office's coastal zones.
    A spot is covered when the NWS forecasts for it, even with no marine
    zone, as on a lake inland. Outside the area the NWS covers, there's
    nothing.
    """
    point = f"{latitude:.4f},{longitude:.4f}"
    containing = await fetch_json(
        session, f"{API}/zones", {"type": "coastal", "point": point}, headers=HEADERS
    )
    if zones := [
        Zone(feature["properties"]["id"], feature["properties"]["name"], 0.0)
        for feature in containing.get("features", [])
    ]:
        return zones, True
    try:
        points = await fetch_json(session, f"{API}/points/{point}", headers=HEADERS)
    except ProviderError:
        # Points outside the US have no forecast office.
        return [], False
    office = points.get("properties", {}).get("cwa")
    listing = await fetch_json(
        session, f"{API}/zones", {"type": "coastal"}, headers=HEADERS
    )
    candidates = [
        feature["properties"]
        for feature in listing.get("features", [])
        if office in (feature["properties"].get("cwa") or ())
    ][:MAX_ZONES]

    async def measure(props: dict[str, Any]) -> Zone | None:
        try:
            shape = await fetch_json(
                session, f"{API}/zones/coastal/{props['id']}", headers=HEADERS
            )
            distance = distance_to_area_km(latitude, longitude, shape["geometry"])
        except ProviderError, KeyError, TypeError, ValueError:
            return None
        return Zone(props["id"], props["name"], distance)

    measured = await asyncio.gather(*(measure(props) for props in candidates))
    return sorted(
        (zone for zone in measured if zone), key=lambda zone: zone.distance_km
    ), True


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value)
