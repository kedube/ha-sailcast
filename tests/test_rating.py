"""Tests for the safety rating."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import product
from typing import Any

import pytest

from custom_components.sailcast.geo import compass_point
from custom_components.sailcast.limits import Level
from custom_components.sailcast.profiles import SizeClass, Skill
from custom_components.sailcast.rating import rate, wind_chill
from custom_components.sailcast.timeline import Alert, Hour

START = datetime(2026, 11, 7, 18, tzinfo=UTC)
D, K, C, L = (
    SizeClass.DINGHY,
    SizeClass.SMALL_KEELBOAT,
    SizeClass.CRUISER,
    SizeClass.LARGE_CRUISER,
)
BEG, INT, ADV = Skill.BEGINNER, Skill.INTERMEDIATE, Skill.ADVANCED
GOOD, CAUTION, NOT_RECOMMENDED, DANGEROUS = Level


def hour(wind: float, gust: float | None = None, **values: Any) -> Hour:
    """Return a mild, clear hour with the given wind and anything else."""
    defaults: dict[str, Any] = {
        "start": START,
        "daylight": True,
        "wind": wind,
        "gust": wind + 4 if gust is None else gust,
        "wind_direction": 270.0,
        "temperature": 18.0,
        "visibility": 20_000.0,
    }
    return Hour(**(defaults | values))


def alert(event: str) -> Alert:
    """Return an official warning in effect for the test hour."""
    return Alert(event=event, zone="PZZ740", start=START, end=START)


def keys(size: SizeClass, skill: Skill, conditions: Hour) -> list[str]:
    """Return the keys of an hour's reasons."""
    return [reason.key for reason in rate(conditions, size, skill).reasons]


@pytest.mark.parametrize(
    ("size", "wind", "gust", "expected"),
    [
        # The plan's examples with the two test boats.
        (K, 9, 16, (GOOD, GOOD, GOOD)),
        (K, 14, 23, (NOT_RECOMMENDED, CAUTION, CAUTION)),
        (K, 17, 22, (NOT_RECOMMENDED, NOT_RECOMMENDED, CAUTION)),
        (C, 10, 24, (GOOD, GOOD, GOOD)),
        (C, 21, 27, (NOT_RECOMMENDED, NOT_RECOMMENDED, GOOD)),
        (K, 25, 29, (DANGEROUS, DANGEROUS, DANGEROUS)),
        (C, 28, 33, (DANGEROUS, DANGEROUS, DANGEROUS)),
    ],
)
def test_plan_examples(
    size: SizeClass, wind: float, gust: float, expected: tuple[Level, ...]
) -> None:
    """Each skill level gets the rating the plan's table gives."""
    conditions = hour(wind, gust)
    assert tuple(rate(conditions, size, skill).level for skill in (BEG, INT, ADV)) == (
        expected
    )


@pytest.mark.parametrize(
    ("skill", "limit"), [(BEG, 10), (INT, 16)], ids=["beginner", "intermediate"]
)
def test_skill_limits(skill: Skill, limit: float) -> None:
    """Sustained wind up to the limit is fine; just past it is not recommended."""
    at = rate(hour(limit, limit + 3), C, skill)
    past = rate(hour(limit + 0.1, limit + 3), C, skill)
    assert at.level is GOOD
    assert past.level is NOT_RECOMMENDED
    assert past.reasons[0].key == "wind_over_limit"
    assert past.reasons[0].values == {"wind": limit + 0.1, "limit": limit}


def test_gusts_never_count_toward_the_skill_limit() -> None:
    """A beginner's 10 kt limit is for sustained wind only."""
    assert rate(hour(9, 22), C, BEG).level is GOOD


def test_advanced_has_no_wind_limit() -> None:
    """Wind alone stays at caution until the boat's dangerous level."""
    assert rate(hour(24, 27), K, ADV).level is CAUTION
    assert rate(hour(25, 27), K, ADV).level is DANGEROUS


@pytest.mark.parametrize(
    ("size", "wind", "gust", "level"),
    [
        (D, 15, 17, CAUTION),
        (D, 21, 23, DANGEROUS),
        (D, 10, 20, CAUTION),
        (D, 12, 25, DANGEROUS),
        (L, 25, 30, CAUTION),
        (L, 34, 38, DANGEROUS),
        (L, 18, 34, CAUTION),
        (L, 28, 41, DANGEROUS),
    ],
)
def test_boat_wind_and_gust_limits(
    size: SizeClass, wind: float, gust: float, level: Level
) -> None:
    """The boat's caution and dangerous levels start at each number."""
    assert rate(hour(wind, gust), size, ADV).level is level


