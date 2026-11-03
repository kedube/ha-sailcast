"""Tests for nudging the next hours toward what's read now."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from custom_components.sailcast.nowcast import (
    AIRPORT,
    BUOY,
    SENSORS,
    Observation,
    latest,
    nudge,
)
from custom_components.sailcast.providers import Reading, Readings
from custom_components.sailcast.providers.open_meteo import (
    MODELS,
    NEARBY_VARIABLES,
    Forecast,
    Marine,
)

NOON = datetime(2026, 11, 2, 20, tzinfo=UTC)
HOUR = timedelta(hours=1)
TIMES = tuple(NOON + HOUR * n for n in range(-2, 10))


def forecast(wind: float = 8.0, direction: float = 270.0) -> Forecast:
    """Return a steady forecast from the three models."""
    steady = {
        "wind_speed_10m": wind,
        "wind_gusts_10m": wind + 4,
        "wind_direction_10m": direction,
        "temperature_2m": 18.0,
    }
    return Forecast(
        times=TIMES,
        values={
            variable: tuple((steady[variable],) * len(TIMES) for _ in MODELS)
            for variable in NEARBY_VARIABLES
        },
    )


def marine(height: float = 1.0) -> Marine:
    """Return steady waves and water temperature at a buoy."""
    return Marine(
        times=TIMES,
        values={
            "wave_height": (height,) * len(TIMES),
            "sea_surface_temperature": (16.0,) * len(TIMES),
        },
    )


def readings(
    when: datetime = NOON + timedelta(minutes=10), **values: float
) -> Readings:
    """Return readings of some fields, all read at once."""
    return Readings({key: Reading(value, when) for key, value in values.items()})


def rows() -> list[dict[str, Any]]:
    """Return a spot's hours, as the timeline builds them."""
    return [
        {
            "start": when,
            "wind": 10.0,
            "gust": 14.0,
            "wind_direction": 270.0,
            "wind_models": (9.0, 10.0, 11.0),
            "temperature": 18.0,
            "visibility": 20_000.0,
            "wave_height": 1.0,
            "water_temperature": 16.0,
        }
        for when in TIMES
    ]


def test_best_fresh_source() -> None:
    """Each field comes from the best source with a fresh reading."""
    sensors = Observation(SENSORS, None, readings(wind=12.0))
    buoy = Observation(BUOY, "46258", readings(wind=14.0, wave_height=1.5))
    old = NOON - timedelta(hours=3)
    airport = Observation(AIRPORT, "KSAN", readings(old, wind=9.0, temperature=20.0))
    chosen = latest([airport, buoy, sensors], NOON + timedelta(minutes=20))
    assert chosen["wind"][0] is sensors
    assert chosen["wave_height"][0] is buoy
    # The airport's reading has expired.
    assert "temperature" not in chosen
    # A reading a little ahead of the clock still counts, but not more.
    ahead = Observation(
        AIRPORT, "KSAN", readings(NOON + timedelta(minutes=30), temperature=20.0)
    )
    assert "temperature" in latest([ahead], NOON + timedelta(minutes=25))
    assert "temperature" not in latest([ahead], NOON)


def test_wind_fades_over_six_hours() -> None:
    """The difference from the forecast there fades out over six hours."""
    hours = rows()
    airport = Observation(AIRPORT, "KSAN", readings(wind=12.0), forecast(8.0))
    adjustments = nudge(
        hours, latest([airport], NOON), forecast=None, marine=None, now=NOON
    )
    assert [(item.field, item.difference) for item in adjustments] == [("wind", 4.0)]
    by_time = {hour["start"]: hour for hour in hours}
    # Hours before the reading stay as forecast.
    assert by_time[NOON - HOUR]["wind"] == 10.0
    # The hour it was read in moves most, then less each hour.
    first = by_time[NOON]["wind"]
    assert first == pytest.approx(10 + 4 * (1 - 20 / 360))
    assert by_time[NOON + HOUR]["wind"] == pytest.approx(10 + 4 * (1 - 80 / 360))
    assert by_time[NOON + 6 * HOUR]["wind"] == 10.0
    # Each model moves with it, and so do gusts, with no gust reading.
    assert by_time[NOON]["wind_models"][1] == pytest.approx(first)
    assert by_time[NOON]["gust"] == pytest.approx(14 + first - 10)
    assert by_time[NOON]["adjusted"] == ("wind", "gust")


