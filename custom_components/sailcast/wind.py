"""The wind map's grids: the wind on a regular grid of points.

A grid is fetched only when someone opens or moves the wind map, never in
the background. The map opens on a spot's wind map circle, or the circles of
nearby spots that overlap, with at most 15 x 15 points about 2 km apart. As
it moves, it gets a grid for what it shows and a little past it: a kept one
that covers the view finely enough, or a new one on a lattice of the finest
spacing that fits the view in 15 points a side, so nearby views share it.
Grids are kept for three hours.

Each point costs one of Open-Meteo's free calls, which stop at 600 a minute,
5,000 an hour and 10,000 a day. Grids keep to 450 a minute and 4,000 an
hour, and SailCast stops fetching them at 6,000 calls in a day, leaving the
rest for the forecast. When no grid can be fetched, the last one stands in.
"""

from __future__ import annotations

import asyncio
from collections import deque
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
# A view's grid: the finest of these spacings (km) that fits it in 15 points a
# side, reaching this share of the view's size past each edge.
SPACINGS_KM: Final = (2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96)
VIEW_MARGIN: Final = 0.15
# A kept grid serves a view if its points are at most this much further apart
# than the view's own grid's would be.
COARSER: Final = 1.25
# The grids' share of Open-Meteo's free calls a minute and an hour.
MINUTE_CALLS: Final = 450
HOUR_CALLS: Final = 4000
LIMITS: Final = ((timedelta(minutes=1), MINUTE_CALLS), (timedelta(hours=1), HOUR_CALLS))

DATA_WIND: HassKey[WindGrids] = HassKey(f"{DOMAIN}_wind")

