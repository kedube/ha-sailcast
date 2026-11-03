"""Spot, boat and sailor profiles.

Each profile is a subentry of the SailCast entry. The setup dialogs use the
checks here, and the panel's settings will use the same ones, so a profile
saved either way is valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Container, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS

from .const import (
    CONF_AHEAD,
    CONF_AUTO_CALENDAR,
    CONF_AUTO_DAYS,
    CONF_AUTO_SPOTS,
    CONF_BOATS,
    CONF_CALENDAR,
    CONF_COLDEST,
    CONF_COMFORT,
    CONF_CURRENT_STATION,
    CONF_DAYS,
    CONF_END,
    CONF_EXPOSED,
    CONF_IDEAL_HIGH,
    CONF_IDEAL_LOW,
    CONF_LENGTH,
    CONF_MARINE_ZONE,
    CONF_MIN_SCORE,
    CONF_OFFSHORE,
    CONF_RAIN,
    CONF_SIZE_CLASS,
    CONF_SKILL,
    CONF_SOURCE_NAMES,
    CONF_SPOTS,
    CONF_START,
    CONF_TIDE_STATION,
    CONF_USER,
    CONF_WATER_TYPE,
    SUBENTRY_BOAT,
    SUBENTRY_SAILOR,
    SUBENTRY_SPOT,
)

MAX_NAME_LENGTH = 40

# The radius sets the wind map's area around a spot, in meters.
DEFAULT_RADIUS = 15_000
MIN_RADIUS = 2_000
MAX_RADIUS = 50_000

# Boat lengths, in meters.
MIN_LENGTH = 1.0
MAX_LENGTH = 50.0

DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")

# A sailor's ideal wind, in knots, and the coldest air they enjoy, in °C.
MAX_IDEAL_WIND: Final = 40.0
COLDEST_RANGE: Final = (-20.0, 35.0)

# Automatic calendar adding: the lowest scores a sailor can choose, and how
# far ahead, as the last day counted from today (1 is today and tomorrow).
MIN_SCORES: Final = (60, 80)
AHEAD_DAYS: Final = (1, 2, 4, 6)


class WaterType(StrEnum):
    """The kind of water a spot is on."""

    OPEN_COAST = "open_coast"
    BAY = "bay"
    RIVER = "river"
    LAKE = "lake"


class SizeClass(StrEnum):
    """Boat sizes. Each has its own safety limits."""

    DINGHY = "dinghy"
    SMALL_KEELBOAT = "small_keelboat"
    CRUISER = "cruiser"
    LARGE_CRUISER = "large_cruiser"


class Skill(StrEnum):
    """Skill levels. Each sets the sailor's limit for sustained wind."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RainTolerance(StrEnum):
    """How much a chance of rain lowers a sailor's scores."""

    AVOID = "avoid"
    SOME = "some"
    ANY = "any"


