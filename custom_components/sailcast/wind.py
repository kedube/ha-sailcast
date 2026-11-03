"""The wind map's grid: the wind on a regular grid of points around the spots.

A grid is fetched only when someone opens the wind map, never in the
background. It covers a spot's wind map circle, or the circles of nearby
spots that overlap, with at most 15 x 15 points about 2 km apart, and it's
kept for three hours. Each point costs one of Open-Meteo's 10,000 daily
calls, so SailCast stops fetching grids at 6,000 calls in a day, leaving the
rest for the forecast, and shows the last grid it has instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Any, Final

import aiohttp
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .coordinator import Budget
from .geo import distance_km
from .profiles import Spot
from .providers import ProviderError, open_meteo

KM_PER_DEGREE: Final = 111.32
MAX_POINTS: Final = 15
MIN_SPACING_KM: Final = 2.0
# Spots whose circles overlap share a grid while its points stay this close.
MAX_SHARED_SPACING_KM: Final = 3.0
KEEP: Final = timedelta(hours=3)
# Old grids are still shown when no new one can be fetched, for this long.
KEEP_STALE: Final = timedelta(days=1)
STOP_AT: Final = 6000

DATA_WIND: HassKey[WindGrids] = HassKey(f"{DOMAIN}_wind")


@dataclass(frozen=True, slots=True)
class GridArea:
    """Where a grid's points are: its corners in degrees and its points a side.

    `spots` are the IDs of the spots it covers.
    """

    south: float
    west: float
    north: float
    east: float
    rows: int
    cols: int
    spots: tuple[str, ...]

    @property
    def points(self) -> list[tuple[float, float]]:
        """Return the points, a row at a time from the south-west corner."""
        return [
            (
                self.south + (self.north - self.south) * row / (self.rows - 1),
                self.west + (self.east - self.west) * col / (self.cols - 1),
            )
            for row in range(self.rows)
            for col in range(self.cols)
        ]

    @property
    def spacing_km(self) -> float:
        """Return the largest distance between neighboring points."""
        middle = math.radians((self.south + self.north) / 2)
        height = (self.north - self.south) * KM_PER_DEGREE / (self.rows - 1)
        width = (
            (self.east - self.west) * KM_PER_DEGREE * math.cos(middle) / (self.cols - 1)
        )
        return max(height, width)

    @property
    def key(self) -> tuple[float, float, float, float, int, int]:
        """Return what identifies the grid's points, for the cache."""
        return (
            round(self.south, 4),
            round(self.west, 4),
            round(self.north, 4),
            round(self.east, 4),
            self.rows,
            self.cols,
        )


def area_for(spots: Sequence[Spot]) -> GridArea:
    """Return a grid over the spots' circles, with points about 2 km apart."""
    south = min(spot.latitude - _lat_degrees(spot.radius) for spot in spots)
    north = max(spot.latitude + _lat_degrees(spot.radius) for spot in spots)
    west = min(spot.longitude - _lon_degrees(spot) for spot in spots)
    east = max(spot.longitude + _lon_degrees(spot) for spot in spots)
    middle = math.radians((south + north) / 2)
    height = (north - south) * KM_PER_DEGREE
    width = (east - west) * KM_PER_DEGREE * math.cos(middle)
    return GridArea(
        south=south,
        west=west,
        north=north,
        east=east,
        rows=_points_along(height),
        cols=_points_along(width),
        spots=tuple(sorted(spot.id for spot in spots)),
    )


def areas(spots: Iterable[Spot]) -> dict[str, GridArea]:
    """Return each spot's grid. Spots whose circles overlap share one.

    Overlapping spots share a grid as long as its points stay within 3 km of
    each other; otherwise each gets its own.
    """
    found = list(spots)
    group = {spot.id: spot.id for spot in found}

    def root(spot: str) -> str:
        while group[spot] != spot:
            group[spot] = group[group[spot]]
            spot = group[spot]
        return spot

    for index, first in enumerate(found):
        for second in found[index + 1 :]:
            apart = distance_km(
                first.latitude, first.longitude, second.latitude, second.longitude
            )
            if apart * 1000 < first.radius + second.radius:
                group[root(first.id)] = root(second.id)
    clusters: dict[str, list[Spot]] = {}
    for spot in found:
        clusters.setdefault(root(spot.id), []).append(spot)
    result = {}
    for members in clusters.values():
        shared = area_for(members)
        if len(members) > 1 and shared.spacing_km > MAX_SHARED_SPACING_KM:
            result.update({spot.id: area_for([spot]) for spot in members})
        else:
            result.update(dict.fromkeys((spot.id for spot in members), shared))
    return result


