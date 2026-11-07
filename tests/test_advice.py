"""Tests for day summaries and rule-based advice."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.sailcast.advice import Advice, advise
from custom_components.sailcast.profiles import SizeClass, Skill, Spot, WaterType
from custom_components.sailcast.providers import TideEvent
from custom_components.sailcast.summary import Trend, summarize
from custom_components.sailcast.timeline import Alert, Daylight, Hour

ZONE = ZoneInfo("America/Los_Angeles")
# Saturday 9 AM to 4 PM in San Diego.
START = datetime(2026, 11, 7, 17, tzinfo=UTC)
DAY = Daylight(
    datetime(2026, 11, 7).date(),
    datetime(2026, 11, 7, 14, 10, tzinfo=UTC),
    datetime(2026, 11, 8, 0, 50, tzinfo=UTC),
    ZONE,
)
SPOT = Spot(
    id="harbor",
    name="Harbor",
    latitude=32.75,
    longitude=-117.27,
    radius=10_000,
    water_type=WaterType.OPEN_COAST,
    offshore=("ne", "e"),
)
D, K, C = SizeClass.DINGHY, SizeClass.SMALL_KEELBOAT, SizeClass.CRUISER
BEG, INT, ADV = Skill.BEGINNER, Skill.INTERMEDIATE, Skill.ADVANCED


def hours(winds: list[float], **values: Any) -> list[Hour]:
    """Return a run of mild hours from START with the given winds."""
    defaults: dict[str, Any] = {
        "daylight": True,
        "wind_direction": 270.0,
        "temperature": 18.0,
        "visibility": 20_000.0,
        "rain_chance": 10.0,
    }
    return [
        Hour(
            **(
                defaults
                | {
                    "start": START + timedelta(hours=index),
                    "wind": wind,
                    "gust": wind + 4,
                }
                | values
            )
        )
        for index, wind in enumerate(winds)
    ]


def keys(advice: list[Advice]) -> list[str]:
    """Return the advice's keys, in order."""
    return [item.key for item in advice]


def by_key(advice: list[Advice], key: str) -> Advice:
    """Return one piece of advice."""
    return next(item for item in advice if item.key == key)


def test_summary() -> None:
    """Ranges, the most rain, the worst weather and the trend."""
    run = hours([6, 7, 8, 10, 12, 13], rain_chance=20.0)
    run[2] = Hour(**(vars_of(run[2]) | {"rain_chance": 60.0, "weather_code": 61}))
    summary = summarize(run)
    assert summary is not None
    assert (summary.wind_low, summary.wind_high, summary.gust) == (6, 13, 17)
    assert summary.trend is Trend.BUILDING
    assert summary.rain_chance == 60
    assert summary.weather_code == 61
    assert summary.waves is None
    assert summarize(hours([12, 12, 9, 9, 6, 6])).trend is Trend.EASING  # type: ignore[union-attr]
    assert summarize(hours([8, 9, 8])).trend is None  # type: ignore[union-attr]
    assert summarize([]) is None


def vars_of(hour: Hour) -> dict[str, Any]:
    """Return an hour's fields."""
    return {name: getattr(hour, name) for name in hour.__slots__}


def test_calm_day() -> None:
    """A calm day: the wind, the water, the tides in daylight and sunset."""
    tide = TideEvent(START + timedelta(hours=2, minutes=20), 1.4, True)
    early = TideEvent(DAY.sunrise - timedelta(hours=1), 0.2, False)
    advice = advise(
        SPOT,
        K,
        INT,
        DAY,
        hours([9, 8, 9, 9], water_temperature=17.5, wave_height=0.5),
        tides=[early, tide],
    )
    assert keys(advice) == ["wind", "waves", "water", "tides", "sunset"]
    assert by_key(advice, "wind").values == {
        "direction": 270,
        "low": 8,
        "high": 9,
        "gust": 13,
        "trend": None,
    }
    assert by_key(advice, "tides").values == {
        "events": [{"time": tide.time.isoformat(), "height": 1.4, "high": True}]
    }
    assert by_key(advice, "sunset").values == {"time": DAY.sunset.isoformat()}
    assert not any(item.hot for item in advice)


def test_tides_after_dark_with_lights() -> None:
    """With navigation lights, the tides after sunset count too."""
    night = [
        Hour(**(vars_of(hour) | {"start": DAY.sunset + timedelta(hours=index)}))
        for index, hour in enumerate(hours([9, 9, 8], daylight=False))
    ]
    tide = TideEvent(DAY.sunset + timedelta(hours=1, minutes=30), 1.6, True)
    lit = advise(SPOT, C, INT, DAY, night, tides=[tide], lights=True)
    assert keys(lit) == ["wind", "tides", "sunset"]
    assert by_key(lit, "tides").values == {
        "events": [{"time": tide.time.isoformat(), "height": 1.6, "high": True}]
    }
    assert "tides" not in keys(advise(SPOT, C, INT, DAY, night, tides=[tide]))


