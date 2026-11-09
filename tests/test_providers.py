"""Tests for the data providers, against recorded responses."""

from __future__ import annotations

from datetime import UTC, date, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast.providers import (
    ProviderError,
    fetch_json,
    noaa_coops,
    nws,
    open_meteo,
)

from .conftest import BAY_POINT, HARBOR_POINT, fixture, mock_suggestions

BEGIN = date(2026, 11, 2)


def test_forecast() -> None:
    """Each place gets every variable from each of the three models."""
    forecasts = open_meteo.parse_forecast(fixture("open_meteo_forecast"), 3)
    assert len(forecasts) == 3
    harbor = forecasts[0]
    assert len(harbor.times) == 192
    assert harbor.times[0] == datetime(2026, 11, 1, tzinfo=UTC)
    assert len(harbor.at("wind_speed_10m", 50)) == 3
    assert all(value is not None for value in harbor.at("wind_speed_10m", 50))
    # ICON has no visibility here.
    assert set(harbor.values["visibility"][2]) == {None}


def test_forecast_needs_every_place() -> None:
    """A response for fewer places than asked for is an error."""
    with pytest.raises(ProviderError):
        open_meteo.parse_forecast(fixture("open_meteo_forecast"), 4)


def test_marine() -> None:
    """Marine data comes for the open water spots."""
    marine = open_meteo.parse_marine(fixture("open_meteo_marine"), 2)
    assert [len(place.times) for place in marine] == [192, 192]
    assert marine[0].values["wave_height"][40] is not None


def test_open_meteo_calls() -> None:
    """Calls are counted the way Open-Meteo counts them."""
    # 8 variables from 3 models over 8 days: 2.4 calls a place.
    assert open_meteo.forecast_calls(3) == pytest.approx(7.2)
    assert open_meteo.marine_calls(2) == 2


async def test_harmonic_tide_station(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A harmonic station has highs, lows and hourly heights."""
    for interval in ("hilo", "h"):
        aioclient_mock.get(
            noaa_coops.DATA_URL,
            params={"station": "9410170", "interval": interval},
            json=fixture(f"noaa_tides_9410170_{interval}"),
        )
    tides = await noaa_coops.async_get_tides(
        async_get_clientsession(hass), "9410170", BEGIN
    )
    assert len(tides.events) == 38
    assert len(tides.hourly) == 241
    assert tides.events[0].time == datetime(2026, 11, 2, 5, 38, tzinfo=UTC)
    assert not tides.events[0].high
    requested = aioclient_mock.mock_calls[0][1]
    assert requested.query["datum"] == "MLLW"
    assert requested.query["application"] == "SailCast"


async def test_subordinate_tide_station(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A subordinate station has only highs and lows."""
    for interval in ("hilo", "h"):
        aioclient_mock.get(
            noaa_coops.DATA_URL,
            params={"station": "9410166", "interval": interval},
            json=fixture(f"noaa_tides_9410166_{interval}"),
        )
    tides = await noaa_coops.async_get_tides(
        async_get_clientsession(hass), "9410166", BEGIN
    )
    assert len(tides.events) == 38
    assert tides.hourly == ()


def test_tides_error() -> None:
    """A station without predictions is an error."""
    with pytest.raises(ProviderError, match="9410166"):
        noaa_coops.parse_tide_events(fixture("noaa_tides_9410166_h"), "9410166")


async def test_currents(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Current stations give slack and peak times, and their directions."""
    aioclient_mock.get(
        noaa_coops.DATA_URL,
        params={"station": "PCT0056", "bin": "1", "interval": "MAX_SLACK"},
        json=fixture("noaa_currents_PCT0056_1"),
    )
    currents = await noaa_coops.async_get_currents(
        async_get_clientsession(hass), "PCT0056_1", BEGIN
    )
    assert currents.station == "PCT0056_1"
    assert (currents.flood_direction, currents.ebb_direction) == (62, 245)
    assert len(currents.events) == 77
    assert currents.events[0].speed < 0  # an ebb
    assert currents.events[1].speed == 0  # slack


async def test_station_lists(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Station lists come nearest first, and weak currents are left out."""
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/tidepredstations.json",
        json=fixture("noaa_tide_stations"),
    )
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/stations.json",
        json=fixture("noaa_current_stations"),
    )
    session = async_get_clientsession(hass)
    tide_stations = await noaa_coops.async_tide_stations_near(
        session, *BAY_POINT, miles=25
    )
    assert [station.id for station in tide_stations[:2]] == ["9410170", "9410152"]
    assert "9410166" in {station.id for station in tide_stations}
    current_stations = await noaa_coops.async_current_stations(session)
    ids = {station.id for station in current_stations}
    assert {"PCT0056_1", "PCT0056_2"} <= ids
    assert "PCT0076_1" not in ids  # weak and variable