# A map view's south, west, north and east edges, in degrees.
type Bounds = tuple[float, float, float, float]


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

    def covers(self, view: Bounds) -> bool:
        """Return whether the grid reaches every edge of a view, or nearly.

        A view may pass an edge by 1% of the grid's size, a sliver the map
        barely shows: a map fitted to a grid's edge can land just past it.
        """
        south, west, north, east = view
        tall = (self.north - self.south) * 0.01
        wide = (self.east - self.west) * 0.01
        return (
            self.south - tall <= south
            and self.west - wide <= west
            and self.north + tall >= north
            and self.east + wide >= east
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


def view_area(view: Bounds, spots: Iterable[Spot]) -> GridArea:
    """Return the grid for a map view, reaching a little past its edges.

    Its points sit on a lattice of the finest spacing that fits it in 15
    points a side, so nearby views share a grid. A view too wide even for the
    widest spacing gets a grid over its middle.
    """
    south, west, north, east = view
    lat_margin = (north - south) * VIEW_MARGIN
    lon_margin = (east - west) * VIEW_MARGIN
    # Longitude steps follow the whole degree of latitude nearest the view's
    # middle, so panning keeps the same lattice.
    narrowing = math.cos(math.radians(round((south + north) / 2)))
    for spacing in SPACINGS_KM:
        lat_step = spacing / KM_PER_DEGREE
        lon_step = lat_step / narrowing
        lats = _lattice(south - lat_margin, north + lat_margin, lat_step)
        lons = _lattice(west - lon_margin, east + lon_margin, lon_step)
        if lats[2] <= MAX_POINTS and lons[2] <= MAX_POINTS:
            break
    else:
        lats = _lattice_middle(south, north, lat_step)
        lons = _lattice_middle(west, east, lon_step)
    (area_south, area_north, rows), (area_west, area_east, cols) = lats, lons
    return GridArea(
        south=area_south,
        west=area_west,
        north=area_north,
        east=area_east,
        rows=rows,
        cols=cols,
        spots=tuple(
            sorted(
                spot.id
                for spot in spots
                if area_south <= spot.latitude <= area_north
                and area_west <= spot.longitude <= area_east
            )
        ),
    )


def _lattice(low: float, high: float, step: float) -> tuple[float, float, int]:
    """Return the lattice lines at or just past each end, and the points between."""
    # Rounding first keeps a range that ends on a line from reaching the next.
    first = math.floor(round(low / step, 6))
    last = max(math.ceil(round(high / step, 6)), first + 1)
    return first * step, last * step, last - first + 1


def _lattice_middle(low: float, high: float, step: float) -> tuple[float, float, int]:
    """Return 15 lattice points around the middle of a range."""
    first = round((low + high) / 2 / step) - MAX_POINTS // 2
    return first * step, (first + MAX_POINTS - 1) * step, MAX_POINTS


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

    @property
    def id(self) -> str:
        """Return what tells this grid from others: its points and when it came."""
        return f"{','.join(map(str, self.area.key))}@{self.fetched.isoformat()}"

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
            "id": self.id,
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


class TooSoonError(Exception):
    """A grid now would go past the grids' calls for a minute or an hour."""

    def __init__(self, seconds: float) -> None:
        """Say how many seconds until it fits."""
        super().__init__(f"No grid for {seconds:.0f} s")
        self.seconds = seconds


class WindGrids:
    """The grids fetched so far, kept for three hours, within the budget."""

    def __init__(self) -> None:
        """Start with no grids."""
        self._grids: dict[tuple[float, float, float, float, int, int], WindGrid] = {}
        self._locks: dict[
            tuple[float, float, float, float, int, int], asyncio.Lock
        ] = {}
        # When each grid was asked for and its calls, for the limits a minute
        # and an hour.
        self._spent: deque[tuple[datetime, float]] = deque()

    @property
    def grids(self) -> list[WindGrid]:
        """Return the grids kept now."""
        return list(self._grids.values())

    async def async_get(
        self, session: aiohttp.ClientSession, area: GridArea, budget: Budget
    ) -> tuple[WindGrid, bool]:
        """Return an area's grid, and whether it's older than three hours.

        A grid older than that is fetched again, unless that would take the
        day's calls past STOP_AT or the grids' calls a minute or an hour past
        their limits, or the fetch fails; then the old one is returned, for up
        to a day. If there's none, raise BudgetSpentError, TooSoonError or the
        provider's error.
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
            if wait := self._wait(cost, now):
                if grid is None:
                    raise TooSoonError(wait)
                return grid, True
            # Counted before asking, so grids asked for together keep within it.
            self._spent.append((now, cost))
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

    async def async_get_view(
        self,
        session: aiohttp.ClientSession,
        view: Bounds,
        spots: Iterable[Spot],
        budget: Budget,
    ) -> tuple[WindGrid | None, bool, float | None]:
        """Return a grid for a map view, whether it's stale, and when to ask again.

        A kept grid that covers the view finely enough comes first, then a new
        one. When none can be fetched, the finest kept grid that covers the
        view stands in, stale if it's older than three hours, or None; if
        waiting would bring one, the seconds to wait come with it. Raise
        BudgetSpentError or the provider's error when there's none to show.
        """
        area = view_area(view, spots)
        now = dt_util.utcnow()
        self._forget_before(now - KEEP_STALE)
        if found := self._covering(view, area.spacing_km * COARSER, now - KEEP):
            return found, False, None
        try:
            grid, stale = await self.async_get(session, area, budget)
        except TooSoonError as err:
            retry: float | None = err.seconds
        except BudgetSpentError, ProviderError:
            if not self._covering(view, math.inf, now - KEEP_STALE):
                raise
            retry = None
        else:
            return grid, stale, None
        old = self._covering(view, math.inf, now - KEEP_STALE)
        return old, old is not None and now - old.fetched >= KEEP, retry

    def _covering(
        self, view: Bounds, spacing_km: float, since: datetime
    ) -> WindGrid | None:
        """Return the finest grid fetched since a time that covers a view.

        Its points must be no further apart than `spacing_km`.
        """
        found = [
            grid
            for grid in self._grids.values()
            if grid.fetched >= since
            and grid.area.covers(view)
            and grid.area.spacing_km <= spacing_km
        ]
        return min(
            found,
            key=lambda grid: (grid.area.spacing_km, -grid.fetched.timestamp()),
            default=None,
        )

    def _wait(self, cost: float, now: datetime) -> float:
        """Return the seconds until `cost` more calls keep within the limits."""
        longest = max(span for span, _ in LIMITS)
        while self._spent and now - self._spent[0][0] >= longest:
            self._spent.popleft()
        wait = 0.0
        for span, limit in LIMITS:
            recent = [(when, calls) for when, calls in self._spent if now - when < span]
            total = sum(calls for _, calls in recent) + cost
            # The oldest calls age out first.
            for when, calls in recent:
                if total <= limit:
                    break
                total -= calls
                wait = max(wait, (when + span - now).total_seconds())
        return wait

    def _forget_before(self, when: datetime) -> None:
        for key in [key for key, grid in self._grids.items() if grid.fetched < when]:
            del self._grids[key]
