"""Tests for finding and using sources outside the US."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.const import DOMAIN, NAME, SUBENTRY_SPOT
from custom_components.sailcast.providers import (
    chs,
    eccc,
    kartverket,
    metar,
    meteoalarm,
    ndbc,
    noaa_coops,
    nws,
)
from custom_components.sailcast.regions import STORAGE_KEY, Regions
from custom_components.sailcast.sources import async_suggest, suggested

from .conftest import (
    BEGINNER,
    KEELBOAT,
    SOLENT_POINT,
    WADDEN_POINT,
    WORLD_RECORDED,
    _spot,
    fixture,
    mock_world,
    set_up_abroad,
    text_fixture,
)

HALIFAX = (44.63, -63.55)
BERGEN = (60.39, 5.32)


def mock_lookups(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer the US lookups as they answer abroad, and each country's own."""
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/tidepredstations.json", json={"stationList": None}
    )
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/stations.json", json={"stations": []}
    )
    aioclient_mock.get(f"{nws.API}/zones", json={"features": []})
    aioclient_mock.get(
        f"{nws.API}/points/{HALIFAX[0]:.4f},{HALIFAX[1]:.4f}", status=404, json={}
    )
    for point in (SOLENT_POINT, WADDEN_POINT, BERGEN):
        aioclient_mock.get(
            f"{nws.API}/points/{point[0]:.4f},{point[1]:.4f}", status=404, json={}
        )
    aioclient_mock.get(ndbc.STATIONS_URL, text="<stations></stations>")
    aioclient_mock.get(metar.STATIONINFO_URL, json=[])
    aioclient_mock.get(
        f"{chs.API}/stations",
        json=[
            {
                "id": "made-up-halifax",
                "code": "00490",
                "officialName": "Halifax",
                "latitude": 44.6591,
                "longitude": -63.5834,
                "timeSeries": [{"code": "wlp-hilo"}],
            }
        ],
    )
    aioclient_mock.get(eccc.API, json=fixture("eccc_areas_halifax"))
    aioclient_mock.get(kartverket.API, text=text_fixture("kartverket_bergen_tab.xml"))
    mock_world(aioclient_mock)