@dataclass(frozen=True, slots=True, kw_only=True)
class Spot:
    """A place to sail, and where its tides, currents and warnings come from.

    The current station includes its depth bin, as in "PCT0056_1". The
    sources' names are kept when they're chosen, by source.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    radius: float
    water_type: WaterType
    offshore: tuple[str, ...] = ()
    exposed: tuple[str, ...] = ()
    tide_station: str | None = None
    current_station: str | None = None
    marine_zone: str | None = None
    source_names: Mapping[str, str] = field(default_factory=dict, hash=False)

    @property
    def open_water(self) -> bool:
        """Return whether the ocean wave model applies here."""
        return self.water_type in (WaterType.OPEN_COAST, WaterType.BAY)

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> Spot:
        """Read a spot from its subentry."""
        data = subentry.data
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            latitude=data[CONF_LATITUDE],
            longitude=data[CONF_LONGITUDE],
            radius=data[CONF_RADIUS],
            water_type=WaterType(data[CONF_WATER_TYPE]),
            offshore=tuple(data.get(CONF_OFFSHORE, ())),
            exposed=tuple(data.get(CONF_EXPOSED, ())),
            tide_station=data.get(CONF_TIDE_STATION),
            current_station=data.get(CONF_CURRENT_STATION),
            marine_zone=data.get(CONF_MARINE_ZONE),
            source_names=dict(data.get(CONF_SOURCE_NAMES) or {}),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Boat:
    """A boat. Its length is in meters."""

    id: str
    name: str
    size_class: SizeClass
    length: float

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> Boat:
        """Read a boat from its subentry."""
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            size_class=SizeClass(subentry.data[CONF_SIZE_CLASS]),
            length=subentry.data[CONF_LENGTH],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Comfort:
    """What a sailor enjoys. It changes their scores, never a safety rating.

    The ideal wind (kt) can only narrow the range their boat and skill allow.
    Cold lowers scores below `coldest` (°C), or 10 °C if it isn't set.
    """

    ideal_low: float | None = None
    ideal_high: float | None = None
    coldest: float | None = None
    rain: RainTolerance = RainTolerance.SOME

    @classmethod
    def from_data(cls, data: Mapping[str, Any] | None) -> Comfort:
        """Read comfort settings, which older sailors don't have."""
        data = data or {}
        return cls(
            ideal_low=data.get(CONF_IDEAL_LOW),
            ideal_high=data.get(CONF_IDEAL_HIGH),
            coldest=data.get(CONF_COLDEST),
            rain=RainTolerance(data.get(CONF_RAIN, RainTolerance.SOME)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AutoCalendar:
    """Automatic adding: each chosen day's best window goes into a calendar.

    `ahead` is the last day to add, counted from today, and `min_score` the
    lowest window score. Spots that have been removed are left out.
    """

    calendar: str
    days: tuple[str, ...]
    min_score: int
    ahead: int
    spots: tuple[str, ...]

    @classmethod
    def from_data(
        cls, data: Mapping[str, Any] | None, spots: Container[str]
    ) -> AutoCalendar | None:
        """Read the settings, or None if automatic adding is off."""
        if not data or not data.get(CONF_CALENDAR):
            return None
        return cls(
            calendar=data[CONF_CALENDAR],
            days=tuple(data[CONF_DAYS]),
            min_score=data[CONF_MIN_SCORE],
            ahead=data[CONF_AHEAD],
            spots=tuple(spot for spot in data[CONF_SPOTS] if spot in spots),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Sailor:
    """A sailor, with their boats and when they can sail.

    The first boat is their default. A missing start or end means sunrise or
    sunset. `user` is the Home Assistant user the panel opens on this sailor
    for.
    """

    id: str
    name: str
    skill: Skill
    boats: tuple[str, ...]
    days: tuple[str, ...]
    start: str | None = None
    end: str | None = None
    user: str | None = None
    comfort: Comfort = Comfort()
    auto_calendar: AutoCalendar | None = None

    @classmethod
    def from_subentry(
        cls,
        subentry: ConfigSubentry,
        boats: Container[str],
        spots: Container[str] = (),
    ) -> Sailor:
        """Read a sailor, leaving out boats and spots removed since."""
        data = subentry.data
        return cls(
            id=subentry.subentry_id,
            name=subentry.title,
            skill=Skill(data[CONF_SKILL]),
            boats=tuple(boat for boat in data[CONF_BOATS] if boat in boats),
            days=tuple(data[CONF_DAYS]),
            start=data.get(CONF_START),
            end=data.get(CONF_END),
            user=data.get(CONF_USER),
            comfort=Comfort.from_data(data.get(CONF_COMFORT)),
            auto_calendar=AutoCalendar.from_data(data.get(CONF_AUTO_CALENDAR), spots),
        )


@dataclass(frozen=True, slots=True)
class Profiles:
    """Every spot, boat and sailor in the SailCast entry, by subentry ID."""

    spots: dict[str, Spot]
    boats: dict[str, Boat]
    sailors: dict[str, Sailor]

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> Profiles:
        """Read the profiles from the entry's subentries."""
        by_type: defaultdict[str, list[ConfigSubentry]] = defaultdict(list)
        for subentry in entry.subentries.values():
            by_type[subentry.subentry_type].append(subentry)
        boats = {
            subentry.subentry_id: Boat.from_subentry(subentry)
            for subentry in by_type[SUBENTRY_BOAT]
        }
        spots = {
            subentry.subentry_id: Spot.from_subentry(subentry)
            for subentry in by_type[SUBENTRY_SPOT]
        }
        return cls(
            spots=spots,
            boats=boats,
            sailors={
                subentry.subentry_id: Sailor.from_subentry(subentry, boats, spots)
                for subentry in by_type[SUBENTRY_SAILOR]
            },
        )

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Return the profiles as lists sorted by name, for the panel."""
        return {
            "spots": _sorted_dicts(self.spots.values()),
            "boats": _sorted_dicts(self.boats.values()),
            "sailors": _sorted_dicts(self.sailors.values()),
        }


def _sorted_dicts(profiles: Iterable[Spot | Boat | Sailor]) -> list[dict[str, Any]]:
    return [
        asdict(profile)
        for profile in sorted(profiles, key=lambda profile: profile.name.casefold())
    ]


def in_order(values: Iterable[str], order: Iterable[str]) -> list[str]:
    """Return the chosen values in a fixed order, such as Monday to Sunday."""
    chosen = set(values)
    return [value for value in order if value in chosen]


def check_name(name: str, taken: Iterable[str]) -> str | None:
    """Return an error if the name is empty, too long or already used."""
    name = name.strip()
    if not name:
        return "name_required"
    if len(name) > MAX_NAME_LENGTH:
        return "name_too_long"
    if name.casefold() in {other.casefold() for other in taken}:
        return "name_taken"
    return None


def check_spot(data: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a spot's data, by field."""
    if not MIN_RADIUS <= data[CONF_RADIUS] <= MAX_RADIUS:
        return {CONF_RADIUS: "radius_out_of_range"}
    return {}


def check_boat(data: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a boat's data, by field."""
    if not MIN_LENGTH <= data[CONF_LENGTH] <= MAX_LENGTH:
        return {CONF_LENGTH: "length_out_of_range"}
    return {}


def check_sailor(
    data: Mapping[str, Any], boats: Container[str], spots: Container[str] = ()
) -> dict[str, str]:
    """Return errors in a sailor's data, by field."""
    errors = {}
    if not data[CONF_BOATS] or any(boat not in boats for boat in data[CONF_BOATS]):
        errors[CONF_BOATS] = "unknown_boat"
    if not data[CONF_DAYS]:
        errors[CONF_DAYS] = "no_days"
    start, end = data.get(CONF_START), data.get(CONF_END)
    if start and end and start >= end:
        errors[CONF_END] = "end_before_start"
    errors.update(check_comfort(data.get(CONF_COMFORT) or {}))
    errors.update(check_auto_calendar(data.get(CONF_AUTO_CALENDAR), spots))
    return errors


def check_comfort(comfort: Mapping[str, Any]) -> dict[str, str]:
    """Return errors in a sailor's comfort settings, by field."""
    errors = {}
    low, high = comfort.get(CONF_IDEAL_LOW), comfort.get(CONF_IDEAL_HIGH)
    for key, value in ((CONF_IDEAL_LOW, low), (CONF_IDEAL_HIGH, high)):
        if value is not None and not 0 <= value <= MAX_IDEAL_WIND:
            errors[key] = "ideal_out_of_range"
    if low is not None and high is not None and low >= high and not errors:
        errors[CONF_IDEAL_HIGH] = "ideal_high_below_low"
    coldest = comfort.get(CONF_COLDEST)
    if coldest is not None and not COLDEST_RANGE[0] <= coldest <= COLDEST_RANGE[1]:
        errors[CONF_COLDEST] = "coldest_out_of_range"
    return errors


def check_auto_calendar(
    auto: Mapping[str, Any] | None, spots: Container[str]
) -> dict[str, str]:
    """Return errors in automatic adding, which is off without a calendar.

    Days and spots are reported as auto_days and auto_spots, apart from the
    sailor's own days.
    """
    if not auto or not auto.get(CONF_CALENDAR):
        return {}
    errors = {}
    if not auto.get(CONF_DAYS):
        errors[CONF_AUTO_DAYS] = "no_days"
    if not auto.get(CONF_SPOTS) or any(spot not in spots for spot in auto[CONF_SPOTS]):
        errors[CONF_AUTO_SPOTS] = "no_spots"
    if auto.get(CONF_MIN_SCORE) not in MIN_SCORES:
        errors[CONF_MIN_SCORE] = "invalid_min_score"
    if auto.get(CONF_AHEAD) not in AHEAD_DAYS:
        errors[CONF_AHEAD] = "invalid_ahead"
    return errors