def test_gusts_and_light_air() -> None:
    """A gust reading moves gusts on its own; in light air direction stays."""
    hours = rows()
    buoy = Observation(
        BUOY, "46258", readings(wind=2.0, gust=20.0, wind_direction=90.0), forecast(8.0)
    )
    nudge(hours, latest([buoy], NOON), forecast=None, marine=None, now=NOON)
    assert hours[2]["wind"] < 10
    # Gusts never fall below the wind.
    assert hours[2]["gust"] > 14
    assert hours[2]["wind_direction"] == 270.0


def test_direction_turns_the_short_way() -> None:
    """A reading of 10° against a forecast of 350° turns the wind 20°."""
    hours = rows()
    airport = Observation(
        AIRPORT,
        "KSAN",
        readings(wind=10.0, wind_direction=10.0),
        forecast(10.0, direction=350.0),
    )
    nudge(hours, latest([airport], NOON), forecast=None, marine=None, now=NOON)
    assert hours[2]["wind_direction"] == pytest.approx(
        (270 + 20 * (1 - 20 / 360)) % 360
    )


def test_sensors_use_the_spots_forecast() -> None:
    """Sensors are at the spot, so they're compared with its own forecast."""
    hours = rows()
    sensors = Observation(SENSORS, None, readings(temperature=21.0))
    adjustments = nudge(
        hours,
        latest([sensors], NOON),
        forecast=forecast(),
        marine=None,
        now=NOON,
    )
    assert adjustments[0].difference == pytest.approx(3.0)
    # Without the spot's forecast there's nothing to compare with.
    assert not nudge(
        rows(), latest([sensors], NOON), forecast=None, marine=None, now=NOON
    )


def test_buoy_waves() -> None:
    """A buoy's waves move the spot's model waves by the difference there."""
    hours = rows()
    buoy = Observation(
        BUOY,
        "46258",
        readings(wave_height=1.6, water_temperature=17.0),
        marine=marine(1.2),
    )
    adjustments = nudge(
        hours, latest([buoy], NOON), forecast=None, marine=None, now=NOON
    )
    assert {item.field: round(item.difference, 6) for item in adjustments} == {
        "wave_height": 0.4,
        "water_temperature": 1.0,
    }
    assert hours[2]["wave_height"] > 1.0
    # Hours with no waves to move are left alone.
    calm = rows()
    calm[2]["wave_height"] = None
    nudge(calm, latest([buoy], NOON), forecast=None, marine=None, now=NOON)
    assert calm[2]["wave_height"] is None


def test_measured_visibility() -> None:
    """A measured visibility replaces the forecast's for the hour under way only."""
    hours = rows()
    airport = Observation(AIRPORT, "KSAN", readings(visibility=600.0))
    now = NOON + timedelta(minutes=40)
    nudge(hours, latest([airport], now), forecast=None, marine=None, now=now)
    assert hours[2]["visibility"] == 600.0
    assert hours[2]["visibility_measured"] is True
    assert hours[3]["visibility"] == 20_000.0
    assert "visibility_measured" not in hours[3]


def test_reading_between_hours() -> None:
    """What was forecast for a reading's time lies between the hours around it."""
    times = (NOON, NOON + HOUR)
    there = Forecast(
        times=times,
        values={
            variable: tuple((6.0, 12.0) for _ in MODELS)
            for variable in NEARBY_VARIABLES
        },
    )
    airport = Observation(
        AIRPORT, "KSAN", readings(NOON + timedelta(minutes=30), wind=9.0), there
    )
    now = NOON + timedelta(minutes=30)
    adjustments = nudge(
        rows(), latest([airport], now), forecast=None, marine=None, now=now
    )
    assert adjustments[0].difference == pytest.approx(0.0)
