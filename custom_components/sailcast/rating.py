"""The safety rating for one hour, boat size and skill level.

How an hour is rated:

1. Limits. Wind, gusts and wave height are compared with the boat size's
   limits, and sustained wind with the sailor's limit. The worst is the
   starting rating.
2. Modifiers. Each makes the rating one level worse, but modifiers alone
   can't push it past "not recommended".
3. Minimums. Strong offshore wind, strong wind against current and poor
   visibility can set a minimum rating.
4. Fixed minimums. Official warnings and thunderstorms set a minimum at every
   skill level.

Skill changes only the limit for sustained wind and, for Advanced, the gusty
rule, which then sets caution instead of making the rating worse.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
import math

from .limits import (
    AGAINST_CURRENT_ANGLE,
    AGAINST_CURRENT_FLOOR,
    AGAINST_CURRENT_MIN_PERIOD,
    AGAINST_CURRENT_MODIFIER,
    AGAINST_CURRENT_WIND,
    BOAT_LIMITS,
    FOOT,
    NAUTICAL_MILE,
    OFFSHORE_FLOOR_WIND,
    OFFSHORE_MODIFIER_WIND,
    SKILL_WIND_LIMITS,
    THUNDERSTORM_CAPE,
    THUNDERSTORM_CODE,
    THUNDERSTORM_RAIN,
    VISIBILITY_CRUISER,
    VISIBILITY_SMALL,
    WARNING_FLOORS,
    WIND_CHILL,
    BoatLimits,
    Level,
    warning_group,
)
from .profiles import DIRECTIONS, SizeClass, Skill
from .timeline import Hour


@dataclass(frozen=True, slots=True)
class Reason:
    """Why an hour got its rating.

    `key` names the reason in translations and `values` fill it in. `level`
    is the rating this reason sets on its own; a modifier sets none and makes
    the rating one level worse instead.
    """

    key: str
    level: Level
    values: Mapping[str, float | str] = field(default_factory=dict)
    modifier: bool = False


@dataclass(frozen=True, slots=True)
class Rating:
    """An hour's rating and its reasons, the most serious first."""

    level: Level
    reasons: tuple[Reason, ...] = ()


def rate(
    hour: Hour, size: SizeClass, skill: Skill, offshore: Collection[str] = ()
) -> Rating:
    """Rate an hour for a boat size at a skill level.

    `offshore` lists the spot's directions (n, ne, and so on) that blow
    offshore.
    """
    rater = _Rater(hour, size, BOAT_LIMITS[size], SKILL_WIND_LIMITS[skill])
    rater.check_limits()
    rater.check_waves_and_current()
    rater.check_shore_and_weather(offshore)
    rater.check_storms_and_warnings()
    return rater.result()