def _lat_degrees(meters: float) -> float:
    return meters / 1000 / KM_PER_DEGREE


def _lon_degrees(spot: Spot) -> float:
    return _lat_degrees(spot.radius) / math.cos(math.radians(spot.latitude))


def _points_along(km: float) -> int:
    # Rounding first keeps 20.000000000000004 km at 11 points, not 12.
    return min(MAX_POINTS, max(2, math.ceil(round(km / MIN_SPACING_KM, 6)) + 1))


@dataclass(frozen=True, slots=True)
class WindGrid:
    """The wind on a grid, hour by hour.

    Each hour has one value per point, in the order of `area.points`: speeds
    and gusts in knots, directions in degrees the wind comes from.
    """

    area: GridArea
    fetched: datetime
    times: tuple[datetime, ...]
    speed: tuple[tuple[float | None, ...], ...]
    direction: tuple[tuple[float | None, ...], ...]
    gust: tuple[tuple[float | None, ...], ...]

    @classmethod
    def from_points(
        cls, area: GridArea, fetched: datetime, wind: open_meteo.WindPoints
    ) -> WindGrid:
        """Turn each point's series into each hour's values."""
        return cls(
            area=area,
            fetched=fetched,
            times=wind.times,
            speed=tuple(zip(*wind.speed, strict=True)),
            direction=tuple(zip(*wind.direction, strict=True)),
            gust=tuple(zip(*wind.gust, strict=True)),
        )

    def as_dict(self, now: datetime, *, stale: bool) -> dict[str, Any]:
        """Return the hours from the one under way, for the panel."""
        first = next(
            (
                index
                for index, time in enumerate(self.times)
                if time + timedelta(hours=1) > now
            ),
            len(self.times),
        )

        def rounded(
            hours: Sequence[Sequence[float | None]], digits: int | None
        ) -> list[list[float | None]]:
            return [
                [None if value is None else round(value, digits) for value in hour]
                for hour in hours[first:]
            ]

        area = self.area
        return {
            "fetched": self.fetched.isoformat(),
            "stale": stale,
            "south": area.south,
            "west": area.west,
            "north": area.north,
            "east": area.east,
            "rows": area.rows,
            "cols": area.cols,
            "spots": list(area.spots),
            "times": [time.isoformat() for time in self.times[first:]],
            "speed": rounded(self.speed, 1),
            "gust": rounded(self.gust, 1),
            "direction": rounded(self.direction, None),
        }


class BudgetSpentError(Exception):
    """No grid can be fetched today, and there's none to show."""


class WindGrids:
    """The grids fetched so far, kept for three hours, within the budget."""

    def __init__(self) -> None:
        """Start with no grids."""
        self._grids: dict[tuple[float, float, float, float, int, int], WindGrid] = {}
        self._locks: dict[
            tuple[float, float, float, float, int, int], asyncio.Lock
        ] = {}

    @property
    def grids(self) -> list[WindGrid]:
        """Return the grids kept now."""
        return list(self._grids.values())

    async def async_get(
        self, session: aiohttp.ClientSession, area: GridArea, budget: Budget
    ) -> tuple[WindGrid, bool]:
        """Return an area's grid, and whether it's older than three hours.

        A grid older than that is fetched again, unless that would take the
        day's calls past STOP_AT or the fetch fails; then the old one is
        returned, for up to a day. Raise BudgetSpentError if there's none, or the
        provider's error if fetching failed.
        """
        key = area.key
        async with self._locks.setdefault(key, asyncio.Lock()):
            now = dt_util.utcnow()
            self._forget_before(now - KEEP_STALE)
            grid = self._grids.get(key)
            if grid is not None and now - grid.fetched < KEEP:
                return grid, False
            cost = open_meteo.wind_calls(len(area.points))
            if budget.today + cost > STOP_AT:
                if grid is None:
                    raise BudgetSpentError
                return grid, True
            try:
                wind = await open_meteo.async_get_wind(session, area.points)
            except ProviderError:
                if grid is None:
                    raise
                return grid, True
            budget.add(cost)
            grid = WindGrid.from_points(area, now, wind)
            self._grids[key] = grid
            return grid, False

    def _forget_before(self, when: datetime) -> None:
        for key in [key for key, grid in self._grids.items() if grid.fetched < when]:
            del self._grids[key]
