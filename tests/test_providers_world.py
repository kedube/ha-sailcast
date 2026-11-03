"""Tests for the tide and warning providers outside the US."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import math
import re
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sailcast import alerts, tides
from custom_components.sailcast.limits import WarningGroup, warning_group
from custom_components.sailcast.providers import (
    ProviderError,
    Tides,
    chs,
    eccc,
    kartverket,
    meteoalarm,
    noaa_coops,
    nws,
    open_meteo,
    rws,
    turning_points,
    worldtides,
)

from .conftest import (
    GARDA_POINT,
    SOLENT_POINT,
    VLISSINGEN_POINT,
    WADDEN_POINT,
    WORLD_RECORDED,
    WORLDTIDES_KEY,
    fixture,
    meteoalarm_geocodes,
    text_fixture,
    worldtides_response,
)

BEGIN = datetime(2026, 11, 2, tzinfo=UTC)


def test_turning_points() -> None:
    """Highs and lows fall between the hours, on the curve through them."""
    hourly = [
        (BEGIN + timedelta(hours=h), 1.5 * math.cos(2 * math.pi * (h - 3.3) / 12.42))
        for h in range(30)
    ]
    events = turning_points(hourly)
    assert [event.high for event in events] == [True, False, True, False, True]
    assert abs(events[0].time - (BEGIN + timedelta(hours=3.3))) < timedelta(minutes=3)
    assert events[1].height == pytest.approx(-1.5, abs=0.01)


def test_rijkswaterstaat() -> None:
    """Dutch stations come from the catalogue, and tides in cm above NAP."""
    stations = rws.parse_stations(fixture("rws_catalogue"))
    assert len(stations) > 90
    harlingen = next(s for s in stations if s.id == "harlingen.waddenzee")
    assert harlingen.name == "Harlingen, Waddenzee"
    found = rws.parse_tides(
        fixture("rws_harlingen_heights"),
        fixture("rws_harlingen_kinds"),
        "rws:harlingen.waddenzee",
    )
    assert found.datum == "NAP"
    assert len(found.events) > 35
    assert all(
        a.high != b.high for a, b in zip(found.events, found.events[1:], strict=False)
    )
    assert all(event.time.tzinfo == UTC for event in found.events)
    # Heights are in meters: Harlingen's highs are about a meter above NAP.
    assert 0.3 < max(event.height for event in found.events) < 2.5
    with pytest.raises(ProviderError):
        rws.parse_tides({"Succesvol": False}, {}, "rws:x")
    assert rws.covers(*WADDEN_POINT)
    assert not rws.covers(*SOLENT_POINT)


def chs_payload(start: datetime, values: list[float]) -> list[dict[str, Any]]:
    """Return made-up CHS events, six hours apart: CHS's data can't be passed on."""
    return [
        {"eventDate": (start + timedelta(hours=6 * i)).isoformat(), "value": value}
        for i, value in enumerate(values)
    ]


def test_canadian_hydrographic_service() -> None:
    """Highs and lows are told apart by their neighbors, even two highs together."""
    stations = chs.parse_stations(
        [
            {
                "id": "abc",
                "code": "00490",
                "officialName": "Somewhere",
                "latitude": 44.66,
                "longitude": -63.58,
                "timeSeries": [{"code": "wlp-hilo"}, {"code": "wlp"}],
            },
            {
                "id": "lakes",
                "code": "11690",
                "officialName": "A lake gauge",
                "latitude": 48.4,
                "longitude": -89.2,
                "timeSeries": [{"code": "wlo"}],
            },
        ]
    )
    assert [(s.id, s.code) for s in stations] == [("abc", "00490")]
    found = chs.parse_tides(
        chs_payload(BEGIN, [0.3, 1.6, 0.5, 1.7, 1.65, 0.4]),
        chs_payload(BEGIN, [1.0, 1.1]),
        "chs:abc",
    )
    assert [event.high for event in found.events] == [
        False,
        True,
        False,
        True,
        True,
        False,
    ]
    assert found.datum == "CD"
    assert found.notice is not None
    assert "not to be used for navigation" in found.notice
    assert len(found.hourly) == 2


def test_kartverket() -> None:
    """Norwegian tides are flagged high or low, in cm above chart datum."""
    found = kartverket.parse_tides(
        text_fixture("kartverket_bergen_tab.xml"),
        text_fixture("kartverket_bergen_pre.xml"),
        kartverket.source(60.39, 5.32),
    )
    assert found.name == "Bergen"
    assert found.notice == "©Kartverket"
    assert found.datum == "CD"
    assert all(
        a.high != b.high for a, b in zip(found.events, found.events[1:], strict=False)
    )
    assert len(found.hourly) > 200
    nothing = '<tide><locationdata><nodata info="Sorry."/></locationdata></tide>'
    with pytest.raises(kartverket.NoDataError):
        kartverket.parse_tides(nothing, nothing, "kartverket:0,0")
    assert kartverket.covers(60.39, 5.32)
    assert not kartverket.covers(*WADDEN_POINT)


async def test_worldtides(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """WorldTides answers by position; a refused key is told apart."""
    aioclient_mock.get(worldtides.API, side_effect=worldtides_response())
    session = async_get_clientsession(hass)
    found = await worldtides.async_get_tides(
        session, WORLDTIDES_KEY, *SOLENT_POINT, BEGIN
    )
    assert found.station == worldtides.source(*SOLENT_POINT)
    assert found.datum == "CD"
    assert found.name == "Test gauge"
    assert found.notice is not None
    assert len(found.hourly) == 14 * 24 + 1
    assert found.events[0].high
    # The outputs go as bare flags, as WorldTides documents them.
    url = str(aioclient_mock.mock_calls[0][1])
    assert "?heights&extremes&" in url
    with pytest.raises(worldtides.KeyRejectedError, match="API key is invalid"):
        await worldtides.async_get_tides(session, "wrong", *SOLENT_POINT, BEGIN)
    assert (
        worldtides.parse_tides({"status": 200, "responseDatum": "LAT"}, 200, "x").datum
        == "LAT"
    )
    with pytest.raises(worldtides.KeyRejectedError):
        worldtides.parse_tides({"status": 400, "error": "Not enough credits"}, 400, "x")
    with pytest.raises(ProviderError) as caught:
        worldtides.parse_tides({"status": 500, "error": "Busy"}, 500, "x")
    assert not isinstance(caught.value, worldtides.KeyRejectedError)


async def test_sea_level(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The ocean model's sea level is a rough tide above mean sea level."""
    aioclient_mock.get(
        open_meteo.MARINE_URL, json=fixture("open_meteo_sea_level_solent")
    )
    found = await tides.async_fetch(
        async_get_clientsession(hass), "model:50.7850,-1.3050", BEGIN
    )
    assert found.datum == "MSL"
    assert len(found.hourly) > 150
    assert found.events