def test_alerts() -> None:
    """Alerts run from onset to end, one per zone that's asked for."""
    alerts = nws.parse_alerts(fixture("nws_alerts"), {"PZZ740", "PZZ745"})
    assert len(alerts) == 1
    advisory = alerts[0]
    assert advisory.event == "Small Craft Advisory"
    assert advisory.zone == "PZZ745"
    assert advisory.start == datetime(2026, 11, 3, 21, tzinfo=UTC)
    assert advisory.end == datetime(2026, 11, 4, 12, tzinfo=UTC)
    assert nws.parse_alerts(fixture("nws_alerts"), {"PZZ740"}) == []


def test_alerts_skip_cancellations_and_tests() -> None:
    """Cancelled alerts and test messages don't count."""
    payload = fixture("nws_alerts")
    feature = payload["features"][0]["properties"]
    feature["messageType"] = "Cancel"
    assert nws.parse_alerts(payload, {"PZZ745"}) == []
    feature["messageType"] = "Alert"
    feature["status"] = "Test"
    assert nws.parse_alerts(payload, {"PZZ745"}) == []


async def test_zone_containing_the_spot(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A pin on open water is in its marine zone."""
    mock_suggestions(aioclient_mock)
    zones, covered = await nws.async_marine_zones(
        async_get_clientsession(hass), *HARBOR_POINT
    )
    assert [(zone.id, zone.distance_km) for zone in zones] == [("PZZ740", 0.0)]
    assert covered


async def test_nearest_zone(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A pin in the bay gets the forecast office's zones, nearest first."""
    mock_suggestions(aioclient_mock)
    zones, covered = await nws.async_marine_zones(
        async_get_clientsession(hass), *BAY_POINT
    )
    assert covered
    assert [zone.id for zone in zones] == ["PZZ740", "PZZ745"]
    assert 0 < zones[0].distance_km < 10
    assert zones[1].distance_km > zones[0].distance_km
    # Only the office's own zones are measured.
    measured = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert not any("PZZ6" in url for url in measured)


async def test_no_zones_outside_the_us(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Away from NWS waters there's no zone, and no error."""
    aioclient_mock.get(f"{nws.API}/zones", json={"features": []})
    aioclient_mock.get(f"{nws.API}/points/51.5000,-0.1000", status=404, json={})
    zones = await nws.async_marine_zones(async_get_clientsession(hass), 51.5, -0.1)
    assert zones == ([], False)


@pytest.mark.parametrize(
    ("mock", "match"),
    [
        ({"status": 503, "text": "busy"}, "503: busy"),
        ({"text": "not json"}, "invalid|Expecting"),
        ({"exc": TimeoutError()}, "TimeoutError"),
    ],
)
async def test_fetch_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock: dict[str, object],
    match: str,
) -> None:
    """Server errors, bad JSON and timeouts all raise ProviderError."""
    aioclient_mock.get("https://example.com/data", **mock)
    with pytest.raises(ProviderError, match=match):
        await fetch_json(async_get_clientsession(hass), "https://example.com/data")


async def test_requests_name_the_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every request sends SailCast's User-Agent."""
    aioclient_mock.get("https://example.com/data", json={})
    await fetch_json(async_get_clientsession(hass), "https://example.com/data")
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["User-Agent"].startswith("SailCast")
