"""Suggest a spot's data sources: stations, a marine zone, a buoy and an airport.

Tide stations come from NOAA's radius search, and in Canada and the
Netherlands from CHS's and Rijkswaterstaat's station lists. In Norway,
Kartverket answers for the pin itself. WorldTides is offered when its key is
set, and the ocean model's rough tide everywhere, though never suggested.
NOAA has no radius search for current stations, so their list is fetched
once and kept for a day, and so are NDBC's buoys and the regional station
lists. Marine zones come from the National Weather Service, and airports
from aviationweather.gov's search by area.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from . import alerts, tides
from .const import CONF_CURRENT_STATION, CONF_MARINE_ZONE, CONF_TIDE_STATION, DOMAIN
from .geo import distance_km
from .providers import (
    ProviderError,
    Station,
    chs,
    eccc,
    kartverket,
    metar,
    meteoalarm,
    ndbc,
    noaa_coops,
    nws,
    rws,
)
from .providers.metar import Airport
from .providers.ndbc import Buoy
from .regions import DATA_REGIONS, Regions

TIDE_MILES: Final = 25
TIDE_KM: Final = TIDE_MILES * 1.609344
CURRENT_KM: Final = 25
ZONE_KM: Final = 40
BUOY_KM: Final = 60
AIRPORT_KM: Final = 40
SHOWN: Final = 6
# A current station is chosen for a new spot only if it's this close, and a
# marine zone only if the pin is in it or this close, as on a pin near shore.
NEAR_CURRENT_KM: Final = 5.0
NEAR_ZONE_KM: Final = 5.0
KEEP_LISTS: Final = timedelta(days=1)

DATA_CURRENT_STATIONS: HassKey[tuple[datetime, list[Station]]] = HassKey(
    f"{DOMAIN}_current_stations"
)
DATA_BUOYS: HassKey[tuple[datetime, list[Buoy]]] = HassKey(f"{DOMAIN}_buoys")
DATA_CHS_STATIONS: HassKey[tuple[datetime, list[Station]]] = HassKey(
    f"{DOMAIN}_chs_stations"
)
DATA_RWS_STATIONS: HassKey[tuple[datetime, list[Station]]] = HassKey(
    f"{DOMAIN}_rws_stations"
)


@dataclass(frozen=True, slots=True)
class Choice:
    """A source a spot could use, how far away it is, and where, for stations.

    `code` is what a station is known by, to show with its name. Sources
    asked about the pin itself have no distance.
    """

    id: str
    name: str
    distance_km: float | None
    latitude: float | None = None
    longitude: float | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class Suggestions:
    """The nearest sources of each kind, nearest first.

    `failed` says that at least one lookup couldn't be done.
    """

    tide: list[Choice]
    current: list[Choice]
    zones: list[Choice]
    buoys: list[Choice] = field(default_factory=list)
    airports: list[Choice] = field(default_factory=list)
    failed: bool = False


async def async_suggest(
    hass: HomeAssistant,
    latitude: float,
    longitude: float,
    *,
    worldtides: bool = False,
) -> Suggestions:
    """Return the sources near a spot. `worldtides` says its key is set."""
    session = async_get_clientsession(hass)
    tide, current, zones, buoys, airports = await asyncio.gather(
        _async_tide_choices(hass, latitude, longitude, worldtides=worldtides),
        _async_current_stations(hass),
        _async_warning_choices(hass, latitude, longitude),
        _async_buoys(hass),
        metar.async_airports_near(session, latitude, longitude, AIRPORT_KM),
        return_exceptions=True,
    )
    failed = False

    def stations(
        found: list[Station] | list[Buoy] | list[Airport] | BaseException,
        limit: float,
    ) -> list[Choice]:
        nonlocal failed
        if isinstance(found, BaseException):
            if not isinstance(found, ProviderError):
                raise found
            failed = True
            return []
        return _nearest(found, latitude, longitude, limit)

    if isinstance(tide, BaseException):
        raise tide
    if isinstance(zones, BaseException):
        raise zones
    tide_choices, tide_failed = tide
    zone_choices, zones_failed = zones
    return Suggestions(
        tide_choices,
        _one_per_station(stations(current, CURRENT_KM)),
        zone_choices,
        stations(buoys, BUOY_KM),
        stations(airports, AIRPORT_KM),
        failed or tide_failed or zones_failed,
    )


async def _async_tide_choices(
    hass: HomeAssistant, latitude: float, longitude: float, *, worldtides: bool
) -> tuple[list[Choice], bool]:
    """Return the tide sources for a pin, and whether a lookup failed.

    Stations from every provider come first, nearest first, then the
    sources asked about the pin itself.
    """
    session = async_get_clientsession(hass)
    lookups: list[tuple[str | None, Awaitable[list[Station]]]] = [
        (
            None,
            noaa_coops.async_tide_stations_near(
                session, latitude, longitude, TIDE_MILES
            ),
        )
    ]
    if chs.covers(latitude, longitude):
        lookups.append(
            (chs.PREFIX, _async_kept(hass, DATA_CHS_STATIONS, chs.async_stations))
        )
    if rws.covers(latitude, longitude):
        lookups.append(
            (rws.PREFIX, _async_kept(hass, DATA_RWS_STATIONS, rws.async_stations))
        )
    found = await asyncio.gather(
        *(lookup for _, lookup in lookups), return_exceptions=True
    )
    failed = False
    stations: list[Station] = []
    for (prefix, _), result in zip(lookups, found, strict=True):
        if isinstance(result, BaseException):
            if not isinstance(result, ProviderError):
                raise result
            failed = True
            continue
        stations.extend(
            Station(
                f"{prefix}:{station.id}" if prefix else station.id,
                station.name,
                station.latitude,
                station.longitude,
                station.code if prefix else station.id,
            )
            for station in result
        )
    choices = _nearest(stations, latitude, longitude, TIDE_KM)
    if kartverket.covers(latitude, longitude):
        try:
            name = await kartverket.async_station_at(
                session, latitude, longitude, dt_util.utcnow()
            )
        except ProviderError:
            failed = True
        else:
            if name:
                choices.append(
                    Choice(
                        tides.KARTVERKET, f"Kartverket at the pin, from {name}", None
                    )
                )
    if worldtides:
        choices.append(Choice(tides.WORLDTIDES, "WorldTides at the pin", None))
    choices.append(Choice(tides.MODEL, "Ocean model at the pin, rough", None))
    return choices, failed


async def _async_warning_choices(
    hass: HomeAssistant, latitude: float, longitude: float
) -> tuple[list[Choice], bool]:
    """Return the warning sources for a pin, and whether a lookup failed.

    US marine zones come first, nearest first, then the NWS's alerts for
    the pin, where the NWS covers it, then any Canadian marine area, whole
    and in its parts, then MeteoAlarm's warnings for a pin in Europe.
    """
    session = async_get_clientsession(hass)
    failed = False
    choices: list[Choice] = []
    try:
        zones, covered = await nws.async_marine_zones(session, latitude, longitude)
    except ProviderError:
        failed = True
    else:
        choices.extend(
            Choice(zone.id, zone.name, zone.distance_km, code=zone.id)
            for zone in zones[:SHOWN]
            if zone.distance_km <= ZONE_KM
        )
        if covered:
            choices.append(
                Choice(alerts.NWS, "National Weather Service alerts at the pin", None)
            )
    if eccc.covers(latitude, longitude):
        try:
            areas = await eccc.async_areas_at(session, latitude, longitude)
        except ProviderError:
            failed = True
        else:
            for area in areas:
                whole = f"{area.name}, all parts" if area.parts else area.name
                choices.append(Choice(eccc.source(area.id), whole, None))
                choices.extend(
                    Choice(eccc.source(area.id, part), part, None)
                    for part in area.parts
                )
    regions = hass.data.setdefault(DATA_REGIONS, Regions(hass))
    try:
        near = await regions.async_place(latitude, longitude)
    except ProviderError:
        failed = True
        near = meteoalarm.Place(
            (), tuple(meteoalarm.outlined_countries(latitude, longitude))
        )
    if near.countries:
        choices.append(
            Choice(
                alerts.METEOALARM,
                f"MeteoAlarm warnings for the pin, from {', '.join(near.services)}",
                None,
            )
        )
    return choices, failed


def _nearest(
    found: list[Station] | list[Buoy] | list[Airport],
    latitude: float,
    longitude: float,
    limit: float,
) -> list[Choice]:
    """Return the stations within a distance of a pin, nearest first."""
    choices = sorted(
        (
            Choice(
                station.id,
                station.name,
                distance_km(latitude, longitude, station.latitude, station.longitude),
                station.latitude,
                station.longitude,
                # Regional stations' IDs carry their provider, and aren't shown.
                getattr(station, "code", None)
                or (None if ":" in station.id else station.id),
            )
            for station in found
        ),
        key=lambda choice: choice.distance_km or 0.0,
    )
    return [
        choice
        for choice in choices
        if choice.distance_km is not None and choice.distance_km <= limit
    ][:SHOWN]


async def _async_kept(
    hass: HomeAssistant,
    key: HassKey[tuple[datetime, list[Station]]],
    fetch: Callable[[aiohttp.ClientSession], Awaitable[list[Station]]],
) -> list[Station]:
    """Return a provider's station list, fetching it at most once a day."""
    now = dt_util.utcnow()
    if (cached := hass.data.get(key)) and now - cached[0] < KEEP_LISTS:
        return cached[1]
    stations = await fetch(async_get_clientsession(hass))
    hass.data[key] = (now, stations)
    return stations


