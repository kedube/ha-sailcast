"""Tests for the wind map's grid: where its points go, sharing, and the budget."""

from __future__ import annotations

import contextlib
from datetime import timedelta
import math

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.coordinator import Budget
from custom_components.sailcast.profiles import Spot, WaterType
from custom_components.sailcast.providers import ProviderError, open_meteo
from custom_components.sailcast.wind import (
    KEEP,
    STOP_AT,
    BudgetSpentError,
    WindGrids,
    area_for,
    areas,
)

from .conftest import BAY_POINT, HARBOR_POINT, RECORDED, RIVER_POINT, mock_wind


def spot(key: str, point: tuple[float, float], radius: float = 10_000) -> Spot:
    """Return a spot with a wind map circle."""
    return Spot(
        id=key,
        name=key.title(),
        latitude=point[0],
        longitude=point[1],
        radius=radius,
        water_type=WaterType.BAY,
    )


HARBOR = spot("harbor", HARBOR_POINT)
BAY = spot("bay", BAY_POINT)
RIVER = spot("river", RIVER_POINT)
# Made-up spots far from the others and from each other, with circles big
# enough for a full 15 x 15 grid each: the most a spot can cost.
FAR = (
    spot("north", (33.6, -117.9), radius=15_000),
    spot("island", (33.4, -118.4), radius=15_000),
    spot("south", (32.0, -116.9), radius=15_000),
)


def test_one_spot() -> None:
    """A 10 km circle gets 11 x 11 points, 2 km apart."""
    area = area_for([HARBOR])
    assert (area.rows, area.cols) == (11, 11)
    assert area.spacing_km == pytest.approx(2.0, abs=0.01)
    assert area.south == pytest.approx(HARBOR_POINT[0] - 10 / 111.32)
    assert area.north == pytest.approx(HARBOR_POINT[0] + 10 / 111.32)
    width = 10 / 111.32 / math.cos(math.radians(HARBOR_POINT[0]))
    assert area.west == pytest.approx(HARBOR_POINT[1] - width)
    points = area.points
    assert len(points) == 121
    assert points[0] == pytest.approx((area.south, area.west))
    assert points[-1] == pytest.approx((area.north, area.east))
    # A row at a time from the south-west.
    assert points[1][0] == pytest.approx(area.south)
    assert points[11][1] == pytest.approx(area.west)


def test_big_circle() -> None:
    """A big circle keeps 15 x 15 points and spreads them out."""
    area = area_for([spot("wide", HARBOR_POINT, radius=50_000)])
    assert (area.rows, area.cols) == (15, 15)
    assert area.spacing_km == pytest.approx(100 / 14, abs=0.05)


def test_overlapping_spots_share() -> None:
    """The three test spots overlap, so one 15 x 15 grid covers them all."""
    found = areas([HARBOR, BAY, RIVER, *FAR])
    shared = found["harbor"]
    assert found["bay"] is shared
    assert found["river"] is shared
    assert shared.spots == ("bay", "harbor", "river")
    assert (shared.rows, shared.cols) == (15, 15)
    assert shared.spacing_km < 3
    # Spots far away each have their own.
    assert len({found[far.id].key for far in FAR}) == 3
    assert found["north"].spots == ("north",)


def test_overlapping_but_spread_out() -> None:
    """Overlapping circles that would need points over 3 km apart don't share."""
    wide = spot("wide", HARBOR_POINT, radius=30_000)
    other = spot("other", (HARBOR_POINT[0] + 0.4, HARBOR_POINT[1]), radius=30_000)
    found = areas([wide, other])
    assert found["wide"].spots == ("wide",)
    assert found["other"].spots == ("other",)


