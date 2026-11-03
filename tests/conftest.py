"""Shared fixtures for the SailCast tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
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
from custom_components.sailcast.providers import (
    metar,
    meteoalarm,
    ndbc,
    noaa_coops,
    nws,
    open_meteo,
    openfreemap,
    rws,
    worldtides,
)

FIXTURES = Path(__file__).parent / "fixtures"
# When the fixtures were recorded: 2:36 PM in San Diego.
RECORDED = datetime(2026, 11, 2, 22, 36, tzinfo=UTC)

# Made-up spots in San Diego, near the test instance's home and far from
# anywhere the maintainer sails. The fixtures were recorded for them.
HARBOR_POINT = (32.75, -117.27)
BAY_POINT = (32.68, -117.17)
RIVER_POINT = (32.76, -117.24)
POINTS = (HARBOR_POINT, BAY_POINT, RIVER_POINT)
# The buoys and airports the readings were recorded at, where NDBC and
# aviationweather.gov put them, in the order the station forecasts were.
STATION_POINTS = {
    "46258": (32.749, -117.502),
    "SDBC1": (32.714, -117.174),
    "KSAN": (32.7364, -117.1973),
    "KNZY": (32.6922, -117.2098),
}
STATION_NAMES = {
    "46258": "Mission Bay West, CA (220)",
    "SDBC1": "9410170 - San Diego, CA",
    "KSAN": "San Diego Intl Arpt",
    "KNZY": "San Diego/North Island NAS",
}
TILE_URL = re.compile(
    r"^https://tiles\.openfreemap\.org/planet/[^/]+/(\d+)/(\d+)/(\d+)\.pbf"
)
# Spots outside the US, in the Solent, the Wadden Sea and on Lake Garda, with
# their recordings made at 2:30 PM UTC the next day. Vlissingen had a
# MeteoAlarm warning in effect then.
WORLD_RECORDED = datetime(2026, 11, 3, 14, 30, tzinfo=UTC)
SOLENT_POINT = (50.785, -1.305)
WADDEN_POINT = (53.18, 5.38)
GARDA_POINT = (45.8, 10.83)
WORLD_POINTS = (SOLENT_POINT, WADDEN_POINT, GARDA_POINT)
VLISSINGEN_POINT = (51.44, 3.57)
WORLDTIDES_KEY = "made-up-worldtides-key"


def fixture(name: str) -> Any:
    """Return a recorded response."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def text_fixture(name: str) -> str:
    """Return a recorded response that isn't JSON."""
    return (FIXTURES / name).read_text()


def with_stations(
    spot: ConfigSubentryData, buoy: str | None = None, airport: str | None = None
) -> ConfigSubentryData:
    """Return a test spot that also reads a buoy and an airport."""
    chosen = {"buoy": buoy, "airport": airport}
    data = dict(spot["data"]) | chosen
    data["source_names"] = {
        key: STATION_NAMES[station] for key, station in chosen.items() if station
    }
    data["source_points"] = {
        key: list(STATION_POINTS[station]) for key, station in chosen.items() if station
    }
    return ConfigSubentryData(**{**spot, "data": data})


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
SOLENT = _spot(
    "solent",
    SOLENT_POINT,
    "bay",
    tide_station="worldtides",
    marine_zone="meteoalarm",
)
WADDEN = _spot(
    "wadden",
    WADDEN_POINT,
    "bay",
    tide_station="rws:harlingen.waddenzee",
    marine_zone="meteoalarm",
    source_names={"tide_station": "Harlingen, Waddenzee"},
)
GARDA = _spot("garda", GARDA_POINT, "lake", marine_zone="meteoalarm")
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