def test_day_over() -> None:
    """With no daylight left, there's only one thing to say."""
    assert keys(advise(SPOT, K, INT, DAY, [])) == ["day_over"]


def test_over_the_skill_limit() -> None:
    """Wind past the sailor's limit, for one hour or several."""
    one = advise(SPOT, K, BEG, DAY, hours([8, 11, 9]))
    assert by_key(one, "over_limit_hour").values == {
        "limit": 10,
        "time": (START + timedelta(hours=1)).isoformat(),
    }
    many = advise(SPOT, K, BEG, DAY, hours([11, 9, 12]))
    assert by_key(many, "over_limit").values == {
        "limit": 10,
        "start": START.isoformat(),
        "end": (START + timedelta(hours=3)).isoformat(),
    }
    assert by_key(many, "over_limit").hot
    near = advise(SPOT, K, INT, DAY, hours([12, 14]))
    assert "near_limit" in keys(near)
    assert "near_limit" not in keys(advise(SPOT, K, ADV, DAY, hours([12, 14])))


@pytest.mark.parametrize(
    ("size", "winds", "expected", "absent"),
    [
        (K, [3, 4], "light_air", "gusty"),
        (C, [19, 20], "reef", "depower"),
        (K, [15, 16], "depower", "reef"),
    ],
)
def test_wind_advice(
    size: SizeClass, winds: list[float], expected: str, absent: str
) -> None:
    """Light air, and reefing as the wind nears the boat's caution level."""
    advice = keys(advise(SPOT, size, ADV, DAY, hours(winds)))
    assert expected in advice
    assert absent not in advice


def test_gusty_for_small_boats() -> None:
    """Gusts well over the wind matter to dinghies and small keelboats."""
    run = hours([10, 11], gust=20.0)
    assert "gusty_dinghy" in keys(advise(SPOT, D, ADV, DAY, run))
    assert "gusty" in keys(advise(SPOT, K, ADV, DAY, run))
    assert not {"gusty", "gusty_dinghy"} & set(keys(advise(SPOT, C, ADV, DAY, run)))


def test_warnings() -> None:
    """Each warning in effect, phrased by what it means for the boat size."""
    advisory = Alert(
        event="Small Craft Advisory", zone="PZZ740", start=START, end=START
    )
    gale = Alert(event="Gale Warning", zone="PZZ740", start=START, end=START)
    run = hours([12, 14], alerts=(advisory,))
    assert by_key(advise(SPOT, K, ADV, DAY, run), "warning_not_recommended").values == {
        "event": "Small Craft Advisory",
        "size": "small_keelboat",
    }
    assert "warning_caution" in keys(advise(SPOT, C, ADV, DAY, run))
    stormy = hours([12], alerts=(advisory, gale))
    assert keys(advise(SPOT, C, ADV, DAY, stormy))[:2] == [
        "warning_caution",
        "warning_dangerous",
    ]
    odd = hours(
        [12], alerts=(Alert(event="Beach Hazards", zone="x", start=START, end=START),)
    )
    assert by_key(advise(SPOT, C, ADV, DAY, odd), "warning").hot


def test_wind_against_current() -> None:
    """A westerly over an ebb flowing west steepens the chop."""
    run = hours([12, 12, 12], current=-1.2, current_direction=265.0)
    advice = by_key(advise(SPOT, C, ADV, DAY, run), "against_current")
    assert advice.values == {
        "flow": "ebb",
        "start": START.isoformat(),
        "end": (START + timedelta(hours=3)).isoformat(),
    }
    slack = hours([12, 12], current=0.3, current_direction=85.0)
    assert "against_current" not in keys(advise(SPOT, C, ADV, DAY, slack))


def test_offshore_wind_for_dinghies() -> None:
    """Wind off the beach is flagged for dinghies only."""
    run = hours([9, 10], wind_direction=60.0)
    assert by_key(advise(SPOT, D, ADV, DAY, run), "offshore").hot
    assert "offshore" not in keys(advise(SPOT, K, ADV, DAY, run))


def test_rain() -> None:
    """Likely rain, with the visibility when it's poor."""
    assert by_key(
        advise(SPOT, K, INT, DAY, hours([8], rain_chance=50.0)), "rain"
    ).values == {"chance": 50.0}
    murky = hours([8], rain_chance=70.0, visibility=2500.0)
    assert by_key(advise(SPOT, K, INT, DAY, murky), "rain_visibility").values == {
        "chance": 70.0,
        "visibility": 2500.0,
    }