async def test_kept_for_three_hours(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A grid is fetched once, kept three hours, and its calls are counted."""
    mock_wind(aioclient_mock)
    freezer.move_to(RECORDED.replace(hour=1))
    grids, budget = WindGrids(), Budget()
    area = area_for([HARBOR])
    session = async_get_clientsession(hass)

    grid, stale = await grids.async_get(session, area, budget)
    assert not stale
    assert aioclient_mock.call_count == 1
    assert budget.today == 121
    assert len(grid.times) == 168
    assert len(grid.speed[0]) == 121

    freezer.tick(KEEP - timedelta(minutes=1))
    assert (await grids.async_get(session, area, budget))[0] is grid
    assert aioclient_mock.call_count == 1

    freezer.tick(timedelta(minutes=2))
    fresh, stale = await grids.async_get(session, area, budget)
    assert fresh is not grid
    assert not stale
    assert budget.today == 242


async def test_payload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The panel gets the hours from the one under way, rounded."""
    mock_wind(aioclient_mock)
    freezer.move_to(RECORDED)
    area = area_for([HARBOR])
    grid, _ = await WindGrids().async_get(async_get_clientsession(hass), area, Budget())
    payload = grid.as_dict(RECORDED, stale=False)
    # 2:36 PM in San Diego is 22:36 UTC, so the hour under way began at 22:00.
    assert payload["times"][0] == "2026-11-02T22:00:00+00:00"
    assert len(payload["times"]) == 168 - 22
    assert (payload["rows"], payload["cols"]) == (11, 11)
    assert payload["spots"] == ["harbor"]
    # Hour 22 of the made-up wind: 5 + 22 kt at the southern row, from the west.
    assert payload["speed"][0][0] == 27.0
    assert payload["gust"][0][0] == 33.0
    assert payload["direction"][0][0] == 270
    assert payload["speed"][0][-1] > payload["speed"][0][0]


async def test_budget_guard(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Near the day's limit, the last grid is shown instead of fetching another."""
    mock_wind(aioclient_mock)
    # Early in the day (UTC), so the count doesn't start again before the end.
    freezer.move_to(RECORDED.replace(hour=1))
    grids, budget = WindGrids(), Budget()
    area = area_for([HARBOR])
    session = async_get_clientsession(hass)
    old, _ = await grids.async_get(session, area, budget)

    budget.add(STOP_AT - budget.today - 100)
    freezer.tick(KEEP + timedelta(minutes=1))
    grid, stale = await grids.async_get(session, area, budget)
    assert grid is old
    assert stale
    assert aioclient_mock.call_count == 1

    with pytest.raises(BudgetSpentError):
        await grids.async_get(session, area_for([BAY]), budget)


async def test_failure_keeps_the_old_grid(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """When a fetch fails, the last grid is shown; with none, the error stands."""
    freezer.move_to(RECORDED.replace(hour=1))
    mock_wind(aioclient_mock)
    grids, budget = WindGrids(), Budget()
    area = area_for([HARBOR])
    session = async_get_clientsession(hass)
    old, _ = await grids.async_get(session, area, budget)

    aioclient_mock.clear_requests()
    aioclient_mock.get(open_meteo.FORECAST_URL, status=502)
    freezer.tick(KEEP + timedelta(minutes=1))
    assert await grids.async_get(session, area, budget) == (old, True)
    with pytest.raises(ProviderError):
        await grids.async_get(session, area_for([BAY]), budget)


async def test_a_day_with_three_spots(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Three spots, each with a grid of its own, opened every ten minutes all day.

    Each grid is fetched every three hours, 8 times a day: 3 x 8 x 225 =
    5,400 calls. The forecast and marine data use about 300 more, so the
    day never reaches the 6,000 where grids stop, and stays well under
    Open-Meteo's 10,000.
    """
    mock_wind(aioclient_mock)
    freezer.move_to(RECORDED.replace(hour=0, minute=0))
    grids, budget = WindGrids(), Budget()
    found = areas(FAR)
    session = async_get_clientsession(hass)
    for step in range(24 * 6):
        if step:
            freezer.tick(timedelta(minutes=10))
        for far in FAR:
            await grids.async_get(session, found[far.id], budget)
    assert aioclient_mock.call_count == 3 * 8
    assert budget.today == 3 * 8 * 225
    forecast = 24 * open_meteo.forecast_calls(3) + 8 * open_meteo.marine_calls(3)
    assert budget.today + forecast < STOP_AT


async def test_more_spots_than_the_budget_allows(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With many far-apart spots, fetching stops at 6,000 calls in a day."""
    mock_wind(aioclient_mock)
    freezer.move_to(RECORDED.replace(hour=0, minute=0))
    grids, budget = WindGrids(), Budget()
    many = [spot(f"spot{n}", (30.0 + n * 0.5, -117.0)) for n in range(12)]
    found = areas(many)
    session = async_get_clientsession(hass)
    for step in range(8):
        if step:
            freezer.tick(KEEP)
        for each in many:
            with contextlib.suppress(BudgetSpentError):
                await grids.async_get(session, found[each.id], budget)
    assert budget.today <= STOP_AT
    assert budget.today > STOP_AT - 121
