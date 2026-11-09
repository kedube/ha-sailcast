"""Tests for measuring fetch and exposure from the shoreline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.providers import ProviderError, openfreemap
from custom_components.sailcast.providers.openfreemap import WaterTile
from custom_components.sailcast.shoreline import (
    DATA_SHORELINES,
    REACH_KM,
    RETRY_AFTER,
    STORAGE_KEY,
    Shoreline,
    Shorelines,
    measure,
)

from .conftest import (
    BAY_POINT,
    FIXTURES,
    HARBOR_POINT,
    RECORDED,
    RIVER_POINT,
    TILE_URL,
    mock_sources,
    mock_tiles,
    set_up,
)

# A tile on the equator, about 9.8 km across; the pin is in its middle.
Z, X, Y = 12, 2048, 2048
UNIT_KM = 360 / 2**Z / 4096 * 111.195


def square(left: float, top: float, right: float, bottom: float) -> tuple[Any, ...]:
    """Return a closed ring in a tile's units."""
    return ((left, top), (right, top), (right, bottom), (left, bottom), (left, top))


def tile(*polygons: tuple[Any, ...], x: int = X, y: int = Y) -> WaterTile:
    """Return a tile with water polygons, each a tuple of rings."""
    return WaterTile(Z, x, y, 4096, tuple(polygons))


def pin() -> tuple[float, float]:
    """Return the middle of the test tile."""
    return openfreemap.position(tile(), 2048, 2048)


def rays(*tiles: WaterTile) -> tuple[float, ...]:
    """Measure the pin in the middle of the test tile."""
    on_water, found = measure(*pin(), tiles)
    assert on_water
    return found


def test_lake() -> None:
    """In a square lake, the water reaches the shore each way."""
    found = rays(tile((square(1024, 1024, 3072, 3072),)))
    assert len(found) == 120
    half = 1024 * UNIT_KM
    for index in (0, 30, 60, 90):  # north, east, south and west
        assert found[index] == pytest.approx(half, rel=0.01)
    # The corners are further.
    assert found[15] == pytest.approx(half * 2**0.5, rel=0.01)


def test_island() -> None:
    """An island stops the water: a hole in the lake."""
    lake = (square(1024, 1024, 3072, 3072), square(2500, 1948, 2700, 2148))
    found = rays(tile(lake))
    assert found[30] == pytest.approx((2500 - 2048) * UNIT_KM, rel=0.01)
    assert found[90] == pytest.approx(1024 * UNIT_KM, rel=0.01)


def test_overlapping_water() -> None:
    """Where a river overlaps the lake, the water goes on up the river."""
    lake = (square(1024, 1024, 3072, 3072),)
    river = (square(2900, 1948, 3800, 2148),)
    found = rays(tile(lake, river))
    assert found[30] == pytest.approx((3800 - 2048) * UNIT_KM, rel=0.01)


def test_tile_seam() -> None:
    """Water cut at a tile's edge goes on in the next tile."""
    west = tile((square(1024, 1024, 4160, 3072),))
    east = tile((square(-64, 1024, 2048, 3072),), x=X + 1)
    found = rays(west, east)
    assert found[30] == pytest.approx(4096 * UNIT_KM, rel=0.01)


def test_open_sea() -> None:
    """Water that reaches 20 km each way is open from every side."""
    sea = [
        tile((square(-64, -64, 4160, 4160),), x=X + dx, y=Y + dy)
        for dx in range(-3, 4)
        for dy in range(-3, 4)
    ]
    found = rays(*sea)
    assert set(found) == {REACH_KM}
    shoreline = Shoreline(True, found, RECORDED)
    assert shoreline.exposed == ("n", "ne", "e", "se", "s", "sw", "w", "nw")
    assert shoreline.fetch(123) == REACH_KM


def test_pin_on_land() -> None:
    """A pin outside every water polygon is on land."""
    assert measure(*pin(), [tile((square(0, 0, 1000, 1000),))]) == (False, ())
    assert measure(*pin(), []) == (False, ())


def test_fetch_averages_near_the_wind() -> None:
    """Fetch averages the rays within 15 degrees; exposure needs the full reach."""
    rays_ = [1.0] * 120
    rays_[90] = REACH_KM  # due west
    shoreline = Shoreline(True, tuple(rays_), RECORDED)
    assert shoreline.fetch(270) == pytest.approx((10 + REACH_KM) / 11)
    assert shoreline.fetch(240) == 1.0
    assert shoreline.exposed == ("w",)


def recorded(point: tuple[float, float]) -> list[WaterTile]:
    """Return the recorded tiles around a point."""
    tiles = []
    for z, x, y in sorted(openfreemap.tiles_around(*point, REACH_KM)):
        body = (FIXTURES / "tiles" / str(z) / str(x) / f"{y}.pbf").read_bytes()
        tiles.append(openfreemap.water(body, z, x, y))
    return tiles


def test_recorded_pins() -> None:
    """The harbor opens onto the ocean; the bay is on land; the river is a basin."""
    on_water, found = measure(*HARBOR_POINT, recorded(HARBOR_POINT))
    assert on_water
    harbor = Shoreline(on_water, found, RECORDED)
    assert {"sw", "w", "nw"} <= set(harbor.exposed)
    assert harbor.fetch(270) == REACH_KM
    # Ocean Beach is a mile and a bit east.
    assert harbor.fetch(90) == pytest.approx(1.6, abs=0.2)

    assert measure(*BAY_POINT, recorded(BAY_POINT)) == (False, ())

    on_water, found = measure(*RIVER_POINT, recorded(RIVER_POINT))
    river = Shoreline(on_water, found, RECORDED)
    assert river.exposed == ()
    assert max(river.fetch(direction) for direction in range(0, 360, 15)) < 0.6


