"""Tests for loading SailCast and its panel."""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast.const import SUBENTRY_BOAT


async def test_panel_added_and_removed(
    hass: HomeAssistant, full_entry: MockConfigEntry, mock_http: MagicMock
) -> None:
    """Loading adds the panel to the sidebar, and unloading removes it."""
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    assert full_entry.state is ConfigEntryState.LOADED

    panel = hass.data[DATA_PANELS]["sailcast"]
    assert panel.sidebar_title == "SailCast"
    assert panel.sidebar_icon == "mdi:sail-boat"
    assert not panel.require_admin
    custom = panel.config["_panel_custom"]
    assert custom["name"] == "sailcast-panel"
    assert custom["module_url"].startswith("/sailcast_static/sailcast-panel.js?v=")
    assert custom["embed_iframe"] is False
    mock_http.async_register_static_paths.assert_awaited_once()

    assert await hass.config_entries.async_unload(full_entry.entry_id)
    assert "sailcast" not in hass.data[DATA_PANELS]


async def test_profile_change_reloads(
    hass: HomeAssistant, full_entry: MockConfigEntry, mock_http: MagicMock
) -> None:
    """Adding a profile reloads the entry with the new profile."""
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    assert len(full_entry.runtime_data.boats) == 2

    hass.config_entries.async_add_subentry(
        full_entry,
        ConfigSubentry(
            data=MappingProxyType({"size_class": "dinghy", "length": 4.2}),
            subentry_type=SUBENTRY_BOAT,
            title="Dinghy",
            unique_id=None,
        ),
    )
    await hass.async_block_till_done()

    assert full_entry.state is ConfigEntryState.LOADED
    assert len(full_entry.runtime_data.boats) == 3
    assert "sailcast" in hass.data[DATA_PANELS]
    # The module is served once, however often the entry reloads.
    mock_http.async_register_static_paths.assert_awaited_once()
