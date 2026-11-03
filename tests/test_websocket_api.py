"""Tests for the panel's WebSocket commands."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.websocket_api import ERR_NOT_FOUND
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.websocket_api import ws_config


async def test_config(
    hass: HomeAssistant, full_entry: MockConfigEntry, sources: AiohttpClientMocker
) -> None:
    """The panel gets every spot, boat and sailor."""
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    connection = MagicMock()

    ws_config(hass, connection, {"id": 7, "type": "sailcast/config"})

    connection.send_result.assert_called_once()
    msg_id, result = connection.send_result.call_args.args
    assert msg_id == 7
    assert [spot["name"] for spot in result["spots"]] == ["Harbor"]
    assert [boat["name"] for boat in result["boats"]] == ["Cruiser", "Keelboat"]
    assert [sailor["name"] for sailor in result["sailors"]] == ["Alex"]


async def test_config_not_set_up(hass: HomeAssistant) -> None:
    """Without a loaded entry, the panel gets an error."""
    connection = MagicMock()

    ws_config(hass, connection, {"id": 8, "type": "sailcast/config"})

    connection.send_error.assert_called_once_with(
        8, ERR_NOT_FOUND, "SailCast isn't set up"
    )
