"""Tests for SailCast's entities, devices and how they follow the profiles."""

from __future__ import annotations

from datetime import UTC, datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN
from custom_components.sailcast.providers import open_meteo, openfreemap


async def test_devices_and_subentries(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Each spot and sailor is a device, tied to its subentry."""
    harbor = device_registry.async_get_device_by_identifier(
        (DOMAIN, "spot_harbor"), loaded.entry_id
    )
    alex = device_registry.async_get_device_by_identifier(
        (DOMAIN, "sailor_alex"), loaded.entry_id
    )
    assert harbor
    assert harbor.name == "Harbor"
    assert alex
    assert alex.name == "Alex"
    warning = entity_registry.async_get("binary_sensor.harbor_marine_warning")
    rating = entity_registry.async_get("sensor.alex_harbor_rating")
    assert warning
    assert warning.config_subentry_id == "spot_harbor"
    assert rating
    assert rating.device_id == alex.id
    assert rating.config_subentry_id == "sailor_alex"


async def test_conditions_are_off_by_default(
    hass: HomeAssistant, loaded: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Spot conditions start disabled; rivers get waves but no water temperature.

    Sheltered water's waves are worked out from its fetch, and water
    temperature comes from the ocean model, for open water only.
    """
    for entity_id in (
        "sensor.harbor_wind",
        "sensor.harbor_wave_height",
        "sensor.river_wave_height",
    ):
        entry = entity_registry.async_get(entity_id)
        assert entry
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entity_registry.async_get("sensor.river_water_temperature") is None
    assert entity_registry.async_get("sensor.river_next_high_tide")


async def test_conditions_when_enabled(
    hass: HomeAssistant, loaded: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Enabled condition sensors show this hour's values and the next tides."""
    for key in ("wind", "wave_height", "next_high_tide"):
        entity_registry.async_update_entity(f"sensor.harbor_{key}", disabled_by=None)
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()

    wind = hass.states.get("sensor.harbor_wind")
    assert float(wind.state) == 6.1  # the middle of 5.4, 7.7 and 6.1 kt
    assert wind.attributes["unit_of_measurement"] == "kn"
    assert float(hass.states.get("sensor.harbor_wave_height").state) == 1.38
    tide = hass.states.get("sensor.harbor_next_high_tide")
    assert datetime.fromisoformat(tide.state) > datetime(2026, 11, 2, 22, tzinfo=UTC)
    assert tide.attributes["height"] > 0


async def test_rating_attributes(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """The rating names its boat and reasons, and when it changes next."""
    state = hass.states.get("sensor.alex_harbor_rating")
    assert state.attributes["options"] == [
        "good",
        "caution",
        "not_recommended",
        "dangerous",
    ]
    assert state.attributes["boat"] == "Keelboat"
    assert state.attributes["reasons"] == ["waves"]
    assert state.attributes["next_rating"] == "caution"
    assert datetime.fromisoformat(state.attributes["next_change"]) > datetime(
        2026, 11, 2, 22, tzinfo=UTC
    )


async def test_no_score_at_night(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Scores are for daylight; ratings carry on through the night."""
    freezer.move_to(datetime(2026, 11, 3, 6, tzinfo=UTC))  # 10 PM in San Diego
    await loaded.runtime_data.results.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sam_river_score").state == STATE_UNKNOWN
    assert hass.states.get("sensor.sam_river_rating").state in (
        "good",
        "caution",
        "not_recommended",
        "dangerous",
    )
    assert hass.states.get("binary_sensor.sam_river_good_to_sail").state == "off"


async def test_removed_spot_takes_its_entities(
    hass: HomeAssistant, loaded: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Removing a spot removes its sensors from every sailor."""
    assert entity_registry.async_get("sensor.alex_river_rating")
    hass.config_entries.async_remove_subentry(loaded, "spot_river")
    await hass.async_block_till_done()
    assert entity_registry.async_get("sensor.alex_river_rating") is None
    assert entity_registry.async_get("binary_sensor.sam_river_good_to_sail") is None
    assert entity_registry.async_get("sensor.alex_harbor_rating")


async def test_unavailable_without_a_forecast(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """If the forecast can't be fetched, SailCast still loads, unavailable."""
    freezer.move_to(datetime(2026, 11, 2, 22, 36, tzinfo=UTC))
    aioclient_mock.get(open_meteo.FORECAST_URL, status=503)
    aioclient_mock.get(open_meteo.MARINE_URL, status=503)
    aioclient_mock.get(open_meteo.ENSEMBLE_URL, status=503)
    aioclient_mock.get(openfreemap.TILEJSON_URL, status=503)
    aioclient_mock.get(
        "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter", status=503
    )
    aioclient_mock.get("https://api.weather.gov/alerts/active", status=503)
    assert await hass.config_entries.async_setup(sailcast_entry.entry_id)
    await hass.async_block_till_done()
    for entity_id in (
        "sensor.alex_harbor_rating",
        "sensor.alex_next_sailing_window",
        "binary_sensor.harbor_marine_warning",
        "calendar.alex_sailing",
    ):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE, entity_id