@pytest.mark.parametrize(
    ("size", "height", "level"),
    [
        (D, 0.29, GOOD),
        (D, 0.31, CAUTION),
        (D, 0.62, NOT_RECOMMENDED),
        (D, 1.22, DANGEROUS),
        (K, 0.62, CAUTION),
        (K, 1.22, NOT_RECOMMENDED),
        (K, 1.99, DANGEROUS),
        (C, 1.83, NOT_RECOMMENDED),
        (C, 3.05, DANGEROUS),
        (L, 2.44, NOT_RECOMMENDED),
        (L, 3.66, DANGEROUS),
    ],
)
def test_wave_limits(size: SizeClass, height: float, level: Level) -> None:
    """Wave limits are the same at every skill level."""
    conditions = hour(8, 10, wave_height=height, wave_period=12.0)
    assert {rate(conditions, size, skill).level for skill in Skill} == {level}


def test_modifiers_stop_at_not_recommended() -> None:
    """Modifiers alone make an hour not recommended, never dangerous."""
    conditions = hour(
        11,
        21,
        wind_direction=90.0,
        temperature=1.0,
        wave_height=0.35,
        wave_period=2.0,
    )
    rating = rate(conditions, D, INT, offshore=["e"])
    modifiers = [reason.key for reason in rating.reasons if reason.modifier]
    assert modifiers == ["gusty", "steep_waves", "offshore_wind", "wind_chill"]
    assert rating.level is NOT_RECOMMENDED


def test_gusty_conditions() -> None:
    """Gusty conditions make it worse, but advanced sailors get caution."""
    gusty = hour(12, 22)
    assert rate(gusty, K, INT).level is NOT_RECOMMENDED
    assert rate(gusty, K, ADV).level is CAUTION
    assert "gusty" in keys(K, ADV, gusty)
    # Cruisers need gusts 15 kt over the mean.
    assert rate(hour(10, 24), C, INT).level is GOOD
    assert rate(hour(10, 25), C, INT).level is CAUTION


def test_steep_short_waves() -> None:
    """Short, steep waves at the caution height make it one level worse."""
    steep = hour(8, 10, wave_height=0.7, wave_period=2.0)
    long = hour(8, 10, wave_height=0.7, wave_period=9.0)
    small = hour(8, 10, wave_height=0.5, wave_period=1.0)
    assert rate(steep, K, ADV).level is NOT_RECOMMENDED
    assert rate(long, K, ADV).level is CAUTION
    assert rate(small, K, ADV).level is GOOD


@pytest.mark.parametrize(
    ("current", "size", "level", "key"),
    [
        (-1.0, K, CAUTION, "wind_against_ebb"),
        (-1.6, K, NOT_RECOMMENDED, "wind_against_ebb"),
        (-1.6, C, CAUTION, "wind_against_ebb"),
        (0.7, K, GOOD, None),
    ],
)
def test_wind_against_current(
    current: float, size: SizeClass, level: Level, key: str | None
) -> None:
    """A westerly against an ebb flowing west steepens the chop."""
    conditions = hour(12, 15, current=current, current_direction=270.0)
    assert rate(conditions, size, ADV).level is level
    if key:
        assert key in keys(size, ADV, conditions)


def test_wind_with_the_current_is_fine() -> None:
    """Wind blowing the same way as the current doesn't count."""
    conditions = hour(12, 15, current=-1.6, current_direction=90.0)
    assert rate(conditions, K, ADV).level is GOOD


def test_wind_against_current_needs_wind() -> None:
    """Under 10 kt of wind, the current rule doesn't apply."""
    conditions = hour(9.9, 13, current=-1.6, current_direction=270.0)
    assert rate(conditions, K, ADV).level is GOOD


def test_offshore_wind_is_for_dinghies() -> None:
    """Offshore wind affects dinghies only, from 8 kt and then 12 kt."""
    light = hour(8, 11, wind_direction=95.0)
    strong = hour(12, 15, wind_direction=95.0)
    assert rate(light, D, ADV, offshore=["e"]).level is CAUTION
    assert rate(strong, D, ADV, offshore=["e"]).level is NOT_RECOMMENDED
    assert rate(strong, K, ADV, offshore=["e"]).level is GOOD
    assert rate(strong, D, ADV, offshore=["w"]).level is GOOD


def test_wind_chill() -> None:
    """Wind chill at or below freezing matters for small boats only."""
    cold = hour(10, 13, temperature=2.0)
    assert rate(cold, K, ADV).level is CAUTION
    assert rate(cold, C, ADV).level is GOOD
    assert rate(hour(10, 13, temperature=8.0), K, ADV).level is GOOD


@pytest.mark.parametrize(
    ("size", "visibility", "level"),
    [
        (K, 3_000, CAUTION),
        (K, 1_500, NOT_RECOMMENDED),
        (C, 3_000, GOOD),
        (C, 1_500, CAUTION),
        (C, 800, NOT_RECOMMENDED),
        (C, 10, NOT_RECOMMENDED),
    ],
)
def test_visibility(size: SizeClass, visibility: float, level: Level) -> None:
    """Forecast visibility can set not recommended, never dangerous."""
    assert rate(hour(8, 10, visibility=visibility), size, ADV).level is level