@dataclass(slots=True)
class _Rater:
    """Collects an hour's reasons as each group of rules runs."""

    hour: Hour
    size: SizeClass
    limits: BoatLimits
    skill_limit: float | None
    base: Level = Level.GOOD
    floor: Level = Level.GOOD
    modifiers: int = 0
    reasons: list[Reason] = field(default_factory=list)

    def note(self, level: Level, key: str, **values: float | str) -> None:
        """Record a limit, which sets the starting rating."""
        self.base = max(self.base, level)
        self.reasons.append(Reason(key, level, values))

    def modify(self, key: str, **values: float | str) -> None:
        """Record a modifier, which makes the rating one level worse."""
        self.modifiers += 1
        self.reasons.append(Reason(key, Level.GOOD, values, modifier=True))

    def set_floor(self, level: Level, key: str, **values: float | str) -> None:
        """Record a minimum rating."""
        self.floor = max(self.floor, level)
        self.reasons.append(Reason(key, level, values))

    def check_limits(self) -> None:
        """Wind and gusts against the boat, sustained wind against the sailor."""
        hour, limits = self.hour, self.limits
        wind = _two_levels(hour.wind, limits.wind)
        if (
            self.skill_limit is not None
            and wind < Level.DANGEROUS
            and hour.wind > self.skill_limit
        ):
            self.note(
                Level.NOT_RECOMMENDED,
                "wind_over_limit",
                wind=hour.wind,
                limit=self.skill_limit,
            )
        elif wind:
            self.note(wind, "wind", wind=hour.wind)
        if gust := _two_levels(hour.gust, limits.gust):
            self.note(gust, "gusts", gust=hour.gust)
        if (spread := hour.gust - hour.wind) >= limits.gusty:
            if self.skill_limit is None:
                # Advanced: wind alone stays at caution, with guidance, until
                # the boat's dangerous level.
                self.note(Level.CAUTION, "gusty", spread=spread)
            else:
                self.modify("gusty", spread=spread)
        if hour.wave_height is not None and (
            waves := _three_levels(hour.wave_height, limits.wave)
        ):
            self.note(waves, "waves", height=hour.wave_height)

    def check_waves_and_current(self) -> None:
        """Steep, short waves, and wind against the current."""
        hour, limits = self.hour, self.limits
        height, period = hour.wave_height, hour.wave_period
        if (
            height is not None
            and period
            and height >= limits.wave[0]
            and (height > math.pow(period, 3.3) / 250 or height / FOOT >= period)
        ):
            self.modify("steep_waves", height=height, period=period)
        if (
            hour.current is None
            or hour.current_direction is None
            or hour.wind < AGAINST_CURRENT_WIND
        ):
            return
        period = max(AGAINST_CURRENT_MIN_PERIOD, hour.wave_period or 0)
        speed = abs(hour.current)
        downwind = (hour.wind_direction + 180) % 360
        if (
            _angle(downwind, hour.current_direction) < 180 - AGAINST_CURRENT_ANGLE
            or speed < AGAINST_CURRENT_MODIFIER * period
        ):
            return
        key = "wind_against_flood" if hour.current > 0 else "wind_against_ebb"
        if limits.small and speed >= AGAINST_CURRENT_FLOOR * period:
            self.set_floor(Level.NOT_RECOMMENDED, key, current=speed)
        else:
            self.modify(key, current=speed)

    def check_shore_and_weather(self, offshore: Collection[str]) -> None:
        """Offshore wind for dinghies, wind chill and forecast visibility."""
        hour, limits = self.hour, self.limits
        if self.size is SizeClass.DINGHY and compass_point(hour.wind_direction) in (
            offshore
        ):
            if hour.wind >= OFFSHORE_FLOOR_WIND:
                self.set_floor(Level.NOT_RECOMMENDED, "offshore_wind", wind=hour.wind)
            elif hour.wind >= OFFSHORE_MODIFIER_WIND:
                self.modify("offshore_wind", wind=hour.wind)
        if limits.small and hour.temperature is not None:
            chill = wind_chill(hour.temperature, hour.wind)
            if chill <= WIND_CHILL:
                self.modify("wind_chill", temperature=chill)
        if hour.visibility is not None:
            caution, not_recommended = (
                VISIBILITY_SMALL if limits.small else VISIBILITY_CRUISER
            )
            miles = hour.visibility / NAUTICAL_MILE
            # Forecast visibility is rough, so it never makes an hour dangerous.
            if miles < not_recommended:
                self.set_floor(
                    Level.NOT_RECOMMENDED, "visibility", visibility=hour.visibility
                )
            elif miles < caution:
                self.set_floor(Level.CAUTION, "visibility", visibility=hour.visibility)

    def check_storms_and_warnings(self) -> None:
        """Thunderstorms and official warnings, the same at every skill level."""
        hour, small = self.hour, self.limits.small
        if hour.weather_code is not None and hour.weather_code >= THUNDERSTORM_CODE:
            self.set_floor(
                Level.NOT_RECOMMENDED if small else Level.CAUTION, "thunderstorms"
            )
        elif (
            small
            and (hour.cape or 0) >= THUNDERSTORM_CAPE
            and (hour.rain_chance or 0) >= THUNDERSTORM_RAIN
        ):
            self.set_floor(Level.CAUTION, "thunderstorms_possible")
        for alert in hour.alerts:
            if group := warning_group(alert.event):
                self.set_floor(
                    WARNING_FLOORS[group][self.size], "warning", event=alert.event
                )

    def result(self) -> Rating:
        """Return the rating: modifiers alone stop at not recommended."""
        level = max(
            self.base,
            min(self.base + self.modifiers, Level.NOT_RECOMMENDED),
            self.floor,
        )
        self.reasons.sort(key=lambda reason: reason.level, reverse=True)
        return Rating(Level(level), tuple(self.reasons))


def wind_chill(temperature: float, wind: float) -> float:
    """Return the wind chill in °C for air in °C and wind in knots.

    This is the NWS formula, which only applies at or below 50 °F and in wind
    of at least 3 mph.
    """
    fahrenheit = temperature * 9 / 5 + 32
    mph = wind * 1.150779
    if fahrenheit > 50 or mph < 3:
        return temperature
    v = math.pow(mph, 0.16)
    chill = 35.74 + 0.6215 * fahrenheit - 35.75 * v + 0.4275 * fahrenheit * v
    return (chill - 32) * 5 / 9


def compass_point(direction: float) -> str:
    """Return the nearest of the eight compass points, such as "ne".

    A direction halfway between two points goes to the next one clockwise.
    """
    return DIRECTIONS[math.floor(direction % 360 / 45 + 0.5) % len(DIRECTIONS)]


def _angle(a: float, b: float) -> float:
    """Return the angle between two directions, from 0 to 180 degrees."""
    difference = abs(a - b) % 360
    return 360 - difference if difference > 180 else difference


def _two_levels(value: float, starts: tuple[float, float]) -> Level:
    if value >= starts[1]:
        return Level.DANGEROUS
    if value >= starts[0]:
        return Level.CAUTION
    return Level.GOOD


def _three_levels(value: float, starts: tuple[float, float, float]) -> Level:
    for level, start in zip(
        (Level.DANGEROUS, Level.NOT_RECOMMENDED, Level.CAUTION),
        reversed(starts),
        strict=True,
    ):
        if value >= start:
            return level
    return Level.GOOD
