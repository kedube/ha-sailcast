"""Tests for local accuracy: readings, the nowcast, waves and repair issues.

The test spots read the buoys and airports the readings were recorded at.
The bay's pin is on land, and the river's is in a small marina basin.
"""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN
from custom_components.sailcast.coordinator import SLOW_DOWN_AT
from custom_components.sailcast.providers import ndbc, noaa_coops, open_meteo
from custom_components.sailcast.waves import WaveSource
from custom_components.sailcast.week import readings_now

from .conftest import RECORDED

SPOTS = ("spot_harbor", "spot_bay", "spot_river")


async def test_readings_at_every_spot(
    hass: HomeAssistant, observed: MockConfigEntry
) -> None:
    """Each spot shows wind read now, and the harbor its buoy's waves.

    The river and harbor read San Diego's airport, and the bay North Island.
    """
    data = observed.runtime_data
    winds = {}
    for spot_id in SPOTS:
        spot = data.profiles.spots[spot_id]
        now = readings_now(data.sources.readings(spot), RECORDED)
        winds[spot_id] = now["fields"]["wind"]
    assert {spot: wind["station"] for spot, wind in winds.items()} == {
        "spot_harbor": "KSAN",
        "spot_bay": "KNZY",
        "spot_river": "KSAN",
    }
    assert winds["spot_bay"]["value"] == 10
    harbor = readings_now(
        data.sources.readings(data.profiles.spots["spot_harbor"]), RECORDED
    )
    assert harbor["fields"]["wave_height"] == {
        "value": 1.4,
        "time": "2026-11-02T22:26:00+00:00",
        "kind": "buoy",
        "station": "46258",
    }
    assert [source["kind"] for source in harbor["sources"]] == ["buoy", "airport"]


async def test_river_waves_come_from_the_estimate(
    hass: HomeAssistant, observed: MockConfigEntry
) -> None:
    """The river's waves are estimated from the wind and its short fetch."""
    conditions = observed.runtime_data.results.data.conditions
    river = conditions["spot_river"]
    assert river.shoreline is not None
    assert river.shoreline.on_water
    assert {hour.wave_source for hour in river.hours} == {WaveSource.ESTIMATE}
    assert all(hour.wave_height is not None for hour in river.hours)
    assert max(hour.wave_height or 0 for hour in river.hours) < 0.3
    # The bay's pin is on land, so its model waves stand.
    bay = conditions["spot_bay"]
    assert bay.shoreline is not None
    assert not bay.shoreline.on_water
    assert {hour.wave_source for hour in bay.hours} == {WaveSource.MODEL}


async def test_readings_nudge_the_next_hours(
    hass: HomeAssistant, observed: MockConfigEntry
) -> None:
    """KSAN read 8 kt where the models had 6.1, so the river's wind goes up."""
    conditions = observed.runtime_data.results.data.conditions
    river = conditions["spot_river"]
    nudged = {item.field: item for item in river.adjustments}
    assert nudged["wind"].station == "KSAN"
    assert nudged["wind"].difference == pytest.approx(1.9, abs=0.01)
    assert nudged["wind_direction"].difference == pytest.approx(-6.3, abs=0.1)
    now = river.index_at(RECORDED)
    assert now is not None
    assert "wind" in river.hours[now].adjusted
    assert "wind" not in river.hours[now + 7].adjusted
    # The harbor's buoy read 1.4 m where the model had 1.47.
    harbor = {item.field: item for item in conditions["spot_harbor"].adjustments}
    assert harbor["wave_height"].difference == pytest.approx(-0.071, abs=0.002)
    assert harbor["water_temperature"].difference == pytest.approx(0.3, abs=0.01)