def test_reading_a_tile() -> None:
    """A recorded tile's water is read from its protocol buffer."""
    z, x, y = 12, 714, 1653
    body = (FIXTURES / "tiles" / str(z) / str(x) / f"{y}.pbf").read_bytes()
    water = openfreemap.water(body, z, x, y)
    assert water.extent == 4096
    assert water.polygons
    assert all(ring[0] == ring[-1] for polygon in water.polygons for ring in polygon)
    # A tile with no water layer is all land.
    assert openfreemap.water(b"", z, x, y).polygons == ()
    with pytest.raises(ProviderError):
        openfreemap.water(b"\x1a\xff", z, x, y)
    assert openfreemap.only_layer(body, "water") == body
    assert openfreemap.only_layer(body, "roads") == b""


def test_tiles_around() -> None:
    """Tiles cover the distance each way around a point."""
    found = openfreemap.tiles_around(*RIVER_POINT, REACH_KM)
    assert {z for z, _, _ in found} == {openfreemap.ZOOM}
    assert len(found) == 36
    assert openfreemap.tiles_around(0, 0, 1, 12) == {
        (12, 2047, 2047),
        (12, 2047, 2048),
        (12, 2048, 2047),
        (12, 2048, 2048),
    }


def tile_requests(aioclient_mock: AiohttpClientMocker) -> int:
    """Return how many map tiles have been fetched."""
    return sum(
        bool(TILE_URL.match(str(url))) for _, url, _, _ in aioclient_mock.mock_calls
    )


async def test_measured_once_and_kept(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A pin is measured once; pins measured together share their tiles."""
    freezer.move_to(RECORDED)
    mock_tiles(aioclient_mock)
    shorelines = Shorelines(hass)
    assert await shorelines.async_measure_pins([HARBOR_POINT, RIVER_POINT])
    # 36 tiles each, most of them the same ones.
    assert tile_requests(aioclient_mock) < 72
    harbor = shorelines.get(*HARBOR_POINT)
    assert harbor is not None
    assert harbor.on_water
    assert harbor.measured == RECORDED

    fetched = tile_requests(aioclient_mock)
    assert not await shorelines.async_measure_pins([HARBOR_POINT, RIVER_POINT])
    assert await shorelines.async_measure(*HARBOR_POINT) is harbor
    assert tile_requests(aioclient_mock) == fetched

    async_fire_time_changed(hass, RECORDED + timedelta(seconds=5))
    await hass.async_block_till_done()
    saved = hass_storage[STORAGE_KEY]["data"]["pins"]
    assert saved[Shorelines.key(*HARBOR_POINT)]["on_water"] is True

    # Another start reads them back.
    again = Shorelines(hass)
    await again.async_load()
    assert again.get(*HARBOR_POINT) == harbor


async def test_failure_is_tried_again_later(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A pin that can't be measured is tried again after six hours."""
    freezer.move_to(RECORDED)
    aioclient_mock.get(openfreemap.TILEJSON_URL, status=503)
    shorelines = Shorelines(hass)
    with pytest.raises(ProviderError):
        await shorelines.async_measure(*RIVER_POINT)
    assert not await shorelines.async_measure_pins([RIVER_POINT])
    assert aioclient_mock.call_count == 2
    freezer.tick(RETRY_AFTER - timedelta(minutes=1))
    assert not await shorelines.async_measure_pins([RIVER_POINT])
    assert aioclient_mock.call_count == 2

    aioclient_mock.clear_requests()
    mock_tiles(aioclient_mock)
    freezer.tick(timedelta(minutes=2))
    assert await shorelines.async_measure_pins([RIVER_POINT])
    assert shorelines.get(*RIVER_POINT) is not None


async def test_unused_pins_are_forgotten(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A pin no spot uses is forgotten after a day."""
    freezer.move_to(RECORDED)
    mock_tiles(aioclient_mock)
    shorelines = Shorelines(hass)
    await shorelines.async_measure_pins([RIVER_POINT])
    await shorelines.async_measure_pins([HARBOR_POINT])
    assert shorelines.get(*RIVER_POINT) is not None
    freezer.move_to(datetime(2026, 11, 4, tzinfo=UTC))
    await shorelines.async_measure_pins([HARBOR_POINT])
    assert shorelines.get(*RIVER_POINT) is None
    assert shorelines.get(*HARBOR_POINT) is not None


async def test_saved_shorelines_used_from_the_start(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a restart, the first results already use the shorelines saved."""
    await set_up(hass, sailcast_entry, freezer)
    assert await hass.config_entries.async_unload(sailcast_entry.entry_id)
    async_fire_time_changed(hass, RECORDED + timedelta(seconds=15))
    await hass.async_block_till_done()
    # A restart starts with nothing in memory, and the tiles can't be fetched.
    hass.data.pop(DATA_SHORELINES)
    sources.clear_requests()
    mock_sources(sources)
    sources.get(TILE_URL, status=503)
    assert await hass.config_entries.async_setup(sailcast_entry.entry_id)
    river = sailcast_entry.runtime_data.results.data.conditions["spot_river"]
    assert {hour.wave_source for hour in river.hours} == {"estimate"}
