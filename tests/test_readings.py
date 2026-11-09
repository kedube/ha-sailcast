"""Tests for readings from buoys, airports and your own sensors."""

from __future__ import annotations

from datetime import UTC, datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.providers import (
    ProviderError,
    ha_entity,
    metar,
    ndbc,
    open_meteo,
)
from custom_components.sailcast.week import readings_now

from .conftest import (
    FIXTURES,
    POINTS,
    RECORDED,
    STATION_POINTS,
    fixture,
    mock_readings,
    mock_sources,
    set_up,
)

BUOY = (FIXTURES / "ndbc_46258.txt").read_text()


def test_buoy_readings() -> None:
    """Each field keeps its newest value and time, in SailCast's units."""
    readings = ndbc.parse_readings(BUOY)
    assert set(readings.fields) == {
        "wave_height",
        "wave_period",
        "wave_direction",
        "water_temperature",
    }
    waves = readings.get("wave_height")
    assert waves is not None
    assert waves.value == 1.4
    assert waves.time == datetime(2026, 11, 2, 22, 26, tzinfo=UTC)
    assert readings.latest == waves.time


def test_buoy_fields_on_their_own_schedules() -> None:
    """Missing values are skipped, so fields can come from different rows."""
    text = (
        "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"  # noqa: E501
        "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft\n"  # noqa: E501
        "2026 11 02 22 30  MM   MM   MM    MM    MM    MM  MM 1019.6    MM  22.9    MM   MM   MM    MM\n"  # noqa: E501
        "2026 11 02 22 00 290  5.0  7.0    MM    MM    MM  MM 1019.6  21.0  22.8    MM  0.4   MM    MM\n"  # noqa: E501
        "2026 11 02 21 30 280  4.0  6.0    MM    MM    MM  MM 1019.6  21.0  22.8    MM   MM   MM    MM\n"  # noqa: E501
        "2026 11 02 21 00 280  9.0"  # cut short by the range
    )
    readings = ndbc.parse_readings(text)
    wind = readings.get("wind")
    assert wind is not None
    assert wind.value == pytest.approx(9.72, abs=0.01)
    assert wind.time == datetime(2026, 11, 2, 22, tzinfo=UTC)
    assert readings.get("gust").value == pytest.approx(13.61, abs=0.01)  # type: ignore[union-attr]
    assert readings.get("visibility").value == pytest.approx(740.8)  # type: ignore[union-attr]
    assert readings.get("water_temperature").time.minute == 30  # type: ignore[union-attr]
    assert readings.get("wave_height") is None


def test_buoy_file_without_header() -> None:
    """A file without its header can't be read."""
    with pytest.raises(ProviderError):
        ndbc.parse_readings("<html>Not found</html>\n")


