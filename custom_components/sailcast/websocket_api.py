"""WebSocket commands for the SailCast panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import SailCastConfigEntry


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the panel's commands."""
    websocket_api.async_register_command(hass, ws_config)


@websocket_api.websocket_command({"type": "sailcast/config"})
@callback
def ws_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send the spots, boats and sailors."""
    entries: list[SailCastConfigEntry] = hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    if not entries:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "SailCast isn't set up"
        )
        return
    connection.send_result(msg["id"], entries[0].runtime_data.profiles.as_dict())
