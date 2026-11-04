"""Tests for loading SailCast and its panel."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import (
    ConfigEntryDisabler,
    ConfigEntryState,
    ConfigSubentry,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import SUBENTRY_BOAT
from custom_components.sailcast.shoreline import Shorelines
from custom_components.sailcast.storage import DATA_STORE


async def test_panel_added_and_removed(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    mock_http: MagicMock,
    sources: AiohttpClientMocker,
) -> None:
    """Loading adds the panel to the sidebar, and turning SailCast off removes it.

    A reload keeps it, so a settings change doesn't send anyone elsewhere.
    """
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

    assert await hass.config_entries.async_reload(full_entry.entry_id)
    assert hass.data[DATA_PANELS]["sailcast"] is panel

    await hass.config_entries.async_set_disabled_by(
        full_entry.entry_id, ConfigEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert "sailcast" not in hass.data[DATA_PANELS]


async def test_panel_removed_with_entry(
    hass: HomeAssistant, full_entry: MockConfigEntry, sources: AiohttpClientMocker
) -> None:
    """Deleting SailCast removes its panel."""
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()

    await hass.config_entries.async_remove(full_entry.entry_id)
    assert "sailcast" not in hass.data[DATA_PANELS]


async def test_saved_data_removed_with_entry(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    hass_storage: dict[str, Any],
) -> None:
    """Deleting SailCast deletes what it saved, also what was saved before a start."""
    names = ("panel", "predictions", "shoreline", "summaries", "meteoalarm_regions")
    for key in (f"sailcast.{name}" for name in names):
        hass_storage[key] = {"version": 1, "key": key, "data": {}}
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    store = hass.data[DATA_STORE]
    store.set_preferences("user1", {"spot": "spot_harbor"})

    await hass.config_entries.async_remove(full_entry.entry_id)
    await hass.async_block_till_done()
    assert [key for key in hass_storage if key.startswith("sailcast.")] == []
    # Added again, SailCast starts afresh.
    assert store.preferences("user1") == {}


async def test_profile_change_reloads(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    mock_http: MagicMock,
    sources: AiohttpClientMocker,
) -> None:
    """Adding a profile reloads the entry with the new profile."""
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    assert len(full_entry.runtime_data.profiles.boats) == 2

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
    assert len(full_entry.runtime_data.profiles.boats) == 3
    assert "sailcast" in hass.data[DATA_PANELS]
    # The module is served once, however often the entry reloads.
    mock_http.async_register_static_paths.assert_awaited_once()


async def test_change_during_setup(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    mock_http: MagicMock,
    sources: AiohttpClientMocker,
) -> None:
    """A profile added while SailCast sets up still reaches it.

    Setup reads the profiles before it fetches, so it reloads once it's done.
    """
    dinghy = ConfigSubentry(
        data=MappingProxyType({"size_class": "dinghy", "length": 4.2}),
        subentry_type=SUBENTRY_BOAT,
        title="Dinghy",
        unique_id=None,
    )
    load = Shorelines.async_load

    async def add_while_loading(shorelines: Shorelines) -> None:
        if dinghy.subentry_id not in full_entry.subentries:
            hass.config_entries.async_add_subentry(full_entry, dinghy)
        await load(shorelines)

    with patch.object(Shorelines, "async_load", add_while_loading):
        assert await hass.config_entries.async_setup(full_entry.entry_id)
        await hass.async_block_till_done()

    assert full_entry.state is ConfigEntryState.LOADED
    assert dinghy.subentry_id in full_entry.runtime_data.profiles.boats
