"""Fetch and exposure from the shoreline: how far open water reaches each way.

Each pin is measured once, from OpenStreetMap's water in OpenFreeMap's map
tiles, and kept on disk. Rays go out every 3 degrees to 20 km and stop where
the water does; a ray that's still on water at 20 km counts as 20 km. The
fetch for a wind is the average of the rays within 15 degrees of where it
comes from, as coastal engineers measure it, so a narrow channel that opens
onto the sea doesn't count as open sea. A compass point is exposed when some
ray within its sector reaches the full 20 km.

Along each ray, the edges of the water polygons mark where it might leave the
water. Tiles cut polygons at their edges, and river and sea polygons overlap
at river mouths, so a crossing alone proves nothing: each stretch between
crossings is checked by whether its middle is in any water.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
import logging
import math
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .geo import DIRECTIONS, KM_PER_DEGREE, angle_between
from .providers import ProviderError, openfreemap
from .providers.openfreemap import WaterTile

LOGGER = logging.getLogger(__package__)

STEP_DEGREES: Final = 3
RAYS: Final = 360 // STEP_DEGREES
REACH_KM: Final = openfreemap.REACH_KM
# The fetch for a wind averages the rays within this many degrees of it.
FETCH_SECTOR: Final = 15.0
# How many tiles are fetched at once.
TILES_AT_ONCE: Final = 4
# A pin that couldn't be measured is tried again after this long.
RETRY_AFTER: Final = timedelta(hours=6)
# Pins no spot uses are forgotten after this long.
KEEP_UNUSED: Final = timedelta(days=1)

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.shoreline"

DATA_SHORELINES: HassKey[Shorelines] = HassKey(f"{DOMAIN}_shorelines")

type Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Shoreline:
    """A pin's open water, every 3 degrees clockwise from north, in km.

    A pin on land has no rays.
    """

    on_water: bool
    rays: tuple[float, ...]
    measured: datetime

    def fetch(self, direction: float) -> float:
        """Return the fetch for wind from a direction: the open water upwind."""
        near = [
            ray
            for index, ray in enumerate(self.rays)
            if angle_between(index * STEP_DEGREES, direction) <= FETCH_SECTOR + 1e-9
        ]
        return sum(near) / len(near) if near else 0.0

    @property
    def exposed(self) -> tuple[str, ...]:
        """Return the compass points with open water to the full distance."""
        return tuple(
            point
            for number, point in enumerate(DIRECTIONS)
            if any(
                ray >= REACH_KM - 0.01
                and angle_between(index * STEP_DEGREES, number * 45) <= 22.5
                for index, ray in enumerate(self.rays)
            )
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the shoreline as JSON-ready data."""
        return {
            "on_water": self.on_water,
            "rays": list(self.rays),
            "measured": self.measured.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Shoreline:
        """Read a shoreline kept on disk."""
        return cls(
            on_water=bool(data["on_water"]),
            rays=tuple(float(ray) for ray in data["rays"]),
            measured=datetime.fromisoformat(data["measured"]),
        )


def measure(
    latitude: float, longitude: float, tiles: Iterable[WaterTile]
) -> tuple[bool, tuple[float, ...]]:
    """Return whether a pin is on water, and how far the water reaches each way."""
    water = _Water(latitude, longitude, tiles)
    if not water.contains(0.0, 0.0):
        return False, ()
    return True, tuple(
        round(water.reach(index * STEP_DEGREES, REACH_KM), 2) for index in range(RAYS)
    )


@dataclass(slots=True)
class _Tile:
    """A tile's water in km east and north of the pin."""

    bounds: tuple[float, float, float, float]  # west, south, east, north
    polygons: list[list[list[Point]]]
    edges: list[tuple[float, float, float, float]]


class _Water:
    """The water around a pin, in km east and north of it."""

    def __init__(
        self, latitude: float, longitude: float, tiles: Iterable[WaterTile]
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.east_km = KM_PER_DEGREE * math.cos(math.radians(latitude))
        self.tiles = [self._tile(tile) for tile in tiles]

    def _local(self, latitude: float, longitude: float) -> Point:
        return (
            (longitude - self.longitude) * self.east_km,
            (latitude - self.latitude) * KM_PER_DEGREE,
        )

    def _tile(self, tile: WaterTile) -> _Tile:
        west, north = self._local(*openfreemap.position(tile, 0, 0))
        east, south = self._local(*openfreemap.position(tile, tile.extent, tile.extent))
        polygons = [
            [
                [self._local(*openfreemap.position(tile, x, y)) for x, y in ring]
                for ring in polygon
            ]
            for polygon in tile.polygons
        ]
        edges = [
            (x1, y1, x2, y2)
            for polygon in polygons
            for ring in polygon
            for (x1, y1), (x2, y2) in pairwise(ring)
        ]
        return _Tile((west, south, east, north), polygons, edges)

    def contains(self, x: float, y: float) -> bool:
        """Return whether a point is on water, by the tile it's in."""
        for tile in self.tiles:
            west, south, east, north = tile.bounds
            if west <= x <= east and south <= y <= north:
                return any(_inside(x, y, polygon) for polygon in tile.polygons)
        return False

    def reach(self, bearing: float, limit: float) -> float:
        """Return how far the water goes from the pin toward a bearing."""
        dx, dy = math.sin(math.radians(bearing)), math.cos(math.radians(bearing))
        end_x, end_y = dx * limit, dy * limit
        crossings = []
        for tile in self.tiles:
            west, south, east, north = tile.bounds
            if (
                max(0.0, end_x) < west
                or min(0.0, end_x) > east
                or max(0.0, end_y) < south
                or min(0.0, end_y) > north
            ):
                continue
            for x1, y1, x2, y2 in tile.edges:
                ex, ey = x2 - x1, y2 - y1
                denominator = dx * ey - dy * ex
                if abs(denominator) < 1e-12:
                    continue
                t = (x1 * ey - y1 * ex) / denominator
                u = (x1 * dy - y1 * dx) / denominator
                if not (0.0 <= u <= 1.0 and 0.0 < t < limit):
                    continue
                # Cuts at a tile's edges lie outside its own area.
                x, y = dx * t, dy * t
                if (
                    west - 1e-6 <= x <= east + 1e-6
                    and south - 1e-6 <= y <= north + 1e-6
                ):
                    crossings.append(t)
        start = 0.0
        for end in [*sorted(crossings), limit]:
            if end - start < 1e-6:
                continue
            middle = (start + end) / 2
            if start > 0.0 and not self.contains(dx * middle, dy * middle):
                return start
            start = end
        return limit


def _inside(x: float, y: float, polygon: Sequence[Sequence[Point]]) -> bool:
    """Return whether a point is in a polygon: inside an odd number of its rings."""
    inside = False
    for ring in polygon:
        for (x1, y1), (x2, y2) in pairwise(ring):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


class Shorelines:
    """Each pin's shoreline, measured once and kept on disk.

    It lives as long as Home Assistant does, so reloading the entry after a
    settings change doesn't measure anything again.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the store."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._known: dict[str, Shoreline] = {}
        self._failed: dict[str, datetime] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    @staticmethod
    def key(latitude: float, longitude: float) -> str:
        """Return the key a pin's shoreline is kept under."""
        return f"{latitude:.4f},{longitude:.4f}"

    async def async_load(self) -> None:
        """Read the shorelines measured before."""
        if self._loaded:
            return
        self._loaded = True
        stored = await self._store.async_load()
        for key, data in ((stored or {}).get("pins") or {}).items():
            try:
                self._known[key] = Shoreline.from_dict(data)
            except KeyError, TypeError, ValueError:
                LOGGER.warning("Ignoring an unreadable saved shoreline")

    def get(self, latitude: float, longitude: float) -> Shoreline | None:
        """Return a pin's shoreline, if it's been measured."""
        return self._known.get(self.key(latitude, longitude))

    async def async_measure(
        self,
        latitude: float,
        longitude: float,
        tiles: dict[tuple[int, int, int], WaterTile] | None = None,
    ) -> Shoreline:
        """Return a pin's shoreline, measuring it if it hasn't been.

        Tiles fetched are added to `tiles`, so pins measured together share
        them. Raises ProviderError if the map tiles can't be fetched or read.
        """
        await self.async_load()
        key = self.key(latitude, longitude)
        tiles = {} if tiles is None else tiles
        async with self._lock:
            if (known := self._known.get(key)) is not None:
                return known
            session = async_get_clientsession(self.hass)
            template = await openfreemap.async_get_template(session)
            limit = asyncio.Semaphore(TILES_AT_ONCE)

            async def fetch(z: int, x: int, y: int) -> None:
                async with limit:
                    tiles[z, x, y] = await openfreemap.async_get_water(
                        session, template, z, x, y
                    )

            around = openfreemap.tiles_around(latitude, longitude, REACH_KM)
            await asyncio.gather(
                *(fetch(*tile) for tile in sorted(around) if tile not in tiles)
            )
            on_water, rays = await self.hass.async_add_executor_job(
                measure, latitude, longitude, [tiles[tile] for tile in sorted(around)]
            )
            shoreline = Shoreline(on_water, rays, dt_util.utcnow())
            self._known[key] = shoreline
            self._failed.pop(key, None)
            self._store.async_delay_save(self._data, 1)
            return shoreline

    async def async_measure_pins(self, pins: Iterable[Point]) -> bool:
        """Measure the pins not measured yet; return whether any were.

        A pin that fails is tried again after a while, and shorelines no pin
        uses any more are forgotten after a day.
        """
        await self.async_load()
        now = dt_util.utcnow()
        wanted = {self.key(*pin): pin for pin in pins}
        tiles: dict[tuple[int, int, int], WaterTile] = {}
        changed = False
        for key, (latitude, longitude) in wanted.items():
            failed = self._failed.get(key)
            if key in self._known or (failed and now - failed < RETRY_AFTER):
                continue
            try:
                await self.async_measure(latitude, longitude, tiles)
            except ProviderError as err:
                LOGGER.warning("Couldn't measure a spot's shoreline: %s", err)
                self._failed[key] = now
                continue
            changed = True
        stale = [
            key
            for key, shoreline in self._known.items()
            if key not in wanted and now - shoreline.measured > KEEP_UNUSED
        ]
        for key in stale:
            del self._known[key]
        if stale:
            self._store.async_delay_save(self._data, 1)
        return changed

    def _data(self) -> dict[str, Any]:
        return {"pins": {key: item.as_dict() for key, item in self._known.items()}}
