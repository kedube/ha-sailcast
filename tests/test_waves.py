"""Tests for waves on sheltered water and from sheltered directions."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.sailcast.waves import WaveSource, shelter, wind_waves


def test_wind_waves() -> None:
    """15 kt over 5 km raises waves of about a foot, every two seconds."""
    height, period = wind_waves(15, 5)
    assert height == pytest.approx(0.355, abs=0.005)
    assert period == pytest.approx(2.32, abs=0.02)
    # More wind or more fetch, bigger waves.
    assert wind_waves(20, 5)[0] > height
    assert wind_waves(15, 20)[0] > height
    # No wind or no fetch, no waves.
    assert wind_waves(0, 5) == (0.0, 0.0)
    assert wind_waves(15, 0) == (0.0, 0.0)


def test_wind_waves_level_off() -> None:
    """Over a very long fetch, waves near a fully developed sea."""
    speed = 20 * 0.514444
    full = 0.283 * speed**2 / 9.80665
    assert wind_waves(20, 100_000)[0] == pytest.approx(full, rel=0.01)


def row(**values: Any) -> dict[str, Any]:
    """Return an hour as the timeline builds it."""
    return {"wind": 15.0, "wind_direction": 270.0, "wave_height": None} | values


def test_sheltered_water_gets_an_estimate() -> None:
    """On a river or lake, waves come from the wind and the fetch upwind."""
    rows = [row(), row(wind_direction=90.0)]
    fetches = {270.0: 5.0, 90.0: 0.5}
    shelter(rows, open_water=False, exposed=None, fetch=fetches.__getitem__)
    assert rows[0]["wave_height"] == pytest.approx(0.355, abs=0.005)
    assert rows[0]["wave_direction"] == 270.0
    assert rows[0]["wave_source"] == WaveSource.ESTIMATE
    assert rows[1]["wave_height"] < rows[0]["wave_height"]


def test_sheltered_water_without_fetch() -> None:
    """Without a fetch, a river has no waves to show."""
    rows = [row()]
    shelter(rows, open_water=False, exposed=None, fetch=None)
    assert rows[0]["wave_height"] is None
    assert "wave_source" not in rows[0]


def test_model_waves_from_an_open_direction() -> None:
    """Model waves from a direction the spot is open to stand."""
    rows = [row(wave_height=1.5, wave_period=9.0, wave_direction=280.0)]
    shelter(rows, open_water=True, exposed=("w",), fetch=lambda _: 5.0)
    assert rows[0]["wave_height"] == 1.5
    assert rows[0]["wave_source"] == WaveSource.MODEL


def test_model_waves_from_a_sheltered_direction() -> None:
    """From a sheltered direction, half the model's waves, or the local ones."""
    swell = row(wind=5.0, wave_height=2.0, wave_period=12.0, wave_direction=0.0)
    chop = row(wind=25.0, wave_height=0.4, wave_period=8.0, wave_direction=0.0)
    shelter([swell, chop], open_water=True, exposed=("w",), fetch=lambda _: 10.0)
    assert swell["wave_height"] == 1.0
    assert swell["wave_period"] == 12.0
    assert swell["wave_direction"] == 0.0
    assert swell["wave_source"] == WaveSource.SHELTERED
    local_height, local_period = wind_waves(25, 10)
    assert chop["wave_height"] == local_height
    assert chop["wave_period"] == local_period
    assert chop["wave_direction"] == 270.0
    assert chop["wave_source"] == WaveSource.SHELTERED


@pytest.mark.parametrize(
    ("exposed", "fetch"),
    [(None, 5.0), (("w",), None)],
)
def test_model_waves_stand_without_knowing_the_shelter(
    exposed: tuple[str, ...] | None, fetch: float | None
) -> None:
    """Without exposure or a fetch to estimate from, the model's waves stand."""
    rows = [row(wave_height=2.0, wave_period=12.0, wave_direction=0.0)]
    shelter(
        rows,
        open_water=True,
        exposed=exposed,
        fetch=None if fetch is None else (lambda _: fetch),
    )
    assert rows[0]["wave_height"] == 2.0
    assert rows[0]["wave_source"] == WaveSource.MODEL
