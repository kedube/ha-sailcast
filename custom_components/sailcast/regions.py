"""MeteoAlarm's warning regions, downloaded when a spot in Europe needs them.

MeteoAlarm's region outlines aren't openly licensed, so SailCast doesn't
include them. The first spot in Europe downloads MeteoAlarm's file (about
33 MB), and a simplified copy (about 1 MB) is kept on disk. Each month
SailCast looks for a newer file; if it can't, the copy it has stays in use.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .providers import ProviderError, meteoalarm

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.meteoalarm_regions"
CHECK_EVERY: Final = timedelta(days=30)
# After a failed check, the copy on disk is used this long before asking again.
RETRY_AFTER: Final = timedelta(days=1)

DATA_REGIONS: HassKey[Regions] = HassKey(f"{DOMAIN}_meteoalarm_regions")


class Regions:
    """MeteoAlarm's warning regions, shared by every SailCast entry."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the regions, read from disk the first time they're needed."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._loaded = False
        self._table: meteoalarm.Table | None = None
        self._name: str | None = None
        self._checked: datetime | None = None

    async def async_place(self, latitude: float, longitude: float) -> meteoalarm.Place:
        """Return the regions and countries a pin takes MeteoAlarm warnings from.

        Outside Europe that's nothing, and nothing is downloaded.
        """
        if not meteoalarm.covers(latitude, longitude):
            return meteoalarm.Place((), ())
        table = await self._async_table()
        return await self.hass.async_add_executor_job(
            meteoalarm.place, latitude, longitude, table
        )

    async def async_remove(self) -> None:
        """Delete the saved regions, when SailCast is deleted."""
        await self._store.async_remove()

    async def _async_table(self) -> meteoalarm.Table:
        """Return the regions, downloading them if they're missing or old."""
        async with self._lock:
            if not self._loaded:
                await self._async_load()
            now = dt_util.utcnow()
            if (
                self._table is not None
                and self._checked
                and now - self._checked < CHECK_EVERY
            ):
                return self._table
            try:
                return await self._async_download(now)
            except ProviderError:
                if self._table is None:
                    raise
                # Keep the copy on disk, and ask again tomorrow.
                self._checked = now - CHECK_EVERY + RETRY_AFTER
                return self._table

    async def _async_download(self, now: datetime) -> meteoalarm.Table:
        """Fetch the newest region outlines, unless they're the ones kept."""
        session = async_get_clientsession(self.hass)
        name = await meteoalarm.async_geocodes_name(session)
        table = self._table
        if name != self._name or table is None:
            body = await meteoalarm.async_get_geocodes(session, name)
            table = await self.hass.async_add_executor_job(
                meteoalarm.parse_regions, body
            )
            self._table, self._name = table, name
        self._checked = now
        await self._store.async_save(
            {
                "name": self._name,
                "checked": now.isoformat(),
                # One string a ring, "lat,lon lat,lon …", keeps the file small.
                "regions": [
                    [code, region, [_text(ring) for ring in rings]]
                    for code, region, rings in table
                ],
            }
        )
        return table

    async def _async_load(self) -> None:
        """Read the regions kept on disk."""
        self._loaded = True
        stored = await self._store.async_load()
        if not stored:
            return
        try:
            self._table = tuple(
                (code, region, tuple(_ring(ring) for ring in rings))
                for code, region, rings in stored["regions"]
            )
            self._name = stored["name"]
            self._checked = datetime.fromisoformat(stored["checked"])
        except AttributeError, KeyError, TypeError, ValueError:
            self._table = None


def _text(ring: meteoalarm.Ring) -> str:
    return " ".join(f"{lat:g},{lon:g}" for lat, lon in ring)


def _ring(text: str) -> meteoalarm.Ring:
    return tuple(
        (float(lat), float(lon))
        for lat, lon in (pair.split(",") for pair in text.split())
    )
