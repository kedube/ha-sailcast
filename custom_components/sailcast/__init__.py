"""SailCast: sailing forecasts, safety ratings and sailing windows."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SIGNAL_UPDATED
from .coordinator import SailCastConfigEntry, SailCastData
from .panel import async_register_panel, async_remove_panel
from .profiles import Profiles
from .services import async_register_services
from .storage import DATA_STORE, SailCastStore
from .websocket_api import async_register_commands

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Load saved preferences and planned sails, and register the commands."""
    store = SailCastStore(hass)
    await store.async_load()
    hass.data[DATA_STORE] = store
    async_register_commands(hass)
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SailCastConfigEntry) -> bool:
    """Start fetching, rate every spot, and add the entities and panel.

    A source that's down doesn't stop setup; its entities show as unavailable
    until it's back.
    """
    data = SailCastData.create(
        hass, entry, Profiles.from_entry(entry), hass.data[DATA_STORE]
    )
    for source in data.sources.all:
        await source.async_refresh()
    await data.results.async_refresh()
    for unsubscribe in data.results.async_follow_sources():
        entry.async_on_unload(unsubscribe)
    entry.async_on_unload(
        async_track_utc_time_change(
            hass, data.results.async_new_hour, minute=0, second=5
        )
    )
    entry.runtime_data = data

    @callback
    def _async_results_changed() -> None:
        """Tell open panels, and check planned sails against the new results."""
        async_dispatcher_send(hass, SIGNAL_UPDATED)
        entry.async_create_background_task(
            hass, data.planner.async_sync(), "sailcast planned sails"
        )

    entry.async_on_unload(data.results.async_add_listener(_async_results_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_panel(hass)

    @callback
    def _async_started(_: HomeAssistant) -> None:
        _async_results_changed()

    # Calendars may still be loading while Home Assistant starts.
    entry.async_on_unload(async_at_started(hass, _async_started))
    # Adding, editing or removing a spot, boat or sailor updates the entry.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SailCastConfigEntry) -> bool:
    """Remove the entities, and the panel if SailCast is being turned off.

    A reload after a settings change keeps the panel, so it stays open.
    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.disabled_by is not None:
        async_remove_panel(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SailCastConfigEntry) -> None:
    """Remove the panel when SailCast is deleted."""
    async_remove_panel(hass)


async def _async_update_listener(
    hass: HomeAssistant, entry: SailCastConfigEntry
) -> None:
    """Reload, so everything uses the changed profiles."""
    hass.config_entries.async_schedule_reload(entry.entry_id)
