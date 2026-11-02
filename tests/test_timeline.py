"""Tests for the hourly conditions timeline."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
import statistics
from zoneinfo import ZoneInfo

import pytest

from custom_components.sailcast.providers import noaa_coops, nws, open_meteo
from custom_components.sailcast.timeline import Alert, Daylight, build, daylight

from .conftest import BAY_POINT, HARBOR_POINT, fixture

PACIFIC = ZoneInfo("America/Los_Angeles")
FIRST_DAY = date(2026, 11, 2)
HOUR = timedelta(hours=1)


def days(point: tuple[float, float], count: int = 7) -> list[Daylight]:
    """Return a week of sunrises and sunsets at a point."""
    return [
        daylight(*point, FIRST_DAY + timedelta(days=offset), PACIFIC)
        for offset in range(count)
    ]


@pytest.fixture(name="forecasts")
def forecasts_fixture() -> list[open_meteo.Forecast]:
    """Return the recorded forecast for the three spots."""
    return open_meteo.parse_forecast(fixture("open_meteo_forecast"), 3)


@pytest.fixture(name="marine")
def marine_fixture() -> list[open_meteo.Marine]:
    """Return the recorded marine data for the two open water spots."""
    return open_meteo.parse_marine(fixture("open_meteo_marine"), 2)


def tides(station: str, *, hourly: bool) -> noaa_coops.Tides:
    """Return a station's recorded tides."""
    events = noaa_coops.parse_tide_events(
        fixture(f"noaa_tides_{station}_hilo"), station
    )
    if not hourly:
        return noaa_coops.Tides(station, events)
    heights = noaa_coops.parse_tide_heights(fixture(f"noaa_tides_{station}_h"), station)
    return noaa_coops.Tides(station, events, heights)


def test_hours_cover_the_local_days(forecasts: list[open_meteo.Forecast]) -> None:
    """The timeline starts at local midnight and keeps the forecast's hours."""
    hours = build(forecast=forecasts[0], days=days(HARBOR_POINT))
    assert hours[0].start == datetime(2026, 11, 2, 8, tzinfo=UTC)
    assert all(b.start - a.start == HOUR for a, b in pairwise(hours))
    # The recording ends partway through the seventh day.
    assert hours[-1].start == datetime(2026, 11, 8, 23, tzinfo=UTC)


def test_models_are_combined(forecasts: list[open_meteo.Forecast]) -> None:
    """Wind is the middle model; rain chance, CAPE and codes the highest."""
    forecast = forecasts[0]
    hours = build(forecast=forecast, days=days(HARBOR_POINT))
    hour = hours[30]
    index = forecast.times.index(hour.start)
    winds = forecast.at("wind_speed_10m", index)
    assert hour.wind_models == winds
    assert hour.wind == statistics.median(winds)
    assert hour.gust == statistics.median(forecast.at("wind_gusts_10m", index))
    assert hour.rain_chance == max(forecast.at("precipitation_probability", index))
    visibilities = [v for v in forecast.at("visibility", index) if v is not None]
    assert hour.visibility == min(visibilities)
    assert 0 <= hour.wind_direction < 360


def test_daylight(forecasts: list[open_meteo.Forecast]) -> None:
    """An hour is daylight when most of it is between sunrise and sunset."""
    week = days(HARBOR_POINT)
    first = week[0]
    assert first.sunrise.astimezone(PACIFIC).hour == 6
    assert first.sunset.astimezone(PACIFIC).hour == 16
    hours = build(forecast=forecasts[0], days=week)
    local = {hour.start.astimezone(PACIFIC).hour: hour.daylight for hour in hours[:24]}
    assert not local[5]
    assert local[6]
    assert local[16]
    assert not local[17]


def test_polar_days() -> None:
    """Where the sun stays up or down all day, daylight covers all or none of it."""
    arctic = (78.2, 15.6)
    oslo = ZoneInfo("Europe/Oslo")
    summer = daylight(*arctic, date(2026, 6, 21), oslo)
    winter = daylight(*arctic, date(2026, 12, 21), oslo)
    assert summer.sunset - summer.sunrise == timedelta(days=1)
    assert winter.sunrise == winter.sunset
    noon = datetime(2026, 12, 21, 12, tzinfo=oslo)
    assert not winter.covers(noon)


