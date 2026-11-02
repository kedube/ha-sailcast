"""Shared fixtures for the SailCast tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sailcast.const import (
    DOMAIN,
    NAME,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)

# Made-up profiles. The spot is in San Diego Bay, near the test instance's
# home, and far from any spot the maintainer sails.
SPOT = ConfigSubentryData(
    data={
        "latitude": 32.7,
        "longitude": -117.2,
        "radius": 10_000.0,
        "water_type": "bay",
        "offshore": ["e"],
        "exposed": ["sw", "w"],
    },
    subentry_id="spot_harbor",
    subentry_type=SUBENTRY_SPOT,
    title="Harbor",
    unique_id=None,
)
KEELBOAT = ConfigSubentryData(
    data={"size_class": "small_keelboat", "length": 6.096},
    subentry_id="boat_keelboat",
    subentry_type=SUBENTRY_BOAT,
    title="Keelboat",
    unique_id=None,
)
CRUISER = ConfigSubentryData(
    data={"size_class": "cruiser", "length": 10.363},
    subentry_id="boat_cruiser",
    subentry_type=SUBENTRY_BOAT,
    title="Cruiser",
    unique_id=None,
)
SAILOR = ConfigSubentryData(
    data={
        "skill": "intermediate",
        "boats": ["boat_keelboat", "boat_cruiser"],
        "days": ["sat", "sun"],
        "start": "09:00:00",
        "end": None,
    },
    subentry_id="sailor_alex",
    subentry_type=SUBENTRY_SAILOR,
    title="Alex",
    unique_id=None,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load SailCast from custom_components."""


@pytest.fixture(autouse=True)
def mock_http(hass: HomeAssistant) -> MagicMock:
    """Stand in for the web server and the frontend.

    The frontend's package isn't installed for tests. The panel only needs
    somewhere to register its module.
    """
    for component in ("http", "frontend", "panel_custom"):
        hass.config.components.add(component)
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    return hass.http


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a SailCast entry with no profiles, added but not set up."""
    entry = MockConfigEntry(domain=DOMAIN, title=NAME, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def full_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a SailCast entry with a spot, two boats and a sailor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[SPOT, KEELBOAT, CRUISER, SAILOR],
    )
    entry.add_to_hass(hass)
    return entry
