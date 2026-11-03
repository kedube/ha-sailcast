"""Suggest a spot's data sources: tide station, current station and marine zone.

Tide stations come from NOAA's radius search. NOAA has no radius search for
current stations, so their list is fetched once and kept for a day. Marine
zones come from the National Weather Service.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import CONF_CURRENT_STATION, DOMAIN
from .geo import distance_km
from .providers import ProviderError, noaa_coops, nws
from .providers.noaa_coops import Station

TIDE_MILES: Final = 25
CURRENT_KM: Final = 25
ZONE_KM: Final = 40
SHOWN: Final = 6
# A current station is chosen for a new spot only if it's this close.
NEAR_CURRENT_KM: Final = 5.0

DATA_CURRENT_STATIONS: HassKey[tuple[datetime, list[Station]]] = HassKey(
    f"{DOMAIN}_current_stations"
)


@dataclass(frozen=True, slots=True)
class Choice:
    """A source a spot could use, how far away it is, and where, for stations."""

    id: str
    name: str
    distance_km: float
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class Suggestions:
    """The nearest sources of each kind, nearest first.

    `failed` says that at least one lookup couldn't be done.
    """

    tide: list[Choice]
    current: list[Choice]
    zones: list[Choice]
    failed: bool = False


async def async_suggest(
    hass: HomeAssistant, latitude: float, longitude: float
) -> Suggestions:
    """Return the sources near a spot."""
    session = async_get_clientsession(hass)
    tide, current, zones = await asyncio.gather(
        noaa_coops.async_tide_stations_near(session, latitude, longitude, TIDE_MILES),
        _async_current_stations(hass),
        nws.async_marine_zones(session, latitude, longitude),
        return_exceptions=True,
    )
    failed = False

    def stations(found: list[Station] | BaseException, limit: float) -> list[Choice]:
        nonlocal failed
        if isinstance(found, BaseException):
            if not isinstance(found, ProviderError):
                raise found
            failed = True
            return []
        choices = sorted(
            (
                Choice(
                    station.id,
                    station.name,
                    distance_km(
                        latitude, longitude, station.latitude, station.longitude
                    ),
                    station.latitude,
                    station.longitude,
                )
                for station in found
            ),
            key=lambda choice: choice.distance_km,
        )
        return [choice for choice in choices if choice.distance_km <= limit][:SHOWN]

    tide_choices = stations(tide, TIDE_MILES * 1.609344)
    current_choices = _one_per_station(stations(current, CURRENT_KM))
    if isinstance(zones, BaseException):
        if not isinstance(zones, ProviderError):
            raise zones
        failed = True
        zone_choices = []
    else:
        zone_choices = [
            Choice(zone.id, zone.name, zone.distance_km)
            for zone in zones
            if zone.distance_km <= ZONE_KM
        ][:SHOWN]
    return Suggestions(tide_choices, current_choices, zone_choices, failed)


async def _async_current_stations(hass: HomeAssistant) -> list[Station]:
    """Return every current station, fetching the list at most once a day."""
    now = dt_util.utcnow()
    if (cached := hass.data.get(DATA_CURRENT_STATIONS)) and now - cached[0] < timedelta(
        days=1
    ):
        return cached[1]
    stations = await noaa_coops.async_current_stations(async_get_clientsession(hass))
    hass.data[DATA_CURRENT_STATIONS] = (now, stations)
    return stations


def _one_per_station(choices: list[Choice]) -> list[Choice]:
    """Keep the shallowest depth bin of each current station.

    Bins are numbered from the surface, and the surface current is the one
    that matters for sailing.
    """
    kept: dict[str, Choice] = {}
    for choice in choices:
        station = choice.id.partition("_")[0]
        if station not in kept or _bin(choice) < _bin(kept[station]):
            kept[station] = choice
    return sorted(kept.values(), key=lambda choice: choice.distance_km)


def _bin(choice: Choice) -> int:
    return int(choice.id.partition("_")[2] or 0)


def suggested(key: str, found: list[Choice]) -> str | None:
    """Return the source to suggest for a new spot, nearest first.

    A current station is suggested only if it's close, because currents
    change a lot over short distances.
    """
    if not found:
        return None
    if key == CONF_CURRENT_STATION and found[0].distance_km > NEAR_CURRENT_KM:
        return None
    return found[0].id