async def test_dutch_pin(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Dutch pin gets Rijkswaterstaat's stations and MeteoAlarm's warnings."""
    mock_lookups(aioclient_mock)
    found = await async_suggest(hass, *WADDEN_POINT)
    assert not found.failed
    ids = [choice.id for choice in found.tide]
    assert ids[0] == "rws:harlingen.waddenzee"
    assert found.tide[0].distance_km is not None
    assert found.tide[0].distance_km < 3
    # The ocean model's tide is there to pick, but never suggested.
    assert ids[-1] == "model"
    assert "worldtides" not in ids
    assert suggested("tide_station", found.tide) == "rws:harlingen.waddenzee"
    (warnings,) = found.zones
    assert warnings.id == "meteoalarm"
    assert "KNMI" in warnings.name
    assert suggested("marine_zone", found.zones) == "meteoalarm"


async def test_uk_pin_with_a_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """In the UK, WorldTides is suggested when its key is set."""
    mock_lookups(aioclient_mock)
    found = await async_suggest(hass, *SOLENT_POINT, worldtides=True)
    assert [choice.id for choice in found.tide] == ["worldtides", "model"]
    assert suggested("tide_station", found.tide) == "worldtides"
    without = await async_suggest(hass, *SOLENT_POINT)
    assert suggested("tide_station", without.tide) is None
    assert suggested("marine_zone", found.zones) == "meteoalarm"


async def test_canadian_pin(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Canadian pin gets CHS's stations and ECCC's marine area."""
    mock_lookups(aioclient_mock)
    found = await async_suggest(hass, *HALIFAX)
    assert found.tide[0].id == "chs:made-up-halifax"
    assert found.tide[0].code == "00490"
    assert [choice.id for choice in found.zones] == ["eccc:m0000053"]
    assert suggested("marine_zone", found.zones) == "eccc:m0000053"


async def test_norwegian_pin(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """In Norway, Kartverket answers for the pin."""
    mock_lookups(aioclient_mock)
    found = await async_suggest(hass, *BERGEN)
    assert found.tide[0].id == "kartverket"
    assert "Bergen" in found.tide[0].name
    assert found.tide[0].distance_km is None
    assert suggested("tide_station", found.tide) == "kartverket"


async def test_setup_labels_abroad(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The setup dialog labels sources at the pin without a code or distance."""
    mock_lookups(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, title=NAME, data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_SPOT), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Wadden",
            "location": {
                "latitude": WADDEN_POINT[0],
                "longitude": WADDEN_POINT[1],
                "radius": 10_000,
            },
            "water_type": "bay",
        },
    )
    assert result["type"] is FlowResultType.FORM
    tides = {
        option["value"]: option["label"]
        for option in result["data_schema"].schema["tide_station"].config["options"]
    }
    assert tides["rws:harlingen.waddenzee"].startswith("Harlingen, Waddenzee, ")
    assert tides["model"] == "Ocean model at the pin, rough"


async def test_rough_tide(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The ocean model's tide gives a curve, but no times, advice or sensors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[
            _spot("solent", SOLENT_POINT, "bay", tide_station="model"),
            KEELBOAT,
            BEGINNER,
        ],
    )
    entry.add_to_hass(hass)
    mock_world(aioclient_mock)
    await set_up_abroad(hass, entry, freezer)
    data = entry.runtime_data
    conditions = data.results.data.conditions["spot_solent"]
    assert conditions.tides is not None
    assert conditions.tides.datum == "MSL"
    assert conditions.tide_events == ()
    assert any(hour.tide_height is not None for hour in conditions.hours)
    assert data.budget.today >= 1
    assert hass.states.get("sensor.solent_next_high_tide") is None


async def test_failing_warnings_stay(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """When a warning source fails, the warnings it last gave stay until they end."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[
            _spot("wadden", WADDEN_POINT, "bay", marine_zone="meteoalarm"),
            _spot("halifax", HALIFAX, "bay", marine_zone="eccc:m0000053"),
            KEELBOAT,
            BEGINNER,
        ],
    )
    entry.add_to_hass(hass)
    mock_world(aioclient_mock, {HALIFAX: WADDEN_POINT})
    aioclient_mock.get(f"{eccc.API}/m0000053", json=fixture("eccc_area_m0000053"))
    await set_up_abroad(hass, entry, freezer)
    warnings = entry.runtime_data.sources.alerts
    halifax = [alert for alert in warnings.data or () if alert.zone.startswith("eccc:")]
    assert halifax
    # Canada's service fails, and MeteoAlarm's feed still answers.
    aioclient_mock.clear_requests()
    mock_world(aioclient_mock, {HALIFAX: WADDEN_POINT})
    aioclient_mock.get(f"{eccc.API}/m0000053", status=503)
    freezer.tick(timedelta(minutes=6))
    await warnings.async_refresh()
    assert warnings.last_update_success
    assert [
        alert for alert in warnings.data or () if alert.zone.startswith("eccc:")
    ] == halifax


async def test_regions_kept_when_meteoalarm_cannot_be_reached(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Regions saved earlier are used when the newest can't be fetched."""
    freezer.move_to(WORLD_RECORDED)
    mock_world(aioclient_mock)
    regions = Regions(hass)
    assert (await regions.async_place(*WADDEN_POINT)).countries == ("NL",)
    # Another start reads them from disk.
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[STORAGE_KEY]["data"]["name"].startswith("MeteoAlarm_Geocodes")
    aioclient_mock.clear_requests()
    again = Regions(hass)
    assert (await again.async_place(*WADDEN_POINT)).regions == ("NL806", "NL809")
    assert aioclient_mock.call_count == 0
    # A month later, the newest can't be listed; the saved ones still work.
    aioclient_mock.get(meteoalarm.GEOCODES_LIST, status=503)
    freezer.tick(timedelta(days=31))
    assert (await again.async_place(*WADDEN_POINT)).regions == ("NL806", "NL809")
    # Outside Europe, nothing is downloaded.
    aioclient_mock.clear_requests()
    assert await Regions(hass).async_place(*HALIFAX) == meteoalarm.Place((), ())
    assert aioclient_mock.call_count == 0