def by_point(
    name: str,
    points: tuple[tuple[float, float], ...],
    stand_ins: dict[tuple[float, float], tuple[float, float]] | None = None,
) -> Any:
    """Answer an Open-Meteo request with the recorded place for each point.

    `stand_ins` answers other points with a recorded one's place. One place
    comes back on its own, as Open-Meteo sends it.
    """
    places = fixture(name)
    if isinstance(places, dict):
        places = [places]
    stand_ins = stand_ins or {}

    async def respond(method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        lats = [float(value) for value in url.query["latitude"].split(",")]
        lons = [float(value) for value in url.query["longitude"].split(",")]
        chosen = [
            places[points.index(stand_ins.get((lat, lon), (lat, lon)))]
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
        open_meteo.FORECAST_URL,
        params={
            "models": ",".join(open_meteo.MODELS),
            "hourly": ",".join(open_meteo.FORECAST_VARIABLES),
        },
        side_effect=by_point("open_meteo_forecast", POINTS),
    )
    aioclient_mock.get(
        open_meteo.MARINE_URL,
        params={"hourly": ",".join(open_meteo.MARINE_VARIABLES)},
        side_effect=by_point("open_meteo_marine", POINTS[:2]),
    )
    aioclient_mock.get(
        open_meteo.ENSEMBLE_URL, side_effect=by_point("open_meteo_spread", POINTS)
    )
    aioclient_mock.get(f"{nws.API}/alerts/active", json=fixture("nws_alerts"))
    mock_readings(aioclient_mock)
    mock_tiles(aioclient_mock)
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


def mock_readings(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer the buoys, airports and the forecast where they are."""
    for buoy in ("46258", "SDBC1"):
        aioclient_mock.get(
            ndbc.REALTIME_URL.format(station=buoy),
            text=(FIXTURES / f"ndbc_{buoy}.txt").read_text(),
        )
    aioclient_mock.get(metar.METAR_URL, json=fixture("aviationweather_metar"))
    aioclient_mock.get(
        open_meteo.FORECAST_URL,
        params={"hourly": ",".join(open_meteo.NEARBY_VARIABLES)},
        side_effect=by_point("open_meteo_nearby", tuple(STATION_POINTS.values())),
    )
    aioclient_mock.get(
        open_meteo.MARINE_URL,
        params={"hourly": ",".join(open_meteo.BUOY_VARIABLES)},
        side_effect=by_point(
            "open_meteo_marine_buoys",
            (STATION_POINTS["46258"], STATION_POINTS["SDBC1"]),
        ),
    )


def mock_tiles(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer map tile requests with the recorded tiles' water."""
    aioclient_mock.get(openfreemap.TILEJSON_URL, json=fixture("openfreemap_tilejson"))

    async def respond(method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        match = TILE_URL.match(str(url))
        assert match is not None
        z, x, y = match.groups()
        path = FIXTURES / "tiles" / z / x / f"{y}.pbf"
        if not path.exists():
            # Only the lake abroad's tiles were recorded.
            return AiohttpClientMockResponse(method, url, status=404)
        return AiohttpClientMockResponse(method, url, response=path.read_bytes())

    aioclient_mock.get(TILE_URL, side_effect=respond)


def wind_response(start: datetime = RECORDED) -> Any:
    """Answer a wind grid request with made-up wind for each point.

    Every point has the same week from the start's midnight (UTC): wind
    building from 5 kt by a knot an hour and starting again each day, from
    the west, with gusts 6 kt over it. Points further north get a knot more
    for each row.
    """
    midnight = int(start.replace(hour=0, minute=0, second=0).timestamp())

    async def respond(method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        lats = [float(value) for value in url.query["latitude"].split(",")]
        lons = [float(value) for value in url.query["longitude"].split(",")]
        south = min(lats)
        places = [
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": {
                    "time": [midnight + hour * 3600 for hour in range(168)],
                    "wind_speed_10m": [
                        5.0 + hour % 24 + round((lat - south) * 50)
                        for hour in range(168)
                    ],
                    "wind_direction_10m": [270] * 168,
                    "wind_gusts_10m": [
                        11.0 + hour % 24 + round((lat - south) * 50)
                        for hour in range(168)
                    ],
                },
            }
            for lat, lon in zip(lats, lons, strict=True)
        ]
        return AiohttpClientMockResponse(
            method, url, json=places if len(places) > 1 else places[0]
        )

    return respond


def mock_wind(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer wind grid requests with made-up wind."""
    aioclient_mock.get(
        open_meteo.FORECAST_URL,
        params={"hourly": ",".join(open_meteo.WIND_VARIABLES)},
        side_effect=wind_response(),
    )


@pytest.fixture
def sources(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Answer every provider request with the recorded responses."""
    mock_sources(aioclient_mock)
    return aioclient_mock


async def set_up(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Set an entry up at the time the fixtures were recorded.

    The pins' shorelines are measured in the background once setup is done,
    and the results are worked out again with them. The clock then moves past
    the refresh's cooldown, so later changes refresh at once, and goes back.
    """
    freezer.move_to(RECORDED)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.move_to(RECORDED)


@pytest.fixture
async def loaded(
    hass: HomeAssistant,
    sailcast_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Return the test entry, set up at the time the fixtures were recorded."""
    await set_up(hass, sailcast_entry, freezer)
    return sailcast_entry


@pytest.fixture
def observed_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an entry whose three test spots also read buoys and airports."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        subentries_data=[
            with_stations(HARBOR, "46258", "KSAN"),
            with_stations(BAY, "SDBC1", "KNZY"),
            with_stations(RIVER, airport="KSAN"),
            KEELBOAT,
            CRUISER,
            SAILOR,
            BEGINNER,
        ],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def observed(
    hass: HomeAssistant,
    observed_entry: MockConfigEntry,
    sources: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Return that entry, set up when the readings were recorded."""
    await set_up(hass, observed_entry, freezer)
    return observed_entry


def mock_suggestions(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer the station, zone, buoy and airport lookups for the test pins."""
    aioclient_mock.get(
        ndbc.STATIONS_URL, text=(FIXTURES / "ndbc_stations.xml").read_text()
    )
    aioclient_mock.get(
        metar.STATIONINFO_URL, json=fixture("aviationweather_stationinfo")
    )
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


def meteoalarm_geocodes() -> dict[str, Any]:
    """Return made-up MeteoAlarm region outlines around the spots abroad.

    MeteoAlarm's own outlines aren't openly licensed, so these are rough
    boxes with the real regions' codes: the Wadden spot in two regions, and
    Garda's in Veneto with Lombardia and Trentino within a few kilometers.
    """

    def box(code: str, name: str, *bounds: float) -> dict[str, Any]:
        south, north, west, east = bounds
        ring = [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]
        return {
            "type": "Feature",
            "properties": {
                "code": code,
                "country": code[:2],
                "name": name,
                "type": "EMMA_ID",
            },
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }

    return {
        "type": "FeatureCollection",
        "features": [
            box("NL801", "Vlissingen", 51.3, 51.6, 3.2, 3.9),
            box("NL806", "Waddenzee", 53.0, 53.5, 4.8, 6.0),
            box("NL809", "Harlingen", 53.1, 53.25, 5.2, 5.5),
            box("NL017", "Friesland", 52.7, 53.05, 5.4, 6.4),
            box("IT006", "Veneto", 45.0, 46.0, 10.82, 12.5),
            box("IT003", "Lombardia", 45.0, 46.3, 9.0, 10.8),
            box("IT002", "Trentino Alto Adige", 45.83, 47.0, 10.4, 12.0),
        ],
    }


def worldtides_response(heights: bool = True) -> Any:
    """Answer a WorldTides request with made-up predictions in its shape.

    The tide is a plain 12.42-hour wave, 1.5 m either side of 2 m above
    chart datum, high at the start of the request.
    """
    period = 44_712

    async def respond(method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        if url.query.get("key") != WORLDTIDES_KEY:
            return AiohttpClientMockResponse(
                method,
                url,
                status=400,
                json={"status": 400, "error": "API key is invalid"},
            )
        start = int(url.query["start"])
        length = int(url.query["length"])
        step = int(url.query["step"])

        def height(when: int) -> float:
            return round(2.0 + 1.5 * math.cos(2 * math.pi * (when - start) / period), 3)

        extremes = [
            {
                "dt": start + k * period // 2,
                "height": height(start + k * period // 2),
                "type": "Low" if k % 2 else "High",
            }
            for k in range(2 * length // period + 1)
        ]
        payload = {
            "status": 200,
            "callCount": 3,
            "copyright": (
                "Made-up predictions for SailCast's tests, in WorldTides' shape."
            ),
            "requestDatum": url.query["datum"],
            "responseDatum": "CD",
            "station": "Test gauge",
            "extremes": extremes,
        }
        if heights:
            payload["heights"] = [
                {"dt": when, "height": height(when)}
                for when in range(start, start + length + 1, step)
            ]
        return AiohttpClientMockResponse(method, url, json=payload)

    return respond


def mock_world(
    aioclient_mock: AiohttpClientMocker,
    stand_ins: dict[tuple[float, float], tuple[float, float]] | None = None,
) -> None:
    """Answer every provider request for the spots abroad with recordings.

    WorldTides' predictions and MeteoAlarm's region outlines are made up.
    `stand_ins` answers the forecast for other pins with a recorded spot's.
    """
    aioclient_mock.get(
        open_meteo.FORECAST_URL,
        params={
            "models": ",".join(open_meteo.MODELS),
            "hourly": ",".join(open_meteo.FORECAST_VARIABLES),
        },
        side_effect=by_point("open_meteo_forecast_world", WORLD_POINTS, stand_ins),
    )
    aioclient_mock.get(
        open_meteo.MARINE_URL,
        params={"hourly": ",".join(open_meteo.MARINE_VARIABLES)},
        side_effect=by_point("open_meteo_marine_world", WORLD_POINTS[:2], stand_ins),
    )
    aioclient_mock.get(
        open_meteo.MARINE_URL,
        params={"hourly": open_meteo.SEA_LEVEL_VARIABLE},
        side_effect=by_point("open_meteo_sea_level_solent", WORLD_POINTS[:1]),
    )
    aioclient_mock.get(
        open_meteo.ENSEMBLE_URL,
        side_effect=by_point("open_meteo_spread_world", WORLD_POINTS, stand_ins),
    )

    async def rws_respond(
        method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        kind = data["AquoPlusWaarnemingMetadata"]["AquoMetadata"]["Grootheid"]["Code"]
        name = "heights" if kind == "WATHTE" else "kinds"
        return AiohttpClientMockResponse(
            method, url, json=fixture(f"rws_harlingen_{name}")
        )

    aioclient_mock.post(rws.DATA_URL, side_effect=rws_respond)
    aioclient_mock.post(rws.CATALOGUE_URL, json=fixture("rws_catalogue"))
    aioclient_mock.get(worldtides.API, side_effect=worldtides_response())
    for country in ("NL", "UK", "IT"):
        aioclient_mock.get(
            meteoalarm.FEED_URL.format(slug=meteoalarm.COUNTRIES[country][0]),
            text=text_fixture(f"meteoalarm_{country.lower()}.xml"),
        )
    for path in FIXTURES.glob("meteoalarm_cap_*.xml"):
        uuid = path.stem.removeprefix("meteoalarm_cap_")
        aioclient_mock.get(
            f"https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands/{uuid}",
            text=path.read_text(),
        )
    aioclient_mock.get(
        meteoalarm.GEOCODES_LIST,
        json=[{"name": "MeteoAlarm_Geocodes_2026_07_31.json", "type": "blob"}],
    )
    aioclient_mock.get(
        meteoalarm.GEOCODES_URL.format(name="MeteoAlarm_Geocodes_2026_07_31.json"),
        text=json.dumps(meteoalarm_geocodes()),
    )
    mock_tiles(aioclient_mock)


@pytest.fixture
def world_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an entry with the three spots abroad, a WorldTides key and a sailor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={},
        options={"worldtides_key": WORLDTIDES_KEY},
        subentries_data=[SOLENT, WADDEN, GARDA, KEELBOAT, CRUISER, BEGINNER],
    )
    entry.add_to_hass(hass)
    return entry


async def set_up_abroad(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Set an entry up in Amsterdam's time, when the spots abroad were recorded."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(WORLD_RECORDED)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.move_to(WORLD_RECORDED)
