"""Tests for scores, sailing windows and confidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.sailcast.limits import Level
from custom_components.sailcast.profiles import Comfort, RainTolerance, SizeClass, Skill
from custom_components.sailcast.rating import Rating, rate
from custom_components.sailcast.scoring import (
    Band,
    Confidence,
    Slot,
    Window,
    band,
    best_window,
    confidence,
    day_score,
    find_windows,
    ideal_wind,
    is_available,
    score,
    steady_level,
)
from custom_components.sailcast.timeline import Hour

DAY = datetime(2026, 11, 7, tzinfo=ZoneInfo("America/Los_Angeles"))
GOOD = Rating(Level.GOOD)
D, K, C, L = (
    SizeClass.DINGHY,
    SizeClass.SMALL_KEELBOAT,
    SizeClass.CRUISER,
    SizeClass.LARGE_CRUISER,
)
BEG, INT, ADV = Skill.BEGINNER, Skill.INTERMEDIATE, Skill.ADVANCED


def hour(wind: float, gust: float | None = None, **values: Any) -> Hour:
    """Return a mild, clear hour with the given wind and anything else."""
    defaults: dict[str, Any] = {
        "start": datetime(2026, 11, 7, 18, tzinfo=UTC),
        "daylight": True,
        "wind": wind,
        "gust": wind + 2 if gust is None else gust,
        "wind_direction": 270.0,
        "temperature": 18.0,
        "visibility": 20_000.0,
    }
    return Hour(**(defaults | values))


@pytest.mark.parametrize(
    ("size", "ranges"),
    [
        (D, ((5, 10), (5, 14), (5, 14))),
        (K, ((7, 10), (7, 16), (7, 17))),
        (C, ((8, 10), (8, 16), (8, 20))),
        (L, ((8, 10), (8, 16), (8, 22))),
    ],
)
def test_ideal_wind(size: SizeClass, ranges: tuple[tuple[int, int], ...]) -> None:
    """Ideal ranges match the plan's table."""
    assert tuple(ideal_wind(size, skill) for skill in (BEG, INT, ADV)) == ranges


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        (hour(10), 100),
        (hour(5), 68),
        (hour(10, 20), 91),
        (hour(10, wave_height=0.9144), 85),
        (hour(10, rain_chance=50.0), 83),
        (hour(10, temperature=5.0), 89),
        (hour(10, visibility=3_000.0), 85),
        (hour(10, visibility=1_500.0), 70),
    ],
    ids=["ideal", "light", "gusty", "waves", "rain", "cold", "haze", "fog"],
)
def test_score(conditions: Hour, expected: int) -> None:
    """Points come off for light air, gusts, waves, rain, cold and haze."""
    assert score(conditions, K, INT, GOOD) == expected


def test_score_above_the_ideal_range() -> None:
    """Past the ideal range, the score falls toward the limit."""
    # An advanced sailor's range tops out at 17 kt; the boat is dangerous at 25.
    assert score(hour(21), K, ADV, GOOD) == 70
    # Past a beginner's limit the score drops fast.
    assert score(hour(11), K, BEG, GOOD) == 40


@pytest.mark.parametrize(
    ("level", "cap"),
    [
        (Level.GOOD, 100),
        (Level.CAUTION, 55),
        (Level.NOT_RECOMMENDED, 25),
        (Level.DANGEROUS, 0),
    ],
)
def test_rating_caps_the_score(level: Level, cap: int) -> None:
    """A caution hour can't score above 55, so it never joins a window."""
    assert score(hour(10), K, INT, Rating(level)) == cap


def test_higher_skill_never_scores_lower() -> None:
    """Over a grid of conditions, scores never drop as skill goes up."""
    for wind, spread, size in product(range(0, 34), (1, 6, 11), SizeClass):
        conditions = hour(wind, wind + spread)
        scores = [
            score(conditions, size, skill, rate(conditions, size, skill))
            for skill in (BEG, INT, ADV)
        ]
        assert scores == sorted(scores), (wind, spread, size)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (80, Band.GREAT),
        (79, Band.GOOD),
        (60, Band.GOOD),
        (59, Band.FAIR),
        (39, Band.POOR),
    ],
)
def test_bands(value: int, expected: Band) -> None:
    """Scores read as great, good, fair or poor."""
    assert band(value) is expected


def slots(*scores: int, start: int = 7, available: bool = True) -> list[Slot]:
    """Return a day's slots from `start` o'clock, one per score."""
    return [
        Slot(DAY + timedelta(hours=start + i), value, available)
        for i, value in enumerate(scores)
    ]


def test_windows_are_two_hours_or_more_at_60() -> None:
    """A window needs two good hours in a row; caution hours break it."""
    windows = find_windows(slots(50, 65, 70, 80, 55, 61, 62, 90), None, None)
    assert [(w.start.hour, w.end.hour, w.hours, w.score) for w in windows] == [
        (8, 11, 3, 72),
        (12, 15, 3, 71),
    ]


def test_single_good_hour_is_not_a_window() -> None:
    """One good hour alone isn't a window."""
    assert find_windows(slots(40, 85, 40), None, None) == []


def test_windows_stay_in_the_sailors_time() -> None:
    """Hours the sailor can't sail break a window."""
    day = [
        *slots(80, 80),
        *slots(80, start=9, available=False),
        *slots(80, 80, start=10),
    ]
    windows = find_windows(day, None, None)
    assert [(w.start.hour, w.end.hour) for w in windows] == [(7, 9), (10, 12)]