@pytest.mark.parametrize(
    ("size", "miles", "level"),
    [
        (K, 0.6, NOT_RECOMMENDED),
        (K, 0.4, DANGEROUS),
        (C, 0.4, NOT_RECOMMENDED),
        (C, 0.2, DANGEROUS),
        (L, 0.2, DANGEROUS),
    ],
)
def test_measured_visibility(size: SizeClass, miles: float, level: Level) -> None:
    """A visibility measured nearby can make the hour dangerous."""
    measured = hour(8, 10, visibility=miles * 1852, visibility_measured=True)
    rating = rate(measured, size, ADV)
    assert rating.level is level
    assert rating.reasons[0].key == "visibility_measured"


def test_thunderstorms() -> None:
    """Forecast thunderstorms set a minimum, as does a likely chance of them."""
    storm = hour(8, 10, weather_code=95)
    possible = hour(8, 10, cape=1200.0, rain_chance=50.0)
    assert rate(storm, K, ADV).level is NOT_RECOMMENDED
    assert rate(storm, C, ADV).level is CAUTION
    assert rate(possible, K, ADV).level is CAUTION
    assert rate(possible, C, ADV).level is GOOD


@pytest.mark.parametrize("skill", list(Skill))
def test_small_craft_advisory(skill: Skill) -> None:
    """An advisory holds small boats at not recommended at every skill level."""
    calm = hour(6, 8, alerts=(alert("Small Craft Advisory"),))
    assert rate(calm, D, skill).level is NOT_RECOMMENDED
    assert rate(calm, K, skill).level is NOT_RECOMMENDED
    assert rate(calm, C, skill).level is CAUTION
    assert rate(calm, L, skill).level is CAUTION
    assert rate(calm, K, skill).reasons[0].values == {"event": "Small Craft Advisory"}


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("Gale Warning", (DANGEROUS, DANGEROUS, DANGEROUS, NOT_RECOMMENDED)),
        ("Special Marine Warning", (DANGEROUS,) * 4),
        ("Dense Fog Advisory", (NOT_RECOMMENDED, NOT_RECOMMENDED, CAUTION, CAUTION)),
        ("Gale Watch", (CAUTION,) * 4),
        ("Marine Weather Statement", (GOOD,) * 4),
    ],
)
def test_official_warnings(event: str, expected: tuple[Level, ...]) -> None:
    """Each warning sets its row's minimum, and statements set none."""
    calm = hour(6, 8, alerts=(alert(event),))
    assert tuple(rate(calm, size, ADV).level for size in (D, K, C, L)) == expected


def test_dangerous_never_loosens() -> None:
    """Nothing makes a dangerous hour better, at any skill level."""
    for skill in Skill:
        assert rate(hour(26, 31), K, skill).level is DANGEROUS
        assert rate(hour(6, 8, alerts=(alert("Storm Warning"),)), L, skill).level is (
            DANGEROUS
        )


def test_higher_skill_is_never_worse() -> None:
    """A higher level never gives a worse rating, over a grid of conditions."""
    for wind, spread, size, offshore in product(
        range(0, 36, 2), (2, 8, 12, 16), SizeClass, ((), ("w",))
    ):
        conditions = hour(wind, wind + spread, wave_height=wind / 25, wave_period=4.0)
        levels = [
            rate(conditions, size, skill, offshore).level for skill in (BEG, INT, ADV)
        ]
        assert levels == sorted(levels, reverse=True), (wind, spread, size)


def test_reasons_put_the_worst_first() -> None:
    """The reasons are ordered from the most serious."""
    conditions = hour(14, 23, alerts=(alert("Small Craft Advisory"),))
    rating = rate(conditions, K, INT)
    assert [reason.level for reason in rating.reasons] == sorted(
        (reason.level for reason in rating.reasons), reverse=True
    )
    assert rating.reasons[0].key == "warning"


@pytest.mark.parametrize(
    ("direction", "point"),
    [(0, "n"), (22.4, "n"), (22.5, "ne"), (180, "s"), (337.5, "n"), (359, "n")],
)
def test_compass_point(direction: float, point: str) -> None:
    """Directions round to the nearest of eight compass points."""
    assert compass_point(direction) == point


def test_wind_chill_formula() -> None:
    """Wind chill follows the NWS formula, only in cold and wind."""
    assert wind_chill(2.0, 10) == pytest.approx(-2.5, abs=0.1)
    assert wind_chill(15.0, 20) == 15.0
    assert wind_chill(-5.0, 2) == -5.0