async def test_buoy_reads_only_the_start(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Only the first 8 KB is asked for, and only that much is read."""
    aioclient_mock.get(ndbc.REALTIME_URL.format(station="46258"), text=BUOY * 5)
    readings = await ndbc.async_get_readings(async_get_clientsession(hass), "46258")
    assert readings.get("wave_height").value == 1.4  # type: ignore[union-attr]
    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert headers["Range"] == "bytes=0-8191"


# A station page's details, as NDBC writes them.
PAGE = (
    "<p><b>32.867 N 117.257 W</b><br>\n\t\t<br>\n"
    "\t\t<b>Site elevation:</b> {site}<br>\n"
    "\t\t<b>Air temp height:</b> 3 m above site elevation<br>\n"
    "\t\t{anemometer}"
    "\t\t<b>Water depth:</b> 65 m<br>\n</p>"
)
ANEMOMETER = "<b>Anemometer height:</b> {height} m above site elevation<br>\n"


@pytest.mark.parametrize(
    ("site", "anemometer", "height"),
    [
        # A buoy.
        ("sea level", "3.8", 3.8),
        # A pier, and a station on the shore.
        ("0 m above mean sea level", "20.2", 20.2),
        ("3.7 m above mean sea level", "10", 13.7),
        # Too high for the wind profile over open water.
        ("25 m above mean sea level", "10", None),
        # No anemometer.
        ("sea level", None, None),
    ],
)
def test_anemometer_height(
    site: str, anemometer: str | None, height: float | None
) -> None:
    """A station page says how high above the water its anemometer is."""
    page = PAGE.format(
        site=site,
        anemometer=ANEMOMETER.format(height=anemometer) if anemometer else "",
    )
    assert ndbc.parse_anemometer_height(page) == height
    assert ndbc.parse_anemometer_height("<p>Station SDBC1</p>") is None


def test_wind_at_standard_height() -> None:
    """A buoy's wind and gusts are scaled to the 10 m forecasts are for."""
    time = datetime(2026, 11, 2, 22, tzinfo=UTC)
    readings = ndbc.Readings(
        {
            "wind": ndbc.Reading(10.0, time),
            "gust": ndbc.Reading(14.0, time),
            "wave_height": ndbc.Reading(1.2, time),
        }
    )
    scaled = ndbc.at_standard_height(readings, 3.8)
    # The wind is about 10% stronger at 10 m than 3.8 m up, over open water.
    assert scaled.get("wind") == ndbc.Reading(
        pytest.approx(10.98, abs=0.01), time, from_height=3.8
    )
    assert scaled.get("gust").value == pytest.approx(15.37, abs=0.01)  # type: ignore[union-attr]
    assert scaled.get("wave_height") == readings.get("wave_height")
    # From a 20 m pier it's lighter at 10 m.
    pier = ndbc.at_standard_height(readings, 20.2)
    assert pier.get("wind").value == pytest.approx(9.39, abs=0.01)  # type: ignore[union-attr]
    # Without a height, the readings stay as they are.
    assert ndbc.at_standard_height(readings, None) is readings


async def test_buoy_wind_scaled_to_standard_height(
    hass: HomeAssistant,
    observed_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A buoy's wind reaches the forecast scaled from its anemometer to 10 m.

    The station page is looked up once; a page without a height leaves the
    readings as they are.
    """
    realtime = (
        "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"  # noqa: E501
        "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft\n"  # noqa: E501
        "2026 11 02 22 30 290  6.0  8.0    MM    MM    MM  MM 1019.6  21.0  22.9    MM   MM   MM    MM\n"  # noqa: E501
    )
    aioclient_mock.get(ndbc.REALTIME_URL.format(station="SDBC1"), text=realtime)
    aioclient_mock.get(
        ndbc.STATION_PAGE_URL.format(station="SDBC1"),
        text=PAGE.format(
            site="0 m above mean sea level", anemometer=ANEMOMETER.format(height="3.8")
        ),
    )
    mock_sources(aioclient_mock)
    await set_up(hass, observed_entry, freezer)

    observed = observed_entry.runtime_data.sources.observations
    wind = next(
        readings.get("wind")
        for key, readings in observed.data.readings.items()
        if "SDBC1" in key
    )
    assert wind is not None
    assert wind.from_height == 3.8
    # 6 m/s is 11.7 kt at 3.8 m, and 12.8 kt at 10 m.
    assert wind.value == pytest.approx(12.81, abs=0.01)
    # It's the bay's freshest wind, and the panel says where it was read.
    data = observed_entry.runtime_data
    bay = readings_now(data.sources.readings(data.profiles.spots["spot_bay"]), RECORDED)
    assert bay["fields"]["wind"] == {
        "value": pytest.approx(12.81, abs=0.01),
        "time": "2026-11-02T22:30:00+00:00",
        "kind": "buoy",
        "station": "SDBC1",
        "from_height": 3.8,
    }
    assert "from_height" not in bay["fields"]["wind_direction"]
    pages = [
        str(url)
        for _, url, _, _ in aioclient_mock.mock_calls
        if "station_page" in str(url)
    ]
    assert sorted(pages) == [
        ndbc.STATION_PAGE_URL.format(station="46258"),
        ndbc.STATION_PAGE_URL.format(station="SDBC1"),
    ]


def test_buoy_list() -> None:
    """Stations that report weather or waves, by NDBC's ID in capitals."""
    buoys = ndbc.parse_stations((FIXTURES / "ndbc_stations.xml").read_text())
    by_id = {buoy.id: buoy for buoy in buoys}
    assert by_id["SDBC1"].name == "9410170 - San Diego, CA"
    assert (by_id["46258"].latitude, by_id["46258"].longitude) == (32.749, -117.502)
    # A station without weather readings isn't offered.
    assert "46235" not in by_id
    text = '<station id="x1" lat="1" lon="2" name="Bay &amp; Harbor" met="y"/>'
    assert ndbc.parse_stations(text)[0].name == "Bay & Harbor"


def test_airport_reports() -> None:
    """An airport's wind, direction, air and visibility, timed by its report."""
    reports = metar.parse_reports(fixture("aviationweather_metar"))
    ksan = reports["KSAN"]
    assert ksan.get("wind").value == 8  # type: ignore[union-attr]
    assert ksan.get("wind_direction").value == 300  # type: ignore[union-attr]
    assert ksan.get("temperature").value == 22.2  # type: ignore[union-attr]
    assert ksan.get("visibility").value == pytest.approx(16093.44)  # type: ignore[union-attr]
    assert ksan.latest == datetime(2026, 11, 2, 21, 51, tzinfo=UTC)
    # No gust in the report says nothing about gusts.
    assert ksan.get("gust") is None
    assert reports["KNZY"].get("wind").value == 10  # type: ignore[union-attr]


def test_airport_report_details() -> None:
    """The newest report counts; calm and variable wind have no direction."""
    reports = metar.parse_reports(
        [
            {"icaoId": "KAAA", "obsTime": 100, "wspd": 12, "wdir": 200},
            {"icaoId": "KAAA", "obsTime": 200, "wspd": 6, "wdir": "VRB", "wgst": 15},
            {"icaoId": "KBBB", "obsTime": 200, "wspd": 0, "wdir": 0},
            {"icaoId": "KCCC", "obsTime": "soon"},
        ]
    )
    assert set(reports) == {"KAAA", "KBBB"}
    assert reports["KAAA"].get("wind").value == 6  # type: ignore[union-attr]
    assert reports["KAAA"].get("gust").value == 15  # type: ignore[union-attr]
    assert reports["KAAA"].get("wind_direction") is None
    assert reports["KBBB"].get("wind_direction") is None
    with pytest.raises(ProviderError):
        metar.parse_reports({"error": "busy"})


@pytest.mark.parametrize(
    ("value", "miles"),
    [
        ("10+", 10.0),
        (6, 6.0),
        (0.25, 0.25),
        ("1/2", 0.5),
        ("1 1/2", 1.5),
        ("M1/4", 0.25),
        ("", None),
        ("fog", None),
        (None, None),
        (True, None),
    ],
)
def test_visibility_miles(value: object, miles: float | None) -> None:
    """Visibility is a number of miles, or text for one."""
    assert metar.visibility_miles(value) == miles


def test_airports_near() -> None:
    """Only airports that send reports are offered, named without stray spaces."""
    airports = metar.parse_airports(fixture("aviationweather_stationinfo"))
    names = {airport.id: airport.name for airport in airports}
    assert names["KSAN"] == "San Diego Intl Arpt"
    assert names["KNKX"] == "Miramar"
    # Buoys in the same box send no airport reports.
    assert all(airport.id.startswith(("K", "M")) for airport in airports)


async def test_airports_near_ask_for_a_box(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The box reaches the distance each way, with four decimals."""
    aioclient_mock.get(
        metar.STATIONINFO_URL, json=fixture("aviationweather_stationinfo")
    )
    found = await metar.async_airports_near(
        async_get_clientsession(hass), 32.68, -117.17, 40
    )
    assert found
    _, url, _, _ = aioclient_mock.mock_calls[0]
    south, west, north, east = url.query["bbox"].split(",")
    assert all(
        len(value.partition(".")[2]) == 4 for value in (south, west, north, east)
    )
    assert (float(south) + float(north)) / 2 == pytest.approx(32.68)
    assert (float(west) + float(east)) / 2 == pytest.approx(-117.17)
    assert (float(north) - float(south)) * 111.195 / 2 == pytest.approx(40, abs=0.01)


async def test_sensors(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Sensors are read in their own units, timed by when they last reported."""
    freezer.move_to(datetime(2026, 11, 2, 22, tzinfo=UTC))
    hass.states.async_set("sensor.wind", "11.5", {"unit_of_measurement": "mph"})
    hass.states.async_set("sensor.direction", "370", {"unit_of_measurement": "°"})
    hass.states.async_set("sensor.air", "68", {"unit_of_measurement": "°F"})
    hass.states.async_set("sensor.gust", "unavailable")
    hass.states.async_set("sensor.water", "warm", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.odd", "3", {"unit_of_measurement": "furlongs/h"})
    readings = ha_entity.read(
        hass,
        {
            "wind": "sensor.wind",
            "wind_direction": "sensor.direction",
            "temperature": "sensor.air",
            "gust": "sensor.gust",
            "water_temperature": "sensor.water",
            "missing": "sensor.nowhere",
        },
    )
    assert set(readings.fields) == {"wind", "wind_direction", "temperature"}
    assert readings.get("wind").value == pytest.approx(9.99, abs=0.01)  # type: ignore[union-attr]
    assert readings.get("wind_direction").value == 10  # type: ignore[union-attr]
    assert readings.get("temperature").value == pytest.approx(20)  # type: ignore[union-attr]
    assert readings.get("wind").time == datetime(2026, 11, 2, 22, tzinfo=UTC)  # type: ignore[union-attr]
    assert ha_entity.read(hass, {"gust": "sensor.odd"}).fields == {}
    # Without a unit, knots and °C are assumed.
    assert ha_entity.convert("wind", 7, None) == 7
    assert ha_entity.convert("visibility", 7, None) is None


def test_calls_for_readings() -> None:
    """The forecast at stations, buoy marine data and the spread are cheap."""
    # 4 variables from 3 models over 2 days: 1.2 calls a place.
    assert open_meteo.nearby_calls(4) == pytest.approx(4.8)
    assert open_meteo.buoy_calls(2) == 2
    assert open_meteo.spread_calls(3) == 3


async def test_forecast_at_stations(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Buoys and airports get today's wind and air from the three models.

    A buoy's comes from the sea, as the spots' does, and an airport's from land.
    """
    mock_readings(aioclient_mock)
    session = async_get_clientsession(hass)
    buoys = [STATION_POINTS["46258"], STATION_POINTS["SDBC1"]]
    airports = [STATION_POINTS["KSAN"], STATION_POINTS["KNZY"]]
    forecasts = await open_meteo.async_get_nearby(session, buoys, sea=True)
    forecasts += await open_meteo.async_get_nearby(session, airports, sea=False)
    cells = [url.query["cell_selection"] for _, url, _, _ in aioclient_mock.mock_calls]
    assert cells == ["sea", "land"]
    assert len(forecasts) == 4
    assert len(forecasts[0].times) == 48
    assert set(forecasts[2].values) == set(open_meteo.NEARBY_VARIABLES)
    assert forecasts[2].at("wind_speed_10m", 22) == (4.4, 6.6, 6.1)
    marine = await open_meteo.async_get_buoy_marine(session, buoys)
    assert marine[0].values["wave_height"][22] == 1.48


async def test_spread(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The ensemble's spread comes for each spot, in knots."""
    aioclient_mock.get(
        open_meteo.ENSEMBLE_URL,
        json=fixture("open_meteo_spread"),
    )
    spreads = await open_meteo.async_get_spread(async_get_clientsession(hass), POINTS)
    assert len(spreads) == 3
    assert len(spreads[0].times) == 192
    assert all(value is not None for value in spreads[0].values[:48])
    _, url, _, _ = aioclient_mock.mock_calls[0]
    assert url.query["models"] == open_meteo.SPREAD_MODEL
    assert url.query["cell_selection"] == "sea"