def test_windows_need_hours_in_a_row() -> None:
    """A gap between hours ends a window."""
    day = [*slots(80, 80), *slots(80, 80, start=12)]
    assert len(find_windows(day, None, None)) == 2


def test_windows_end_at_sunset() -> None:
    """Windows start no earlier than sunrise and end by sunset."""
    sunrise = DAY + timedelta(hours=6, minutes=20)
    sunset = DAY + timedelta(hours=16, minutes=34)
    windows = find_windows(slots(*[80] * 11, start=6), sunrise, sunset)
    assert [(w.start, w.end) for w in windows] == [(sunrise, sunset)]


def test_best_window() -> None:
    """The best window has the highest average, or is longer if they're close."""
    short = Window(DAY, DAY + timedelta(hours=2), 80.2, 2)
    long = Window(DAY, DAY + timedelta(hours=4), 79.9, 4)
    worse = Window(DAY, DAY + timedelta(hours=5), 70.0, 5)
    assert best_window([short, long, worse]) is long
    assert best_window([worse, short]) is short
    assert best_window([]) is None


def test_day_score() -> None:
    """A day scores its best window, or at most 59 without one."""
    day = slots(50, 82, 84, 60, 61)
    assert day_score(day, find_windows(day, None, None)) == 72
    no_window = slots(90, 40, 90, 50, 40)
    assert day_score(no_window, find_windows(no_window, None, None)) == 59
    assert day_score(slots(30, 45, 50), []) == 48
    assert day_score(slots(80, 80, available=False), []) is None


def test_confidence() -> None:
    """Confidence follows the typical spread between the models."""

    def hours(*spreads: float) -> list[Hour]:
        return [hour(10, wind_models=(10, 10 + spread, None)) for spread in spreads]

    assert confidence(hours(1, 2, 3, 10)) == (Confidence.HIGH, 3)
    assert confidence(hours(4, 5, 7)) == (Confidence.MEDIUM, 5)
    assert confidence(hours(7, 8)) == (Confidence.LOW, 8)
    assert confidence([hour(10, wind_models=(10, None, None))]) is None


def test_ensemble_spread_lowers_confidence() -> None:
    """A wide ensemble spread lowers confidence, but a narrow one never raises it."""

    def hours(spread: float, sigma: float) -> list[Hour]:
        return [hour(10, wind_models=(10, 10 + spread, None), wind_spread=sigma)] * 3

    assert confidence(hours(1, 1.0)) == (Confidence.HIGH, 1)
    assert confidence(hours(1, 2.5)) == (Confidence.MEDIUM, 1)
    assert confidence(hours(1, 4.0)) == (Confidence.LOW, 1)
    assert confidence(hours(7, 0.5)) == (Confidence.LOW, 7)


def test_is_available() -> None:
    """Sailors sail on their days, between their start and end times."""
    saturday_9 = DAY + timedelta(hours=9)
    friday_9 = saturday_9 - timedelta(days=1)
    assert is_available(["sat"], None, None, saturday_9)
    assert not is_available(["sun"], None, None, saturday_9)
    assert not is_available(["sat", "sun"], None, None, friday_9)
    assert is_available(["sat"], "09:00:00", None, saturday_9)
    assert not is_available(["sat"], "09:30:00", None, saturday_9)
    assert is_available(["sat"], None, "10:00:00", saturday_9)
    assert not is_available(["sat"], None, "09:59:00", saturday_9)


def test_steady_level() -> None:
    """A day's best rating has to hold for two hours in a row."""
    good, caution, not_recommended = Level.GOOD, Level.CAUTION, Level.NOT_RECOMMENDED
    assert steady_level([caution, good, caution]) is caution
    assert steady_level([caution, good, good, not_recommended]) is good
    assert steady_level([not_recommended]) is not_recommended


def test_comfort_narrows_the_ideal_wind() -> None:
    """A sailor's own range can narrow the boat's, never widen it."""
    assert ideal_wind(K, INT, Comfort(ideal_low=9, ideal_high=12)) == (9, 12)
    assert ideal_wind(K, BEG, Comfort(ideal_low=4, ideal_high=20)) == (7, 10)
    # A range wholly above a beginner's 10 kt limit is ignored.
    assert ideal_wind(K, BEG, Comfort(ideal_low=12)) == (7, 10)


def test_comfort_changes_scores() -> None:
    """Comfort moves scores, but the rating's cap still holds."""
    # 13 kt is ideal in a keelboat at 16 kt, but past this sailor's 12 kt: one
    # knot of the four up to their limit costs 15.
    assert score(hour(13), K, INT, GOOD) == 100
    assert score(hour(13), K, INT, GOOD, Comfort(ideal_high=12)) == 85
    # A 40% chance of rain costs 20, 14 or 6, by tolerance.
    wet = hour(10, rain_chance=40)
    assert [
        score(wet, K, INT, GOOD, Comfort(rain=tolerance))
        for tolerance in (RainTolerance.AVOID, RainTolerance.SOME, RainTolerance.ANY)
    ] == [80, 86, 94]
    # 8 °C costs 1.2 points per °F below 10 °C, or below the sailor's own.
    cold = hour(10, temperature=8.0)
    assert score(cold, K, INT, GOOD) == 96
    assert score(cold, K, INT, GOOD, Comfort(coldest=5)) == 100
    assert score(cold, K, INT, GOOD, Comfort(coldest=15)) == 85
    caution = Rating(Level.CAUTION)
    assert score(hour(10), K, INT, caution, Comfort(rain=RainTolerance.ANY)) == 55