def test_marine_data(
    forecasts: list[open_meteo.Forecast], marine: list[open_meteo.Marine]
) -> None:
    """Open water spots get waves and water temperature."""
    hours = build(forecast=forecasts[0], days=days(HARBOR_POINT), marine=marine[0])
    hour = hours[10]
    index = marine[0].times.index(hour.start)
    assert hour.wave_height == marine[0].values["wave_height"][index]
    assert hour.wave_period == marine[0].values["wave_period"][index]
    assert hour.water_temperature is not None
    river = build(forecast=forecasts[2], days=days(HARBOR_POINT))
    assert river[10].wave_height is None


def test_hourly_tides(forecasts: list[open_meteo.Forecast]) -> None:
    """A harmonic station's hourly heights are used as they are."""
    station = tides("9410170", hourly=True)
    hours = build(forecast=forecasts[0], days=days(HARBOR_POINT), tides=station)
    heights = dict(station.hourly)
    for hour in hours[:48]:
        assert hour.tide_height == heights[hour.start]
    # Between a low and the next high, the tide is rising.
    low = next(event for event in station.events if not event.high)
    after = next(hour for hour in hours if hour.start > low.time)
    assert after.tide_rising is True


def test_interpolated_tides(forecasts: list[open_meteo.Forecast]) -> None:
    """A subordinate station's highs and lows are joined by a cosine curve."""
    station = tides("9410166", hourly=False)
    hours = build(forecast=forecasts[1], days=days(BAY_POINT), tides=station)
    for hour in hours:
        before = [event for event in station.events if event.time <= hour.start]
        after = [event for event in station.events if event.time > hour.start]
        if not before or not after:
            assert hour.tide_height is None
            continue
        low, high = sorted((before[-1].height, after[0].height))
        assert hour.tide_height is not None
        assert low <= hour.tide_height <= high
        assert hour.tide_rising is after[0].high


def test_currents(forecasts: list[open_meteo.Forecast]) -> None:
    """Currents between slack and peak times follow a cosine curve."""
    currents = noaa_coops.parse_currents(
        fixture("noaa_currents_PCT0056_1"), "PCT0056_1"
    )
    hours = build(forecast=forecasts[1], days=days(BAY_POINT), currents=currents)
    speeds = [hour.current for hour in hours if hour.current is not None]
    assert max(speeds) > 0 > min(speeds)
    peak = max(abs(event.speed) for event in currents.events)
    assert max(abs(speed) for speed in speeds) <= peak
    for hour in hours:
        if hour.current is not None and hour.current > 0:
            assert hour.current_direction == currents.flood_direction
        elif hour.current is not None and hour.current < 0:
            assert hour.current_direction == currents.ebb_direction


def test_alerts_apply_from_onset_to_end(
    forecasts: list[open_meteo.Forecast],
) -> None:
    """An alert covers the hours between its onset and end, not before."""
    alerts = nws.parse_alerts(fixture("nws_alerts"), {"PZZ745"})
    hours = build(forecast=forecasts[0], days=days(HARBOR_POINT), alerts=alerts)
    covered = [hour.start for hour in hours if hour.alerts]
    assert covered[0] == datetime(2026, 11, 3, 21, tzinfo=UTC)
    assert covered[-1] == datetime(2026, 11, 4, 11, tzinfo=UTC)
    assert len(covered) == 15


def test_alert_partway_through_an_hour(
    forecasts: list[open_meteo.Forecast],
) -> None:
    """An alert that starts partway through an hour covers that hour."""
    start = datetime(2026, 11, 5, 18, 30, tzinfo=UTC)
    alert = Alert(
        event="Gale Warning", zone="PZZ740", start=start, end=start + timedelta(hours=2)
    )
    hours = build(forecast=forecasts[0], days=days(HARBOR_POINT), alerts=[alert])
    covered = [hour.start.hour for hour in hours if hour.alerts]
    assert covered == [18, 19, 20]


def test_no_days_no_hours(forecasts: list[open_meteo.Forecast]) -> None:
    """Without any days there's nothing to build."""
    assert build(forecast=forecasts[0], days=[]) == []
