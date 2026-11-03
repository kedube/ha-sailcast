"""Shared fixtures for the SailCast tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.sailcast.const import (
    DOMAIN,
    NAME,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)
from custom_components.sailcast.providers import noaa_coops, nws, open_meteo

FIXTURES = Path(__file__).parent / "fixtures"
# When the fixtures were recorded: 2:36 PM in San Diego.
RECORDED = datetime(2026, 11, 2, 22, 36, tzinfo=UTC)

# Made-up spots in San Diego, near the test instance's home and far from
# anywhere the maintainer sails. The fixtures were recorded for them.
HARBOR_POINT = (32.75, -117.27)
BAY_POINT = (32.68, -117.17)
RIVER_POINT = (32.76, -117.24)
POINTS = (HARBOR_POINT, BAY_POINT, RIVER_POINT)


def fixture(name: str) -> Any:
    """Return a recorded response."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _spot(
    key: str,
    point: tuple[float, float],
    water_type: str,
    **data: Any,
) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={
            "latitude": point[0],
            "longitude": point[1],
            "radius": 10_000.0,
            "water_type": water_type,
            "offshore": [],
            "exposed": [],
            "tide_station": None,
            "current_station": None,
            "marine_zone": None,
            **data,
        },
        subentry_id=f"spot_{key}",
        subentry_type=SUBENTRY_SPOT,
        title=key.title(),
        unique_id=None,
    )


SPOT = HARBOR = _spot(
    "harbor",
    HARBOR_POINT,
    "open_coast",
    offshore=["ne", "e", "se"],
    exposed=["sw", "w", "nw"],
    tide_station="9410170",
    marine_zone="PZZ740",
)
BAY = _spot(
    "bay",
    BAY_POINT,
    "bay",
    offshore=["ne", "e"],
    exposed=["s", "sw"],
    tide_station="9410166",
    current_station="PCT0056_1",
    marine_zone="PZZ740",
)
RIVER = _spot(
    "river",
    RIVER_POINT,
    "river",
    exposed=["w"],
    tide_station="9410196",
    marine_zone="PZZ740",
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
BEGINNER = ConfigSubentryData(
    data={
        "skill": "beginner",
        "boats": ["boat_keelboat"],
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "start": None,
        "end": None,
    },
    subentry_id="sailor_sam",
    subentry_type=SUBENTRY_SAILOR,
    title="Sam",
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


@pytest.fixture
def sailcast_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an entry with the three test spots, both boats and two sailors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[HARBOR, BAY, RIVER, KEELBOAT, CRUISER, SAILOR, BEGINNER],
    )
    entry.add_to_hass(hass)
    return entry


def by_point(name: str, points: tuple[tuple[float, float], ...]) -> Any:
    """Answer an Open-Meteo request with the recorded place for each point.

    One place comes back on its own, as Open-Meteo sends it.
    """
    places = fixture(name)

    async def respond(method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        lats = [float(value) for value in url.query["latitude"].split(",")]
        lons = [float(value) for value in url.query["longitude"].split(",")]
        chosen = [
            places[points.index((lat, lon))]
            for lat, lon in zip(lats, lons, strict=True)
        ]
        return AiohttpClientMockResponse(
            method, url, json=chosen if len(chosen) > 1 else chosen[0]
        )

    return respond


def mock_sources(
    aioclient_mock: AiohttpClientMocker, *, predictions: bool = True
) -> None:
    """Answer every provider request with the recorded responses.

    Without predictions, tide and current requests are left unanswered.
    """
    aioclient_mock.get(
        open_meteo.FORECAST_URL, side_effect=by_point("open_meteo_forecast", POINTS)
    )
    aioclient_mock.get(
        open_meteo.MARINE_URL, side_effect=by_point("open_meteo_marine", POINTS[:2])
    )
    aioclient_mock.get(f"{nws.API}/alerts/active", json=fixture("nws_alerts"))
    if not predictions:
        return
    for station in ("9410166", "9410170", "9410196"):
        for interval in ("hilo", "h"):
            aioclient_mock.get(
                noaa_coops.DATA_URL,
                params={"station": station, "interval": interval},
                json=fixture(f"noaa_tides_{station}_{interval}"),
            )
    aioclient_mock.get(
        noaa_coops.DATA_URL,
        params={"station": "PCT0056", "product": "currents_predictions"},
        json=fixture("noaa_currents_PCT0056_1"),
    )


@pytest.fixture
def sources(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Answer every provider request with the recorded responses."""
    mock_sources(aioclient_mock)
    return aioclient_mock


@pytest.fixture
async def loaded(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Return the test entry, set up at the time the fixtures were recorded."""
    freezer.move_to(RECORDED)
    assert await hass.config_entries.async_setup(sailcast_entry.entry_id)
    await hass.async_block_till_done()
    return sailcast_entry


def mock_suggestions(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer the station and zone lookups for the harbor and bay pins."""
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/tidepredstations.json",
        json=fixture("noaa_tide_stations"),
    )
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/stations.json",
        json=fixture("noaa_current_stations"),
    )
    aioclient_mock.get(
        f"{nws.API}/zones",
        params={"point": f"{HARBOR_POINT[0]:.4f},{HARBOR_POINT[1]:.4f}"},
        json=fixture("nws_zones_harbor"),
    )
    aioclient_mock.get(
        f"{nws.API}/zones",
        params={"point": f"{BAY_POINT[0]:.4f},{BAY_POINT[1]:.4f}"},
        json=fixture("nws_zones_bay"),
    )
    aioclient_mock.get(
        f"{nws.API}/points/{BAY_POINT[0]:.4f},{BAY_POINT[1]:.4f}",
        json=fixture("nws_points_bay"),
    )
    aioclient_mock.get(f"{nws.API}/zones", json=fixture("nws_zones_coastal"))
    for zone in ("PZZ740", "PZZ745"):
        aioclient_mock.get(
            f"{nws.API}/zones/coastal/{zone}", json=fixture(f"nws_zone_{zone}")
        )


@pytest.fixture
def suggestions(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Answer the station and zone lookups for the test pins."""
    mock_suggestions(aioclient_mock)
    return aioclient_mock


@pytest.fixture
async def family(hass: HomeAssistant, tmp_path: Path) -> str:
    """Set up a Local Calendar named Family and return its entity ID.

    It keeps its events in a file in the config folder, so that's a new one.
    """
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()
    entry = MockConfigEntry(domain="local_calendar", data={"calendar_name": "Family"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return "calendar.family"
