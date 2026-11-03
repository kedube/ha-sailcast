"""Tests for fetching on a schedule and working out the results."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN, NAME
from custom_components.sailcast.coordinator import (
    FORECAST_INTERVAL,
    SLOW_FORECAST_INTERVAL,
    STORAGE_KEY,
    Budget,
)
from custom_components.sailcast.providers import noaa_coops, open_meteo
from custom_components.sailcast.timeline import Alert

from .conftest import BAY, KEELBOAT, RECORDED, SAILOR, mock_sources


def noaa_calls(aioclient_mock: AiohttpClientMocker) -> int:
    """Return how many prediction requests were made."""
    return sum(
        1
        for call in aioclient_mock.mock_calls
        if str(call[1]).startswith(noaa_coops.DATA_URL)
    )


async def test_budget(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Open-Meteo calls are counted as Open-Meteo counts them."""
    budget = loaded.runtime_data.budget
    assert budget.today == pytest.approx(
        open_meteo.forecast_calls(3)
        + open_meteo.marine_calls(2)
        + open_meteo.spread_calls(3)
    )


async def test_forecast_slows_near_the_limit(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """Near the daily limit, the forecast refreshes every three hours."""
    forecast = loaded.runtime_data.sources.forecast
    assert forecast.update_interval == FORECAST_INTERVAL
    loaded.runtime_data.budget.calls = 8000
    await forecast.async_refresh()
    assert forecast.update_interval == SLOW_FORECAST_INTERVAL


def test_budget_starts_again_each_day(freezer: FrozenDateTimeFactory) -> None:
    """The count starts again each day, in UTC."""
    freezer.move_to(RECORDED)
    budget = Budget()
    budget.add(10)
    assert budget.today == 10
    freezer.move_to(RECORDED + timedelta(days=1))
    assert budget.today == 0
    budget.add(3)
    assert budget.today == 3


async def test_predictions_are_kept_for_the_day(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    sources: AiohttpClientMocker,
    hass_storage: dict[str, Any],
) -> None:
    """Predictions are fetched once a day; a reload uses the saved ones."""
    assert STORAGE_KEY in hass_storage
    fetched = noaa_calls(sources)
    assert fetched == 7  # highs and lows plus hourly for 3 stations, 1 current
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    assert noaa_calls(sources) == fetched
    assert hass.states.get("sensor.sam_river_rating").state == "good"


async def test_saved_predictions_outlast_an_outage(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """When NOAA is down, yesterday's predictions keep the tides going."""
    freezer.move_to(RECORDED)
    mock_sources(aioclient_mock)
    assert await hass.config_entries.async_setup(sailcast_entry.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(sailcast_entry.entry_id)
    saved = hass_storage[STORAGE_KEY]["data"]
    saved["fetched"] = dict.fromkeys(saved["fetched"], "2026-11-01")

    aioclient_mock.clear_requests()
    mock_sources(aioclient_mock, predictions=False)
    aioclient_mock.get(noaa_coops.DATA_URL, status=503)
    assert await hass.config_entries.async_setup(sailcast_entry.entry_id)
    await hass.async_block_till_done()

    predictions = sailcast_entry.runtime_data.sources.predictions
    assert not predictions.last_update_success
    assert set(predictions.data.tides) == {"9410166", "9410170", "9410196"}
    hours = sailcast_entry.runtime_data.results.data.conditions["spot_harbor"].hours
    assert hours[0].tide_height is not None


async def test_results_follow_the_sources(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """A new warning reaches the entities without waiting for the hour."""
    assert hass.states.get("binary_sensor.harbor_marine_warning").state == "off"
    now = datetime(2026, 11, 2, 22, tzinfo=UTC)
    gale = Alert(
        event="Gale Warning", zone="PZZ740", start=now, end=now + timedelta(hours=6)
    )
    loaded.runtime_data.sources.alerts.async_set_updated_data((gale,))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.harbor_marine_warning").state == "on"
    assert hass.states.get("sensor.alex_harbor_rating").state == "dangerous"


async def test_now_moves_on_each_hour(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """At the top of each hour, the entities move on to the new hour."""
    later = datetime(2026, 11, 3, 1, 0, 5, tzinfo=UTC)  # 5 PM, after sunset
    freezer.move_to(later)
    async_fire_time_changed(hass, later)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sam_river_score").state == "unknown"
    assert hass.states.get("binary_sensor.sam_river_good_to_sail").state == "off"


async def test_no_zone_no_warnings_request(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Spots without a marine zone don't ask for warnings."""
    freezer.move_to(RECORDED)
    mock_sources(aioclient_mock)
    bay = BAY | {"data": BAY["data"] | {"marine_zone": None}}
    entry = MockConfigEntry(
        domain=DOMAIN, title=NAME, data={}, subentries_data=[bay, KEELBOAT, SAILOR]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not any("alerts" in str(call[1]) for call in aioclient_mock.mock_calls)
    assert hass.states.get("binary_sensor.bay_marine_warning") is None
    assert hass.states.get("sensor.alex_bay_rating").state == "not_recommended"