async def test_noaa_outside_the_us(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Far from its stations, NOAA's list is null, which is no stations."""
    aioclient_mock.get(
        f"{noaa_coops.STATIONS_URL}/tidepredstations.json", json={"stationList": None}
    )
    assert (
        await noaa_coops.async_tide_stations_near(
            async_get_clientsession(hass), *SOLENT_POINT, 25
        )
        == []
    )


def test_tide_sources() -> None:
    """Sources by position are kept by pin; stations by their ID."""
    solent = SimpleNamespace(
        tide_station="worldtides", latitude=SOLENT_POINT[0], longitude=SOLENT_POINT[1]
    )
    assert tides.key(solent) == "worldtides:50.7850,-1.3050"
    assert tides.provider("worldtides:50.7850,-1.3050") == "worldtides"
    assert tides.provider("9410170") == "noaa"
    assert tides.provider("rws:harlingen.waddenzee") == "rws"
    assert tides.provider("model") == "model"
    now = WORLD_RECORDED
    kept = Tides(
        "worldtides:1,2",
        (),
        ((now + timedelta(days=9), 1.0),),
        datum="CD",
    )
    assert not tides.stale(kept, now - timedelta(days=4), now)
    assert tides.stale(kept, now - timedelta(days=4), now + timedelta(days=2))
    daily = Tides("9410170", ())
    assert not tides.stale(daily, now - timedelta(hours=1), now)
    assert tides.stale(daily, now - timedelta(days=1), now)


def test_nws_alerts_at_a_pin() -> None:
    """A lake's alerts for its pin are all kept under the pin."""
    found = nws.parse_alerts(fixture("nws_alerts_lake"), None, "nws:39.0900,-120.0400")
    assert [alert.event for alert in found] == ["Lake Wind Advisory"]
    assert found[0].zone == "nws:39.0900,-120.0400"
    assert warning_group(found[0].event) is WarningGroup.ADVISORY


def test_canadian_warnings() -> None:
    """Canada's warnings run from when they're issued to the end of the next day."""
    (area,) = eccc.parse_areas(fixture("eccc_areas_halifax"))
    assert area.id == "m0000053"
    assert area.parts == ()
    zone = ZoneInfo("America/Halifax")
    found = eccc.parse_warnings(fixture("eccc_area_m0000053"), area.id, zone)
    assert found
    for alert in found:
        assert alert.zone.startswith("eccc:m0000053/")
        assert alert.end.astimezone(zone).hour == 0
        assert alert.end - alert.start < timedelta(days=2)
        assert warning_group(alert.event) is not None
    whole = SimpleNamespace(
        marine_zone="eccc:m0000053", latitude=44.63, longitude=-63.55
    )
    assert all(alerts.applies(alert, alerts.key(whole) or "") for alert in found)
    assert not alerts.applies(found[0], "eccc:m0000053/Somewhere else")


def test_warning_groups_abroad() -> None:
    """Lake, Canadian and European warnings each set a minimum rating."""
    assert warning_group("Lake Wind Advisory") is WarningGroup.ADVISORY
    assert warning_group("Strong wind warning") is WarningGroup.ADVISORY
    assert warning_group("Gale warning") is WarningGroup.GALE
    assert warning_group("Squall watch") is WarningGroup.WATCH
    assert warning_group("Flood Watch") is None
    assert warning_group("Yellow wind warning") is WarningGroup.ADVISORY
    assert warning_group("Orange wind warning") is WarningGroup.GALE
    assert warning_group("Orange thunderstorm warning") is WarningGroup.STORM
    assert warning_group("Red fog warning") is WarningGroup.FOG_AND_SPRAY
    assert warning_group("Yellow rain warning") is None


def test_meteoalarm_feed() -> None:
    """A feed's warnings are read once each, with their regions or outlines."""
    found = meteoalarm.parse_feed(text_fixture("meteoalarm_nl.xml"))
    assert found
    assert all(warning.level in meteoalarm.LEVELS for warning in found)
    flushing = next(warning for warning in found if "NL801" in warning.regions)
    assert flushing.event == "Yellow wind warning"
    assert flushing.link.startswith("https://feeds.meteoalarm.org/")
    assert flushing.expires > flushing.onset
    italy = meteoalarm.parse_feed(text_fixture("meteoalarm_it.xml"))
    assert {warning.kind for warning in italy} >= {"wind"}
    # One warning listed for two regions is read once.
    entry = text_fixture("meteoalarm_nl.xml")
    first = entry[entry.index("<entry>") : entry.index("</entry>") + 8]
    twice = first.replace("NL801", "NL802")
    merged = meteoalarm.parse_feed(f"<feed>{first}{twice}</feed>")
    assert len(merged) == 1
    assert merged[0].regions == ("NL801", "NL802")
    # Titles write a coastal event as one word; a yellow one rates as an advisory.
    coastal = re.sub(
        r"<title>\w+ \w+ Warning", "<title>Yellow Coastalevent Warning", first
    )
    (warning,) = meteoalarm.parse_feed(f"<feed>{coastal}</feed>")
    assert warning.event == "Yellow coastal event warning"
    assert warning_group(warning.event) is WarningGroup.ADVISORY
    with pytest.raises(ProviderError):
        meteoalarm.parse_feed("<html>busy</html>")


def test_meteoalarm_details() -> None:
    """A warning's text is read in English, with its sender."""
    (path,) = list((text_fixture.__globals__["FIXTURES"]).glob("meteoalarm_cap_*.xml"))
    details = meteoalarm.parse_details(path.read_text())
    assert details.sender == "KNMI Royal Netherlands Meteorological Institute"
    assert details.text is not None
    assert "NE-6" in details.text


def test_meteoalarm_regions() -> None:
    """A pin takes its own regions, those close by, or the nearest out at sea."""
    body = json.dumps(meteoalarm_geocodes()).encode()
    table = meteoalarm.parse_regions(body)
    assert len(table) == 7
    wadden = meteoalarm.place(*WADDEN_POINT, table)
    assert set(wadden.regions) == {"NL806", "NL809"}
    assert wadden.services == ("KNMI",)
    garda = meteoalarm.place(*GARDA_POINT, table)
    assert set(garda.regions) == {"IT002", "IT003", "IT006"}
    offshore = meteoalarm.place(51.6, 3.0, table)
    assert offshore.regions == ("NL801",)
    solent = meteoalarm.place(*SOLENT_POINT, table)
    assert solent.regions == ()
    assert solent.countries == ("UK",)
    warning = meteoalarm.parse_feed(text_fixture("meteoalarm_nl.xml"))[0]
    flushing = meteoalarm.place(*VLISSINGEN_POINT, table)
    assert meteoalarm.applies(warning, flushing, *VLISSINGEN_POINT) == (
        "NL801" in warning.regions
    )
    outlined = meteoalarm.Warning(
        level="yellow",
        kind="fog",
        area="A box",
        regions=(),
        outlines=(((50.0, -2.0), (51.0, -2.0), (51.0, -1.0), (50.0, -1.0)),),
        onset=BEGIN,
        expires=BEGIN + timedelta(hours=6),
        sent=BEGIN,
        link="https://feeds.meteoalarm.org/x",
    )
    assert meteoalarm.applies(outlined, solent, *SOLENT_POINT)
    assert not meteoalarm.applies(outlined, wadden, *WADDEN_POINT)
    with pytest.raises(ProviderError):
        meteoalarm.parse_regions(b'{"features": [{"properties": 1}]}')


def test_warning_sources() -> None:
    """Warning sources are named for their provider; zones are the NWS's."""
    assert alerts.provider("PZZ740") == "nws"
    assert alerts.provider("nws") == "nws"
    assert alerts.provider("meteoalarm") == "meteoalarm"
    assert alerts.provider("eccc:m0000144/Western Lake Ontario") == "eccc"
    spot = SimpleNamespace(marine_zone="meteoalarm", latitude=53.18, longitude=5.38)
    assert alerts.key(spot) == "meteoalarm:53.1800,5.3800"
    assert alerts.pin("meteoalarm:53.1800,5.3800") == (53.18, 5.38)
