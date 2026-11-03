"""Tests for spots outside the US: the Solent, the Wadden Sea and Lake Garda."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN, NAME
from custom_components.sailcast.limits import Level, SizeClass
from custom_components.sailcast.providers import worldtides
from custom_components.sailcast.regions import STORAGE_KEY as REGIONS_KEY

from .conftest import (
    BEGINNER,
    KEELBOAT,
    SOLENT,
    VLISSINGEN_POINT,
    WADDEN_POINT,
    WORLD_RECORDED,
    _spot,
    mock_world,
    set_up_abroad,
)


async def test_complete_weeks_abroad(
    hass: HomeAssistant,
    world_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A spot in the UK, the Netherlands and a lake each produce a complete week."""
    mock_world(aioclient_mock)
    await set_up_abroad(hass, world_entry, freezer)
    data = world_entry.runtime_data
    results = data.results.data
    zone = dt_util.get_default_time_zone()
    for spot in ("spot_solent", "spot_wadden", "spot_garda"):
        conditions = results.conditions[spot]
        days = {day.date for day in conditions.days}
        assert len(days) == 7
        # Every day has its daylight hours, with wind, gusts and air.
        lit = [hour for hour in conditions.hours if hour.daylight]
        assert {hour.start.astimezone(zone).date() for hour in lit} == days
        assert all(hour.temperature is not None for hour in lit)
        outlook = results.outlook("sailor_sam", spot)
        assert outlook is not None
        assert all(
            len(ratings) == len(conditions.hours) for ratings in outlook.sizes.values()
        )
    # The Solent's tides come from WorldTides, above chart datum, every day.
    solent = results.conditions["spot_solent"]
    assert solent.tides is not None
    assert solent.tides.datum == "CD"
    assert {event.time.astimezone(zone).date() for event in solent.tide_events} >= {
        day.date for day in solent.days
    }
    # The Wadden Sea's come from Rijkswaterstaat at Harlingen, above NAP.
    wadden = results.conditions["spot_wadden"]
    assert wadden.tides is not None
    assert wadden.tides.datum == "NAP"
    assert {event.time.astimezone(zone).date() for event in wadden.tide_events} >= {
        day.date for day in wadden.days
    }
    assert all(hour.tide_height is not None for hour in wadden.hours)
    # The lake has no tide, and its waves are worked out from its fetch.
    garda = results.conditions["spot_garda"]
    assert garda.tides is None
    assert {hour.wave_source for hour in garda.hours} == {"estimate"}
    # Every spot's warnings come from MeteoAlarm, from the right regions.
    alerts = data.sources.alerts
    assert alerts.last_update_success
    places = {key.partition(":")[0]: place for key, place in alerts.places.items()}
    assert places
    assert {place.countries for place in alerts.places.values()} == {
        ("UK",),
        ("NL",),
        ("IT",),
    }
    assert {tuple(sorted(place.regions)) for place in alerts.places.values()} >= {
        ("NL806", "NL809"),
        ("IT002", "IT003", "IT006"),
    }
    assert data.sources.predictions.last_update_success


async def test_meteoalarm_warning_rates_the_hours(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A yellow wind warning holds small keelboats at not recommended, with its text."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[
            _spot("flushing", VLISSINGEN_POINT, "open_coast", marine_zone="meteoalarm"),
            KEELBOAT,
            BEGINNER,
        ],
    )
    entry.add_to_hass(hass)
    mock_world(aioclient_mock, {VLISSINGEN_POINT: WADDEN_POINT})
    await set_up_abroad(hass, entry, freezer)
    conditions = entry.runtime_data.results.data.conditions["spot_flushing"]
    (alert,) = {alert.event: alert for alert in conditions.alerts}.values()
    assert alert.event == "Yellow wind warning"
    assert alert.issuer == "KNMI Royal Netherlands Meteorological Institute"
    assert alert.details is not None
    assert "NE-6" in alert.details
    outlook = entry.runtime_data.results.data.outlook("sailor_sam", "spot_flushing")
    assert outlook is not None
    during = [
        index
        for index, hour in enumerate(conditions.hours)
        if alert.start <= hour.start < alert.end
    ]
    assert during
    assert all(
        outlook.sizes[SizeClass.SMALL_KEELBOAT][index].level >= Level.NOT_RECOMMENDED
        for index in during
    )


async def test_worldtides_key_problems(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A missing or refused WorldTides key is a repair issue, asked about once."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[SOLENT, KEELBOAT, BEGINNER],
    )
    entry.add_to_hass(hass)
    mock_world(aioclient_mock)
    await set_up_abroad(hass, entry, freezer)
    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, "worldtides_key_missing")
    assert issue is not None
    assert issue.translation_placeholders == {"spots": "Solent"}
    assert not any(worldtides.API in str(call[1]) for call in aioclient_mock.mock_calls)

    hass.config_entries.async_update_entry(entry, options={"worldtides_key": "wrong"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert registry.async_get_issue(DOMAIN, "worldtides_key_missing") is None
    issue = registry.async_get_issue(DOMAIN, "worldtides_key_rejected")
    assert issue is not None
    assert issue.translation_placeholders == {
        "error": "API key is invalid",
        "spots": "Solent",
    }
    asked = sum(worldtides.API in str(call[1]) for call in aioclient_mock.mock_calls)
    assert asked == 1
    # Asking again with the same key wouldn't help.
    freezer.tick(timedelta(hours=1, minutes=1))
    await entry.runtime_data.sources.predictions.async_refresh()
    assert (
        sum(worldtides.API in str(call[1]) for call in aioclient_mock.mock_calls)
        == asked
    )
    # The key never shows in what's logged or in diagnostics' errors.
    error = entry.runtime_data.sources.predictions.last_exception
    assert error is None or "wrong" not in str(error)


async def test_regions_downloaded_once(
    hass: HomeAssistant,
    world_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """MeteoAlarm's regions are downloaded once and kept on disk."""
    mock_world(aioclient_mock)
    await set_up_abroad(hass, world_entry, freezer)
    downloads = [
        call
        for call in aioclient_mock.mock_calls
        if "MeteoAlarm_Geocodes" in str(call[1])
    ]
    assert len(downloads) == 1
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.tick(timedelta(seconds=5))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert REGIONS_KEY in hass_storage
    assert WORLD_RECORDED