async def test_readings_are_fetched_on_their_own_schedules(
    hass: HomeAssistant,
    observed: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Buoys every 20 minutes, airports every 30, and their forecast hourly."""

    def calls(url: str) -> int:
        return sum(
            str(called).startswith(url) for _, called, _, _ in sources.mock_calls
        )

    buoys = ndbc.REALTIME_URL.partition("{")[0]
    assert calls(buoys) == 2
    budget = observed.runtime_data.budget
    assert budget.today == pytest.approx(
        open_meteo.forecast_calls(3)
        + open_meteo.marine_calls(2)
        + open_meteo.spread_calls(3)
        + open_meteo.nearby_calls(4)
        + open_meteo.buoy_calls(2)
    )
    for minutes, buoy_calls in ((10, 2), (20, 4), (30, 4), (40, 6)):
        freezer.move_to(RECORDED + timedelta(minutes=minutes, seconds=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert calls(buoys) == buoy_calls, minutes
    assert calls("https://aviationweather.gov/api/data/metar") == 2


async def test_stations_forecast_from_their_own_cells(
    hass: HomeAssistant, observed: MockConfigEntry, sources: AiohttpClientMocker
) -> None:
    """The forecast at the buoys comes from the sea, and at the airports from land."""
    requests = [
        (url.query["latitude"], url.query["cell_selection"])
        for _, url, _, _ in sources.mock_calls
        if str(url).startswith(open_meteo.FORECAST_URL)
        and url.query["hourly"] == ",".join(open_meteo.NEARBY_VARIABLES)
    ]
    assert requests == [("32.7490,32.7140", "sea"), ("32.7364,32.6922", "land")]


async def test_pin_on_land(hass: HomeAssistant, observed: MockConfigEntry) -> None:
    """The bay's pin is on land, which is a repair issue until it moves."""
    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, "pin_on_land_spot_bay")
    assert issue is not None
    assert issue.translation_key == "pin_on_land"
    assert issue.translation_placeholders == {"spot": "Bay"}
    assert registry.async_get_issue(DOMAIN, "pin_on_land_spot_river") is None

    bay = observed.subentries["spot_bay"]
    hass.config_entries.async_update_subentry(
        observed, bay, data={**bay.data, "latitude": 32.715, "longitude": -117.18}
    )
    # The reload measures the moved pin in the background.
    await hass.async_block_till_done(wait_background_tasks=True)
    async_fire_time_changed(hass, RECORDED + timedelta(seconds=5))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert registry.async_get_issue(DOMAIN, "pin_on_land_spot_bay") is None


async def test_quiet_buoy(
    hass: HomeAssistant, observed: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """A buoy with nothing newer than 12 hours is a repair issue."""
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "quiet_buoy_46258") is None
    later = RECORDED + timedelta(hours=12, minutes=30)
    freezer.move_to(later)
    async_fire_time_changed(hass, later)
    await hass.async_block_till_done()
    issue = registry.async_get_issue(DOMAIN, "quiet_buoy_46258")
    assert issue is not None
    assert issue.translation_placeholders == {
        "station": "46258 (Mission Bay West, CA (220))",
        "spots": "Harbor",
    }
    # The airports report hourly in real life, but these recorded reports
    # are as old.
    assert registry.async_get_issue(DOMAIN, "quiet_airport_KSAN") is not None


async def test_failing_tide_station(
    hass: HomeAssistant,
    observed: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A tide station that fails for a day is a repair issue."""
    predictions = observed.runtime_data.sources.predictions
    sources.clear_requests()
    sources.get(noaa_coops.DATA_URL, status=500)
    tomorrow = RECORDED + timedelta(days=1)
    freezer.move_to(tomorrow)
    await predictions.async_refresh()
    assert "tide:9410196" in predictions.failing
    freezer.move_to(tomorrow + timedelta(days=1, minutes=1))
    await predictions.async_refresh()
    observed.runtime_data.results.async_update_listeners()
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "failing_tide_9410196")
    assert issue is not None
    assert issue.translation_placeholders == {
        "station": "9410196",
        "spots": "River",
        "provider": "NOAA",
    }


async def test_budget_low(hass: HomeAssistant, observed: MockConfigEntry) -> None:
    """Near Open-Meteo's daily limit, there's an issue until the count resets."""
    data = observed.runtime_data
    data.budget.add(SLOW_DOWN_AT)
    data.results.async_update_listeners()
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "budget_low")
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["calls"].startswith("8\u202f")


async def test_quiet_sensor(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Your own sensor's readings come first, and a quiet one is an issue."""
    river = sailcast_entry.subentries["spot_river"]
    hass.config_entries.async_update_subentry(
        sailcast_entry,
        river,
        data={**river.data, "sensors": {"wind": "sensor.dock_wind"}},
    )
    freezer.move_to(RECORDED - timedelta(minutes=5))
    hass.states.async_set("sensor.dock_wind", "12", {"unit_of_measurement": "kn"})
    freezer.move_to(RECORDED)
    assert await hass.config_entries.async_setup(sailcast_entry.entry_id)
    await hass.async_block_till_done()
    data = sailcast_entry.runtime_data
    river_now = data.results.data.conditions["spot_river"]
    assert {item.field: item.kind for item in river_now.adjustments} == {
        "wind": "sensors"
    }
    later = RECORDED + timedelta(hours=13)
    freezer.move_to(later)
    async_fire_time_changed(hass, later)
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "quiet_sensor_sensor.dock_wind")
    assert issue is not None
    assert issue.translation_placeholders == {
        "sensor": "sensor.dock_wind",
        "spots": "River",
    }


async def test_issues_go_with_the_entry(
    hass: HomeAssistant, observed: MockConfigEntry
) -> None:
    """Removing SailCast clears its repair issues."""
    assert await hass.config_entries.async_remove(observed.entry_id)
    await hass.async_block_till_done()
    assert not [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    ]
