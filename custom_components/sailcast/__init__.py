"""SailCast: sailing forecasts, safety ratings and sailing windows."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .panel import async_register_panel, async_remove_panel
from .profiles import Profiles, SailCastConfigEntry
from .websocket_api import async_register_commands

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the panel's WebSocket commands."""
    async_register_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SailCastConfigEntry) -> bool:
    """Read the profiles and add the panel to the sidebar."""
    entry.runtime_data = Profiles.from_entry(entry)
    await async_register_panel(hass)
    # Adding, editing or removing a spot, boat or sailor updates the entry.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SailCastConfigEntry) -> bool:
    """Remove the panel."""
    async_remove_panel(hass)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: SailCastConfigEntry
) -> None:
    """Reload, so everything uses the changed profiles."""
    hass.config_entries.async_schedule_reload(entry.entry_id)
