"""Where a spot's tides come from, and fetching them.

A spot's tide source is a station or a position. Stations are a NOAA
station's ID, with no prefix, or a regional provider's station, such as
"chs:<id>" in Canada or "rws:<code>" in the Netherlands. Sources asked by
position use the spot's pin: Kartverket in Norway, WorldTides with your own
key, and the ocean model's sea level, which is rough and only ever chosen by
hand. Predictions are kept by station, or by provider and pin, so spots
sharing one share its predictions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

import aiohttp

from .providers import (
    ProviderError,
    Tides,
    chs,
    kartverket,
    noaa_coops,
    open_meteo,
    rws,
    turning_points,
    worldtides,
)

if TYPE_CHECKING:
    from .profiles import Spot

NOAA: Final = "noaa"
CHS: Final = chs.PREFIX
RWS: Final = rws.PREFIX
KARTVERKET: Final = kartverket.PREFIX
WORLDTIDES: Final = worldtides.SOURCE
MODEL: Final = "model"
BY_POSITION: Final = (KARTVERKET, WORLDTIDES, MODEL)
# WorldTides costs credits, so its two weeks are kept until fewer than this
# many days are left.
WORLDTIDES_LEFT: Final = timedelta(days=8)


class MissingKeyError(ProviderError):
    """A source needs an API key that isn't set."""


def provider(source: str) -> str:
    """Return who provides a tide source, or the predictions kept under a key.

    That's "noaa", "chs", "rws", "kartverket", "worldtides" or "model".
    """
    name, sep, _ = source.partition(":")
    if sep:
        return name
    return source if source in BY_POSITION else NOAA


def key(spot: Spot) -> str | None:
    """Return the key a spot's tide predictions are kept under, if it has tides."""
    source = spot.tide_station
    if not source:
        return None
    if source in BY_POSITION:
        return f"{source}:{spot.latitude:.4f},{spot.longitude:.4f}"
    return source


def stale(tides: Tides | None, fetched: datetime | None, now: datetime) -> bool:
    """Return whether predictions should be fetched again.

    Most are fetched once a day. WorldTides' are kept while they still
    cover more than a week ahead, to save its credits.
    """
    if tides is None or fetched is None:
        return True
    if provider(tides.station) == WORLDTIDES:
        last = tides.hourly[-1][0] if tides.hourly else fetched
        return last - now < WORLDTIDES_LEFT
    return fetched.date() != now.date()


async def async_fetch(
    session: aiohttp.ClientSession,
    source: str,
    begin: datetime,
    *,
    worldtides_key: str | None = None,
) -> Tides:
    """Return the predictions kept under a key, starting at `begin`."""
    name = provider(source)
    place = source.partition(":")[2]
    if name == NOAA:
        return await noaa_coops.async_get_tides(session, source, begin.date())
    if name == CHS:
        return await chs.async_get_tides(session, place, begin)
    if name == RWS:
        return await rws.async_get_tides(session, place, begin)
    latitude, longitude = (float(part) for part in place.split(","))
    if name == KARTVERKET:
        return await kartverket.async_get_tides(session, latitude, longitude, begin)
    if name == WORLDTIDES:
        if not worldtides_key:
            raise MissingKeyError("No WorldTides key is set")
        return await worldtides.async_get_tides(
            session, worldtides_key, latitude, longitude, begin
        )
    (hourly,) = await open_meteo.async_get_sea_level(session, [(latitude, longitude)])
    return Tides(source, turning_points(hourly), hourly, datum="MSL")