async def _async_current_stations(hass: HomeAssistant) -> list[Station]:
    """Return every current station, fetching the list at most once a day."""
    now = dt_util.utcnow()
    if (cached := hass.data.get(DATA_CURRENT_STATIONS)) and now - cached[
        0
    ] < KEEP_LISTS:
        return cached[1]
    stations = await noaa_coops.async_current_stations(async_get_clientsession(hass))
    hass.data[DATA_CURRENT_STATIONS] = (now, stations)
    return stations


async def _async_buoys(hass: HomeAssistant) -> list[Buoy]:
    """Return every buoy with readings, fetching the list at most once a day."""
    now = dt_util.utcnow()
    if (cached := hass.data.get(DATA_BUOYS)) and now - cached[0] < KEEP_LISTS:
        return cached[1]
    buoys = await ndbc.async_stations(async_get_clientsession(hass))
    hass.data[DATA_BUOYS] = (now, buoys)
    return buoys


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
    return sorted(kept.values(), key=lambda choice: choice.distance_km or 0.0)


def _bin(choice: Choice) -> int:
    return int(choice.id.partition("_")[2] or 0)


def suggested(key: str, found: list[Choice]) -> str | None:
    """Return the source to suggest for a new spot, nearest first.

    A current station is suggested only if it's close, because currents
    change a lot over short distances. A marine zone is suggested only if
    the pin is in it or near it; otherwise the next source is, such as the
    NWS's alerts for a lake's pin. The ocean model's rough tide is never
    suggested; it's there to pick by hand.
    """
    if key == CONF_TIDE_STATION:
        found = [choice for choice in found if choice.id != tides.MODEL]
    if key == CONF_MARINE_ZONE:
        found = [
            choice
            for choice in found
            if choice.distance_km is None or choice.distance_km <= NEAR_ZONE_KM
        ]
    if not found:
        return None
    if key == CONF_CURRENT_STATION and (found[0].distance_km or 0) > NEAR_CURRENT_KM:
        return None
    return found[0].id
