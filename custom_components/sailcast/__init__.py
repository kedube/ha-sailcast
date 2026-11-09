"""SailCast: sailing forecasts, safety ratings and sailing windows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_utc_time_change,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .assist import NAME as ASSIST_NAME, SailCastAPI
from .briefing import DATA_BRIEFINGS, Briefings, async_remove_old
from .const import DOMAIN, SIGNAL_UPDATED
from .coordinator import SailCastConfigEntry, SailCastData, async_remove_predictions
from .panel import async_register_panel, async_remove_panel
from .profiles import Profiles
from .regions import DATA_REGIONS, Regions
from .repairs import async_clear_issues, async_update_issues
from .services import async_register_services
from .shoreline import DATA_SHORELINES, Shorelines
from .storage import DATA_STORE, SailCastStore
from .websocket_api import async_register_commands

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]
# Pins whose shoreline couldn't be measured are tried again this often.
SHORELINE_CHECK: Final = timedelta(hours=1)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Load saved preferences and planned sails, and register the commands.

    Ask SailCast's tools are offered to conversation agents from here, so a
    reload doesn't take them away from an agent that uses them.
    """
    store = SailCastStore(hass)
    await store.async_load()
    hass.data[DATA_STORE] = store
    async_register_commands(hass)
    async_register_services(hass)
    llm.async_register_api(hass, SailCastAPI(hass=hass, id=DOMAIN, name=ASSIST_NAME))
    # The day summaries before 1.00 were replaced by the briefing.
    hass.async_create_background_task(async_remove_old(hass), "sailcast old summaries")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SailCastConfigEntry) -> bool:
    """Start fetching, rate every spot, and add the entities and panel.

    A source that's down doesn't stop setup; its entities show as unavailable
    until it's back.
    """
    # Adding, editing or removing a spot, boat or sailor updates the entry.
    # Listening before the profiles are read means a change made while setup
    # fetches still reloads SailCast once setup is done.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    data = SailCastData.create(
        hass, entry, Profiles.from_entry(entry), hass.data[DATA_STORE]
    )
    for source in data.sources.all:
        await source.async_refresh()
    # Shorelines measured before are read first, so the first results have
    # them; only new pins are measured in the background.
    await data.sources.shorelines.async_load()
    await data.briefings.async_load()
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
        """Tell open panels, check planned sails, and update repair issues."""
        async_dispatcher_send(hass, SIGNAL_UPDATED)
        entry.async_create_background_task(
            hass, data.planner.async_sync(), "sailcast planned sails"
        )
        async_update_issues(hass, data, dt_util.utcnow())

    entry.async_on_unload(data.results.async_add_listener(_async_results_changed))

    async def _async_measure_shorelines(_: datetime | None = None) -> None:
        """Measure new pins' shorelines, and rate again with them."""
        pins = [
            (spot.latitude, spot.longitude) for spot in data.profiles.spots.values()
        ]
        if await data.sources.shorelines.async_measure_pins(pins):
            await data.results.async_request_refresh()

    entry.async_create_background_task(
        hass, _async_measure_shorelines(), "sailcast shorelines"
    )
    entry.async_on_unload(
        async_track_time_interval(hass, _async_measure_shorelines, SHORELINE_CHECK)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_panel(hass)

    @callback
    def _async_started(_: HomeAssistant) -> None:
        _async_results_changed()

    # Calendars may still be loading while Home Assistant starts.
    entry.async_on_unload(async_at_started(hass, _async_started))
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
    """Remove the panel, repair issues and saved data when SailCast is deleted.

    Events SailCast added to calendars stay, since the calendars are yours.
    """
    async_remove_panel(hass)
    async_clear_issues(hass)
    await hass.data[DATA_STORE].async_remove()
    # A new one deletes a file saved before Home Assistant started.
    await (hass.data.pop(DATA_SHORELINES, None) or Shorelines(hass)).async_remove()
    await (hass.data.pop(DATA_BRIEFINGS, None) or Briefings(hass)).async_remove()
    await (hass.data.pop(DATA_REGIONS, None) or Regions(hass)).async_remove()
    await async_remove_predictions(hass)


async def _async_update_listener(
    hass: HomeAssistant, entry: SailCastConfigEntry
) -> None:
    """Reload, so everything uses the changed profiles."""
    hass.config_entries.async_schedule_reload(entry.entry_id)
